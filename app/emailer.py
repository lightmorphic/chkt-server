"""Outgoing email over plain SMTP, provider-agnostic.

Fail-safe and visible: if SMTP isn't fully configured, nothing pretends to
send. The message is recorded and the UI says so.
"""
import smtplib
import ssl
from email.message import EmailMessage

from . import db
from .settings_store import get as setting, smtp_configured


def send(subject: str, body: str, to: str | None = None):
    """Returns (ok, plain-language message)."""
    recipient = to or setting("alert_email")
    if not recipient:
        _record(subject, body, "No alert email address is set.")
        return False, "No alert email address is set, message recorded instead."
    if not smtp_configured():
        _record(subject, body, "SMTP is not fully configured.")
        return False, "Email isn't fully set up, message recorded instead of sent."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = setting("smtp_from")
    msg["To"] = recipient
    msg.set_content(body)

    host = setting("smtp_host")
    port = int(setting("smtp_port") or "587")
    user = setting("smtp_username")
    password = setting("smtp_password")

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls(context=ssl.create_default_context())
        with server:
            if user:
                server.login(user, password)
            server.send_message(msg)
        return True, f"Sent to {recipient}."
    except Exception as e:
        _record(subject, body, f"Send failed: {e}")
        return False, f"Sending failed: {e}"


def _record(subject: str, body: str, reason: str):
    with db.connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS mail_outbox ("
            "id TEXT PRIMARY KEY, subject TEXT, body TEXT, reason TEXT, at INTEGER)"
        )
        conn.execute(
            "INSERT INTO mail_outbox (id, subject, body, reason, at) VALUES (?,?,?,?,?)",
            (db.new_id(), subject, body, reason, db.now_millis()),
        )


def outbox():
    with db.connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS mail_outbox ("
            "id TEXT PRIMARY KEY, subject TEXT, body TEXT, reason TEXT, at INTEGER)"
        )
        return conn.execute("SELECT * FROM mail_outbox ORDER BY at DESC LIMIT 20").fetchall()
