"""Key-value settings, encrypted at rest. Secrets are never rendered back to
a page, the UI shows a mask, and saving an empty field keeps the old value.
"""
import datetime

from . import db
from .crypto import decrypt, encrypt

# Keys whose values are secrets: masked in the UI, kept on empty save.
SECRET_KEYS = {"smtp_password", "vapid_private", "totp_secret", "remote_cal_password"}


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


def save_form(form, keys):
    """Save settings from a form dict. Empty secret fields keep what's there."""
    for key in keys:
        value = (form.get(key) or "").strip()
        if key in SECRET_KEYS and value == "":
            continue
        put(key, value)


def smtp_configured() -> bool:
    return all(get(k) for k in ("smtp_host", "smtp_port", "smtp_from"))


def quiet_hours() -> dict:
    """Mirrors the app's QuietHours: off by default, HH:MM start/end."""
    return {
        "enabled": get("quiet_enabled") == "1",
        "start": get("quiet_start", "22:00"),
        "end": get("quiet_end", "07:00"),
    }


def set_quiet_hours(enabled: bool, start: str, end: str):
    put("quiet_enabled", "1" if enabled else "0")
    put("quiet_start", start)
    put("quiet_end", end)


def quiet_hours_now(now: datetime.datetime = None) -> bool:
    """True if `now` (real clock, unless given for testing) falls inside the
    configured quiet window. Handles a window that spans midnight, same as
    the app's version of this check."""
    q = quiet_hours()
    if not q["enabled"]:
        return False
    try:
        sh, sm = (int(x) for x in q["start"].split(":"))
        eh, em = (int(x) for x in q["end"].split(":"))
    except (ValueError, AttributeError):
        return False
    now = now or datetime.datetime.now()
    t = now.hour * 60 + now.minute
    start_m, end_m = sh * 60 + sm, eh * 60 + em
    if start_m <= end_m:
        return start_m <= t < end_m
    return t >= start_m or t < end_m
