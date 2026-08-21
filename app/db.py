"""SQLite storage. One database file, one schema, shared by web UI and sync API.

Every row carries updated_at (epoch millis) and deleted_at (tombstone) so the
sync protocol can merge newest-wins with Android and never resurrect deletions.
"""
import contextlib
import os
import sqlite3
import time
import uuid

def db_path():
    # Resolved on every connect, not at import, so tests and deployments can
    # point CHKT_DB anywhere before or after this module loads.
    return os.environ.get("CHKT_DB", os.path.join(os.path.dirname(__file__), "..", "data", "chkt.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    tags TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    due_at INTEGER,
    duration_minutes INTEGER NOT NULL DEFAULT 0,
    repeat_rule TEXT NOT NULL DEFAULT '',
    alert_mode TEXT NOT NULL DEFAULT 'NOTIFY_AND_SPEAK',
    pre_tone INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    vibrate INTEGER NOT NULL DEFAULT 1,
    respect_dnd INTEGER NOT NULL DEFAULT 0,
    nag_interval_minutes INTEGER NOT NULL DEFAULT 0,
    nag_stop_after_minutes INTEGER NOT NULL DEFAULT 60,
    nag_started_at INTEGER,
    delete_after_dismissed INTEGER NOT NULL DEFAULT 0,
    snoozed_until INTEGER,
    location_trigger TEXT NOT NULL DEFAULT 'NONE',
    latitude REAL,
    longitude REAL,
    radius_metres REAL NOT NULL DEFAULT 150,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_at);
CREATE TABLE IF NOT EXISTS completion_log (
    id TEXT PRIMARY KEY,
    reminder_id TEXT NOT NULL,
    due_at INTEGER NOT NULL,
    action TEXT NOT NULL,
    at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_log_at ON completion_log(at);
CREATE TABLE IF NOT EXISTS auth (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    -- Never written: the live TOTP seed is Fernet-encrypted in `settings`
    -- (settings_store.SECRET_KEYS). Kept only because dropping a column is
    -- a table rebuild on old SQLite for zero behaviour change.
    totp_secret TEXT,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS access_keys (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    last_used_at INTEGER
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value BLOB NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id TEXT PRIMARY KEY,
    subscription_json TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS fired (
    reminder_id TEXT NOT NULL,
    due_at INTEGER NOT NULL,
    fired_at INTEGER NOT NULL,
    quiet INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (reminder_id, due_at)
);
"""

# Additive migrations for databases created before a column existed. Each is
# safe to re-run: SQLite rejects a duplicate column and we just ignore that.
MIGRATIONS = [
    "ALTER TABLE fired ADD COLUMN quiet INTEGER NOT NULL DEFAULT 0",
    # Ringing was removed as an alert component; rewrite rows saved under
    # the old three-way scheme onto their closest new equivalent. Plain
    # UPDATEs, safe to re-run: nothing matches after the first pass.
    "UPDATE reminders SET alert_mode = 'NOTIFY_AND_SPEAK' WHERE alert_mode = 'RING_AND_SPEAK'",
    "UPDATE reminders SET alert_mode = 'NOTIFY_ONLY' WHERE alert_mode = 'RING_ONLY'",
    # Reminders gained a length so they can be published to a calendar as a
    # block rather than a moment. 0 — every existing reminder — is a moment.
    "ALTER TABLE reminders ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 0",
    # Tags became lowercase-only, so "Cal" and "cal" stop being two tags that
    # read identically. Touch updated_at on the rows that actually change, so
    # phones pull the tidied version instead of pushing the old one back.
    "UPDATE reminders SET tags = lower(tags), updated_at = CAST(strftime('%s','now') AS INTEGER) * 1000 "
    "WHERE tags <> lower(tags)",
]


def now_millis():
    return int(time.time() * 1000)


def new_id():
    return str(uuid.uuid4())


@contextlib.contextmanager
def connect():
    """Yields a connection that commits on success, rolls back on error, and
    always closes, `with sqlite3.connect(...)` alone never closes."""
    path = db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        for statement in MIGRATIONS:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass  # already applied
