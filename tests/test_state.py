"""/state: the one number the live-updating reminder list polls."""
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


class StateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
        os.environ["CHKT_BACKUP_DIR"] = os.path.join(_tmp, "backups")
        cls.client = create_app().test_client()
        setup = cls.client.get("/setup").get_data(as_text=True)
        csrf = re.search(r'name="csrf" value="([^"]+)"', setup).group(1)
        cls.client.post("/setup", data={
            "csrf": csrf, "username": "devtest",
            "password": "local-dev-smoke-test-1", "confirm": "local-dev-smoke-test-1"})

    def test_requires_login(self):
        fresh = create_app().test_client()
        self.assertEqual(302, fresh.get("/state").status_code)

    def test_moves_when_a_reminder_changes(self):
        before = self.client.get("/state").get_json()["latest"]
        now = db.now_millis()
        store.upsert_reminder({
            "id": "s1", "tags": "", "title": "T", "notes": "", "due_at": now + 60_000,
            "duration_minutes": 0, "repeat_rule": "", "alert_mode": "NOTIFY_AND_SPEAK",
            "pre_tone": 0, "enabled": 1, "vibrate": 1, "respect_dnd": 0,
            "nag_interval_minutes": 0, "nag_stop_after_minutes": 60, "nag_started_at": None,
            "delete_after_dismissed": 0, "snoozed_until": None, "location_trigger": "NONE",
            "latitude": None, "longitude": None, "radius_metres": 150.0,
            "created_at": now, "updated_at": now, "deleted_at": None})
        after = self.client.get("/state").get_json()["latest"]
        self.assertGreater(after, before)

    def test_deletions_move_it_too(self):
        now = db.now_millis()
        store.upsert_reminder({
            "id": "s2", "tags": "", "title": "Doomed", "notes": "", "due_at": now + 60_000,
            "duration_minutes": 0, "repeat_rule": "", "alert_mode": "NOTIFY_AND_SPEAK",
            "pre_tone": 0, "enabled": 1, "vibrate": 1, "respect_dnd": 0,
            "nag_interval_minutes": 0, "nag_stop_after_minutes": 60, "nag_started_at": None,
            "delete_after_dismissed": 0, "snoozed_until": None, "location_trigger": "NONE",
            "latitude": None, "longitude": None, "radius_metres": 150.0,
            "created_at": now, "updated_at": now, "deleted_at": None})
        before = self.client.get("/state").get_json()["latest"]
        store.soft_delete("reminders", "s2")
        self.assertGreater(self.client.get("/state").get_json()["latest"], before)
