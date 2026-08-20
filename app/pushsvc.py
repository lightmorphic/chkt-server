"""Web push + the due-reminder engine.

A background thread wakes every 20 seconds, finds reminders whose time has
arrived, pushes a notification to every subscribed browser, records the fire,
and advances repeating reminders, mirroring what the Android app does
locally. An open CHKT page also polls /web/fired and does the talking
(browser speech synthesis) client-side.
"""
import json
import threading
import time

from . import db, store
from .settings_store import get as setting, put as setting_put, quiet_hours_now

_started = False


def ensure_vapid_keys():
    """Generate the web-push VAPID keypair once, stored encrypted."""
    if setting("vapid_private"):
        return
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    import base64

    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_raw = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = base64.urlsafe_b64encode(public_raw).rstrip(b"=").decode()
    setting_put("vapid_private", private_pem)
    setting_put("vapid_public", public_b64)


def public_key() -> str:
    return setting("vapid_public")


def add_subscription(subscription: dict):
    """One row per endpoint: the page re-subscribes on every load, and
    without the replace this grew a duplicate row (and a duplicate push
    per fire) each time."""
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM push_subscriptions WHERE json_extract(subscription_json, '$.endpoint') = ?",
            (subscription.get("endpoint"),),
        )
        conn.execute(
            "INSERT INTO push_subscriptions (id, subscription_json, created_at) VALUES (?,?,?)",
            (db.new_id(), json.dumps(subscription), db.now_millis()),
        )


def _push_all(title: str, body: str, reminder_id: str, quiet: bool = False):
    from pywebpush import webpush, WebPushException

    private_pem = setting("vapid_private")
    if not private_pem:
        return
    claims = {"sub": "mailto:" + (setting("alert_email") or "admin@localhost")}
    with db.connect() as conn:
        subs = conn.execute("SELECT * FROM push_subscriptions").fetchall()
    for sub in subs:
        try:
            webpush(
                subscription_info=json.loads(sub["subscription_json"]),
                data=json.dumps({"title": title, "body": body, "reminderId": reminder_id, "quiet": quiet}),
                vapid_private_key=private_pem,
                vapid_claims=dict(claims),
            )
        except WebPushException as e:
            # 404/410 means the browser dropped the subscription, forget it.
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                with db.connect() as conn:
                    conn.execute("DELETE FROM push_subscriptions WHERE id = ?", (sub["id"],))
        except Exception:
            continue


def recently_fired(since_millis: int):
    """Fires newer than `since`, the web page polls this to alert in-page."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT f.reminder_id, f.due_at, f.fired_at, f.quiet, "
            "r.title, r.notes, r.alert_mode, r.pre_tone, r.vibrate "
            "FROM fired f JOIN reminders r ON r.id = f.reminder_id "
            "WHERE f.fired_at > ? ORDER BY f.fired_at", (since_millis,)).fetchall()
        return [dict(r) for r in rows]


def _prune(now: int):
    """Housekeeping once a day: fire records and sent mail have no value
    after a week / a month, and nothing else ever deletes them."""
    last = setting("last_prune_at")
    if last and now - int(last) < 24 * 3600 * 1000:
        return
    setting_put("last_prune_at", str(now))
    with db.connect() as conn:
        conn.execute("DELETE FROM fired WHERE fired_at < ?", (now - 7 * 24 * 3600 * 1000,))
    try:
        with db.connect() as conn:
            conn.execute("DELETE FROM mail_outbox WHERE at < ?", (now - 30 * 24 * 3600 * 1000,))
    except Exception:
        pass  # table only exists once the first email has been sent


def _loop():
    while True:
        try:
            now = db.now_millis()
            _prune(now)
            # Computed once per tick: same window used for every reminder
            # that fires in this pass, same as the app checking it once per alert.
            quiet = quiet_hours_now()

            for reminder in store.due_now():
                fire_at = reminder["snoozed_until"] or reminder["due_at"]
                store.mark_fired(reminder["id"], fire_at, quiet)
                _push_all(reminder["title"], reminder.get("notes") or "", reminder["id"], quiet)
                if reminder.get("nag_interval_minutes"):
                    # Keep the occurrence live and keep reminding until answered.
                    store.set_nag_started(reminder["id"], now)
                else:
                    store.advance_after_fire(reminder)

            for reminder in store.nagging_now():
                started = reminder["nag_started_at"]
                fire_at = reminder["snoozed_until"] or reminder["due_at"] or started
                if now - started >= reminder["nag_stop_after_minutes"] * 60_000:
                    # Gave it a fair go; count it missed and move on.
                    store.add_log(reminder["id"], fire_at, "MISSED")
                    store.advance_after_fire(reminder)
                    continue
                last = store.last_fired_at(reminder["id"]) or started
                if now - last >= reminder["nag_interval_minutes"] * 60_000:
                    store.touch_fired(reminder["id"], fire_at, quiet)
                    _push_all(reminder["title"], reminder.get("notes") or "", reminder["id"], quiet)
        except Exception:
            # The engine must never die; next tick retries.
            pass
        time.sleep(20)


def start_engine():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="chkt-due-engine").start()
