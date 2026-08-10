"""Reminder data operations — the single write path for both the web UI and
the sync API, so nothing can drift.
"""
from datetime import datetime

from . import db
from .repeat_rules import next_after

LIST_FIELDS = ("id", "name", "position", "updated_at", "deleted_at")
REMINDER_FIELDS = (
    "id", "list_id", "title", "notes", "due_at", "repeat_rule", "alert_mode",
    "pre_tone", "enabled", "snoozed_until", "location_trigger", "latitude",
    "longitude", "radius_metres", "created_at", "updated_at", "deleted_at",
)


def lists(include_deleted=False):
    q = "SELECT * FROM lists" + ("" if include_deleted else " WHERE deleted_at IS NULL") + " ORDER BY position, name"
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(q).fetchall()]


def reminders_for(list_id):
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM reminders WHERE list_id = ? AND deleted_at IS NULL "
            "ORDER BY due_at IS NULL, due_at", (list_id,)).fetchall()]


def get_reminder(reminder_id):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return dict(row) if row else None


def upsert_list(record: dict):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO lists (id, name, position, updated_at, deleted_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, position=excluded.position, "
            "updated_at=excluded.updated_at, deleted_at=excluded.deleted_at",
            tuple(record.get(f) for f in LIST_FIELDS),
        )


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
    assert table in ("lists", "reminders")
    now = db.now_millis()
    with db.connect() as conn:
        conn.execute(f"UPDATE {table} SET deleted_at = ?, updated_at = ? WHERE id = ?",
                     (now, now, record_id))
        if table == "lists":
            conn.execute(
                "UPDATE reminders SET deleted_at = ?, updated_at = ? WHERE list_id = ? AND deleted_at IS NULL",
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
    updated["updated_at"] = now
    if nxt is not None:
        updated["due_at"] = int(nxt.timestamp() * 1000)
    elif reminder.get("location_trigger", "NONE") == "NONE":
        updated["enabled"] = 0
    upsert_reminder(updated)
    return updated


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


def mark_fired(reminder_id: str, due_at: int):
    with db.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO fired (reminder_id, due_at, fired_at) VALUES (?,?,?)",
                     (reminder_id, due_at, db.now_millis()))


def changed_since(since: int):
    with db.connect() as conn:
        return {
            "lists": [dict(r) for r in conn.execute(
                "SELECT * FROM lists WHERE updated_at > ?", (since,)).fetchall()],
            "reminders": [dict(r) for r in conn.execute(
                "SELECT * FROM reminders WHERE updated_at > ?", (since,)).fetchall()],
            "logs": [dict(r) for r in conn.execute(
                "SELECT * FROM completion_log WHERE at > ?", (since,)).fetchall()],
        }
