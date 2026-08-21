"""The History page: spent one-offs leave the main list, show up in
history, and reopening one pre-arms it for reuse."""
import os
import re
import tempfile
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
_tmp = tempfile.mkdtemp(prefix="chkt-test-")
os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
os.environ["CHKT_BACKUP_DIR"] = os.path.join(_tmp, "backups")
os.environ["CHKT_INSECURE_COOKIES"] = "1"

from app import create_app  # noqa: E402  (env must be set first)
from app import db, store  # noqa: E402


def _reminder(rid, title, enabled, repeat_rule="", location_trigger="NONE", due_at=1_700_000_000_000):
    now = db.now_millis()
    return {
        "id": rid, "tags": "", "title": title, "notes": "", "due_at": due_at,
        "duration_minutes": 0,
        "repeat_rule": repeat_rule, "alert_mode": "NOTIFY_AND_SPEAK", "pre_tone": 0,
        "enabled": 1 if enabled else 0, "vibrate": 1, "respect_dnd": 0,
        "nag_interval_minutes": 0, "nag_stop_after_minutes": 60, "nag_started_at": None,
        "delete_after_dismissed": 0, "snoozed_until": None,
        "location_trigger": location_trigger, "latitude": None, "longitude": None,
        "radius_metres": 150.0, "created_at": now, "updated_at": now, "deleted_at": None,
    }


class HistoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
        os.environ["CHKT_BACKUP_DIR"] = os.path.join(_tmp, "backups")
        cls.app = create_app()
        cls.client = cls.app.test_client()
        setup_html = cls.client.get("/setup").get_data(as_text=True)
        csrf = re.search(r'name="csrf" value="([^"]+)"', setup_html).group(1)
        cls.client.post("/setup", data={
            "csrf": csrf, "username": "devtest",
            "password": "local-dev-smoke-test-1", "confirm": "local-dev-smoke-test-1",
        })
        store.upsert_reminder(_reminder("spent", "Collect parcel", enabled=False))
        store.upsert_reminder(_reminder("live", "Water plants", enabled=True))
        store.upsert_reminder(_reminder("paused-daily", "Stretch", enabled=False, repeat_rule="DAILY"))

    def test_predicate(self):
        self.assertTrue(store.is_ended(_reminder("x", "t", enabled=False)))
        # Switched-off repeating and location reminders have ended too.
        self.assertTrue(store.is_ended(_reminder("x", "t", enabled=False, repeat_rule="DAILY")))
        self.assertTrue(store.is_ended(_reminder("x", "t", enabled=False, location_trigger="ARRIVE")))
        self.assertFalse(store.is_ended(_reminder("x", "t", enabled=True)))
        self.assertFalse(store.is_ended(_reminder("x", "t", enabled=True, repeat_rule="DAILY")))

    def test_main_list_hides_ended_history_shows_them(self):
        home = self.client.get("/").get_data(as_text=True)
        history = self.client.get("/history").get_data(as_text=True)
        self.assertNotIn("Collect parcel", home)
        self.assertNotIn("Stretch", home)  # switched-off repeat is history too
        self.assertIn("Water plants", home)
        self.assertIn("Collect parcel", history)
        self.assertIn("Stretch", history)
        self.assertNotIn("Water plants", history)

    def test_reuse_prearms_the_edit_form(self):
        html = self.client.get("/reminder/spent/edit").get_data(as_text=True)
        # Active comes ticked, and the stale date is rolled forward.
        self.assertRegex(html, r'name="active" checked')
        from datetime import datetime
        self.assertIn(datetime.now().strftime("%Y-%m-%d"), html)
