"""Key-value settings, encrypted at rest. Secrets are never rendered back to
a page, the UI shows a mask, and saving an empty field keeps the old value.
"""
import json

from . import db
from .crypto import decrypt, encrypt

# Keys whose values are secrets: masked in the UI, kept on empty save.
SECRET_KEYS = {"smtp_password", "github_token", "vapid_private", "totp_secret"}


def get(key: str, default: str = "") -> str:
    with db.connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return decrypt(row["value"])
    except Exception:
        return default


def put(key: str, value: str):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, encrypt(value), db.now_millis()),
        )


def get_json(key: str, default=None):
    raw = get(key, "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        return default


def put_json(key: str, value):
    put(key, json.dumps(value))


def save_form(form, keys):
    """Save settings from a form dict. Empty secret fields keep what's there."""
    for key in keys:
        value = (form.get(key) or "").strip()
        if key in SECRET_KEYS and value == "":
            continue
        put(key, value)


def smtp_configured() -> bool:
    return all(get(k) for k in ("smtp_host", "smtp_port", "smtp_from"))
