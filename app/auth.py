"""Login, sessions, optional TOTP 2FA, and device access keys.

Single-account by design: this is a personal server. First visit with no
account set up walks through creating one. Passwords are scrypt-hashed;
device access keys are random tokens stored as SHA-256 hashes.
"""
import hashlib
import hmac
import os
import secrets
import threading
import time
from functools import wraps

import pyotp
from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .settings_store import get as setting_get, put as setting_put

bp = Blueprint("auth", __name__)


@bp.app_context_processor
def _inject_csrf():
    """Every template can render {{ csrf_token() }}, including pages like
    the base layout's logout form that don't go through a view's kwargs."""
    return {"csrf_token": csrf_token}


# ---- Online-guessing throttle (login and 2FA) ----
#
# Single-account personal server: after MAX_FAILURES wrong passwords or
# codes from one address inside the window, that address waits out the rest
# of the window. In-memory on purpose — a restart clearing it is fine, the
# point is making sustained remote guessing (especially of 6-digit TOTP
# codes) uneconomical, not perfect bookkeeping.
_MAX_FAILURES = 5
_WINDOW_SECONDS = 15 * 60
_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()


def _throttle_key() -> str:
    return request.remote_addr or "?"


def _throttled() -> bool:
    now = time.monotonic()
    with _failures_lock:
        fails = [t for t in _failures.get(_throttle_key(), []) if now - t < _WINDOW_SECONDS]
        _failures[_throttle_key()] = fails
        return len(fails) >= _MAX_FAILURES


def _record_failure():
    with _failures_lock:
        _failures.setdefault(_throttle_key(), []).append(time.monotonic())


def _clear_failures():
    with _failures_lock:
        _failures.pop(_throttle_key(), None)


_THROTTLED_MESSAGE = "Too many attempts. Wait 15 minutes and try again."
_EXPIRED_MESSAGE = "The form has expired, reload the page and try again."


def account_exists() -> bool:
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) c FROM auth").fetchone()["c"] > 0


def _get_account():
    with db.connect() as conn:
        return conn.execute("SELECT * FROM auth WHERE id = 1").fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not account_exists():
            return redirect(url_for("auth.setup"))
        if not session.get("user"):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf():
    sent = request.form.get("csrf", "")
    return hmac.compare_digest(sent, session.get("csrf", "-"))


def _setup_token_ok() -> bool:
    """Optional gate for internet-facing installs: when CHKT_SETUP_TOKEN is
    set, first-run account creation needs that token (?setup_token=...), so
    a stranger who finds the fresh install can't claim the account. Unset
    (the private-network default), setup stays open exactly as before."""
    required = os.environ.get("CHKT_SETUP_TOKEN", "")
    if not required:
        return True
    supplied = request.args.get("setup_token") or request.form.get("setup_token") or ""
    return hmac.compare_digest(supplied, required)


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if account_exists():
        return redirect(url_for("auth.login"))
    if not _setup_token_ok():
        return ("This server requires a setup token. Open /setup?setup_token=... "
                "with the token from your CHKT_SETUP_TOKEN setting.", 403)
    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        if not check_csrf():
            error = _EXPIRED_MESSAGE
        elif len(username) < 2:
            error = "Pick a username of at least 2 characters."
        elif len(password) < 12:
            error = "Use a password of at least 12 characters."
        elif password != confirm:
            error = "The two passwords don't match."
        else:
            with db.connect() as conn:
                conn.execute(
                    "INSERT INTO auth (id, username, password_hash, created_at) VALUES (1, ?, ?, ?)",
                    (username, generate_password_hash(password, method="scrypt"), db.now_millis()),
                )
            session.clear()
            session["user"] = username
            return redirect(url_for("views.home"))
    return render_template("setup.html", error=error)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not account_exists():
        return redirect(url_for("auth.setup"))
    error = ""
    if request.method == "POST":
        account = _get_account()
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not check_csrf():
            error = _EXPIRED_MESSAGE
        elif _throttled():
            error = _THROTTLED_MESSAGE
        elif account and hmac.compare_digest(username, account["username"]) \
                and check_password_hash(account["password_hash"], password):
            _clear_failures()
            totp_secret = setting_get("totp_secret")
            if totp_secret:
                session["pending_2fa"] = True
                return redirect(url_for("auth.second_factor"))
            session.clear()
            session["user"] = username
            session.permanent = True
            return redirect(url_for("views.home"))
        else:
            _record_failure()
            error = "Wrong username or password."
    return render_template("login.html", error=error)


@bp.route("/login/2fa", methods=["GET", "POST"])
def second_factor():
    if not session.get("pending_2fa"):
        return redirect(url_for("auth.login"))
    error = ""
    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        totp = pyotp.TOTP(setting_get("totp_secret"))
        if not check_csrf():
            error = _EXPIRED_MESSAGE
        elif _throttled():
            error = _THROTTLED_MESSAGE
        # A TOTP code is single-use: replaying one that already signed in
        # (shoulder-surfed, intercepted) must fail even inside its window.
        elif code != setting_get("totp_last_used") and totp.verify(code, valid_window=1):
            setting_put("totp_last_used", code)
            _clear_failures()
            account = _get_account()
            session.clear()
            session["user"] = account["username"]
            session.permanent = True
            return redirect(url_for("views.home"))
        else:
            _record_failure()
            error = "That code didn't match. Codes change every 30 seconds, try the current one."
    return render_template("second_factor.html", error=error)


@bp.route("/logout", methods=["POST"])
def logout():
    if check_csrf():
        session.clear()
    return redirect(url_for("auth.login"))


# ---- Device access keys (for the Android app's sync) ----

def new_access_key(label: str) -> str:
    token = secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO access_keys (id, label, key_hash, created_at) VALUES (?, ?, ?, ?)",
            (db.new_id(), label or "Device", _hash_key(token), db.now_millis()),
        )
    return token


def revoke_access_key(key_id: str):
    with db.connect() as conn:
        conn.execute("DELETE FROM access_keys WHERE id = ?", (key_id,))


def list_access_keys():
    with db.connect() as conn:
        return conn.execute("SELECT id, label, created_at, last_used_at FROM access_keys ORDER BY created_at").fetchall()


def verify_access_key(token: str) -> bool:
    if not token:
        return False
    hashed = _hash_key(token)
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM access_keys WHERE key_hash = ?", (hashed,)).fetchone()
        if row is None:
            return False
        conn.execute("UPDATE access_keys SET last_used_at = ? WHERE id = ?", (db.now_millis(), row["id"]))
    return True


def _hash_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
