"""Reminder data operations, the single write path for both the web UI and
the sync API, so nothing can drift.
"""
from datetime import datetime

from . import db
from .repeat_rules import next_after

_LEGACY_ALERT_MODES = {"RING_AND_SPEAK": "NOTIFY_AND_SPEAK", "RING_ONLY": "NOTIFY_ONLY"}
_ALERT_MODES = {"NOTIFY_AND_SPEAK", "SPEAK_ONLY", "NOTIFY_ONLY"}


def normalize_alert_mode(value):
    """Maps a stored/imported alert_mode onto the current three-way scheme.
    Ringing was removed as an alert component; a JSON export/sync payload
    from an older app or server build can still carry the old five values."""
    value = _LEGACY_ALERT_MODES.get(value, value)
    return value if value in _ALERT_MODES else "NOTIFY_AND_SPEAK"


REMINDER_FIELDS = (
    "id", "tags", "title", "notes", "due_at", "repeat_rule", "alert_mode",
    "pre_tone", "enabled", "vibrate", "respect_dnd", "nag_interval_minutes",
    "nag_stop_after_minutes", "nag_started_at", "delete_after_dismissed",
    "snoozed_until", "location_trigger", "latitude",
    "longitude", "radius_metres", "created_at", "updated_at", "deleted_at",
)


def next_alert_millis(reminder: dict, now: int = None) -> int:
    """Sort key for the reminder list: once a repeating reminder's fire time
    has passed, its real next alert is the next occurrence (tomorrow, next
    week, ...), not the stale past time still in due_at until it's answered
    or nag-timed-out. A one-off keeps its raw time even when overdue — it
    has no next occurrence to roll forward to, and unanswered still means
    it needs attention now."""
    raw = reminder.get("snoozed_until") or reminder.get("due_at")
    if raw is None:
        return None
    now = now if now is not None else db.now_millis()
    if raw > now:
        return raw
    nxt = next_after(reminder.get("repeat_rule", ""),
                      datetime.fromtimestamp(raw / 1000).astimezone(),
                      datetime.fromtimestamp(now / 1000).astimezone())
    return int(nxt.timestamp() * 1000) if nxt is not None else raw


def is_ended(r) -> bool:
    """A reminder that has ended: switched off and not deleted. Covers a
    one-off that fired (answering one switches it off), a repeating
    reminder whose run is over, and anything turned off by hand. These
    live on the History page rather than the main list — visible to look
    back on, and reusable by switching back on with a new date. Mirrors
    the app's isEnded."""
    return not r["enabled"] and r.get("deleted_at") is None


def reminders(include_deleted=False):
    q = ("SELECT * FROM reminders"
         + ("" if include_deleted else " WHERE deleted_at IS NULL"))
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute(q).fetchall()]
    now = db.now_millis()
    rows.sort(key=lambda r: (
        not r["enabled"],
        next_alert_millis(r, now) is None,
        next_alert_millis(r, now) or 0,
    ))
    return rows


def tag_list(reminder):
    return [t.strip() for t in (reminder.get("tags") or "").split(",") if t.strip()]


def all_tags():
    seen = []
    for r in reminders():
        for t in tag_list(r):
            if t not in seen:
                seen.append(t)
    return sorted(seen)


def get_reminder(reminder_id):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return dict(row) if row else None


def upsert_reminder(record: dict):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO reminders ({fields}) VALUES ({marks}) "
            "ON CONFLICT(id) DO UPDATE SET {sets}".format(
                fields=",".join(REMINDER_FIELDS),
                marks=",".join("?" * len(REMINDER_FIELDS)),
                sets=",".join(f"{f}=excluded.{f}" for f in REMINDER_FIELDS if f != "id"),
            ),
            tuple(record.get(f) for f in REMINDER_FIELDS),
        )


def soft_delete(table: str, record_id: str):
    assert table == "reminders"
    now = db.now_millis()
    with db.connect() as conn:
        conn.execute(f"UPDATE {table} SET deleted_at = ?, updated_at = ? WHERE id = ?",
                     (now, now, record_id))


def add_log(reminder_id: str, due_at: int, action: str):
    with db.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO completion_log (id, reminder_id, due_at, action, at) VALUES (?,?,?,?,?)",
            (db.new_id(), reminder_id, due_at, action, db.now_millis()),
        )


def log_counts(since_millis: int):
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT action, COUNT(*) c FROM completion_log WHERE at >= ? GROUP BY action",
            (since_millis,)).fetchall()
    counts = {r["action"]: r["c"] for r in rows}
    done, missed = counts.get("DONE", 0), counts.get("MISSED", 0)
    rate = round(done * 100 / (done + missed)) if (done + missed) else None
    return {"done": done, "missed": missed, "snoozed": counts.get("SNOOZED", 0), "rate": rate}


def advance_after_fire(reminder: dict):
    """Same behaviour as the app: repeating reminders move on, one-offs disable."""
    now = db.now_millis()
    prev = reminder.get("due_at")
    nxt = None
    if prev is not None:
        nxt = next_after(reminder.get("repeat_rule", ""),
                         datetime.fromtimestamp(prev / 1000).astimezone(),
                         datetime.now().astimezone())
    updated = dict(reminder)
    updated["snoozed_until"] = None
    updated["nag_started_at"] = None
    updated["updated_at"] = now
    if nxt is not None:
        updated["due_at"] = int(nxt.timestamp() * 1000)
    elif reminder.get("location_trigger", "NONE") == "NONE":
        updated["enabled"] = 0
    upsert_reminder(updated)
    return updated


def acknowledge(reminder_id: str, due_at: int, action: str):
    """User answered (DONE) or dismissed (MISSED): log, stop nagging, advance,
    and honour delete-after-dismissed. Single path shared by UI and engine."""
    reminder = get_reminder(reminder_id)
    if reminder is None:
        return
    add_log(reminder_id, due_at, action)
    if reminder.get("delete_after_dismissed"):
        soft_delete("reminders", reminder_id)
        return
    advance_after_fire(reminder)


def nagging_now():
    """Reminders mid-nag: fired once, unanswered, nag interval set."""
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM reminders WHERE deleted_at IS NULL AND enabled = 1 "
            "AND nag_started_at IS NOT NULL AND nag_interval_minutes > 0").fetchall()]


def set_nag_started(reminder_id: str, at: int):
    with db.connect() as conn:
        conn.execute("UPDATE reminders SET nag_started_at = ? WHERE id = ?", (at, reminder_id))


def last_fired_at(reminder_id: str):
    with db.connect() as conn:
        row = conn.execute(
            "SELECT MAX(fired_at) m FROM fired WHERE reminder_id = ?", (reminder_id,)).fetchone()
        return row["m"]


def touch_fired(reminder_id: str, due_at: int, quiet: bool = False):
    """Refresh the fire timestamp for a nag re-alert so pollers re-announce it."""
    with db.connect() as conn:
        cur = conn.execute("UPDATE fired SET fired_at = ?, quiet = ? WHERE reminder_id = ? AND due_at = ?",
                           (db.now_millis(), 1 if quiet else 0, reminder_id, due_at))
        if cur.rowcount == 0:
            # No row for this occurrence (e.g. due_at moved underneath a
            # nag cycle): insert instead, so last_fired_at still advances —
            # otherwise the nag interval test would pass on every 20-second
            # tick and spam a push each time.
            conn.execute(
                "INSERT OR IGNORE INTO fired (reminder_id, due_at, fired_at, quiet) VALUES (?,?,?,?)",
                (reminder_id, due_at, db.now_millis(), 1 if quiet else 0))


def clear_fired(reminder_id: str):
    """Forget fire records for a reminder whose occurrence moved on (sync
    told us it was answered elsewhere); the next occurrence starts clean."""
    with db.connect() as conn:
        conn.execute("DELETE FROM fired WHERE reminder_id = ?", (reminder_id,))


def due_now():
    """Timed reminders whose fire time has arrived and not yet been handled."""
    now = db.now_millis()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE deleted_at IS NULL AND enabled = 1 "
            "AND COALESCE(snoozed_until, due_at) IS NOT NULL "
            "AND COALESCE(snoozed_until, due_at) <= ?", (now,)).fetchall()
        out = []
        for r in rows:
            fire_at = r["snoozed_until"] or r["due_at"]
            seen = conn.execute(
                "SELECT 1 FROM fired WHERE reminder_id = ? AND due_at = ?",
                (r["id"], fire_at)).fetchone()
            if not seen:
                out.append(dict(r))
        return out


def mark_fired(reminder_id: str, due_at: int, quiet: bool = False):
    with db.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO fired (reminder_id, due_at, fired_at, quiet) VALUES (?,?,?,?)",
            (reminder_id, due_at, db.now_millis(), 1 if quiet else 0))


def changed_since(since: int):
    with db.connect() as conn:
        return {
            "reminders": [dict(r) for r in conn.execute(
                "SELECT * FROM reminders WHERE updated_at > ?", (since,)).fetchall()],
            "logs": [dict(r) for r in conn.execute(
                "SELECT * FROM completion_log WHERE at > ?", (since,)).fetchall()],
        }
