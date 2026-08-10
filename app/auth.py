"""Login, sessions, optional TOTP 2FA, and device access keys.

Single-account by design: this is a personal server. First visit with no
account set up walks through creating one. Passwords are scrypt-hashed;
device access keys are random tokens stored as SHA-256 hashes.
"""
import hashlib
import hmac
import secrets
from functools import wraps

import pyotp
from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .settings_store import get as setting_get, put as setting_put

bp = Blueprint("auth", __name__)


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


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if account_exists():
        return redirect(url_for("auth.login"))
    error = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        if len(username) < 2:
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
                # Same first-run behaviour as the app: start with one list.
                count = conn.execute(
                    "SELECT COUNT(*) c FROM lists WHERE deleted_at IS NULL").fetchone()["c"]
                if count == 0:
                    conn.execute(
                        "INSERT INTO lists (id, name, position, updated_at) VALUES (?, 'Reminders', 0, ?)",
                        (db.new_id(), db.now_millis()),
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
        if account and hmac.compare_digest(username, account["username"]) \
                and check_password_hash(account["password_hash"], password):
            totp_secret = setting_get("totp_secret")
            if totp_secret:
                session["pending_2fa"] = True
                return redirect(url_for("auth.second_factor"))
            session.clear()
            session["user"] = username
            session.permanent = True
            return redirect(url_for("views.home"))
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
        if totp.verify(code, valid_window=1):
            account = _get_account()
            session.clear()
            session["user"] = account["username"]
            session.permanent = True
            return redirect(url_for("views.home"))
        error = "That code didn't match. Codes change every 30 seconds, try the current one."
    return render_template("second_factor.html", error=error)


@bp.route("/logout", methods=["POST"])
def logout():
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
