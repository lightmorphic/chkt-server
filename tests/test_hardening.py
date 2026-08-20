"""Regression tests for the 2026-08-20 hardening pass: sync must end a
server-side nag cycle when the phone answered the reminder, and login must
throttle sustained guessing."""
import json
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
from app import auth, db, store  # noqa: E402
from app.auth import new_access_key  # noqa: E402

from test_sync_api import reminder_json  # noqa: E402


class NagSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
        os.environ["CHKT_BACKUP_DIR"] = os.path.join(_tmp, "backups")
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.key = new_access_key("nag test device")

    def _sync(self, body):
        return self.client.post(
            "/api/sync", data=json.dumps(body),
            headers={"Authorization": "Bearer " + self.key,
                     "Content-Type": "application/json"})

    def test_answering_on_the_phone_stops_the_server_nag(self):
        # A nagging reminder is mid-cycle on the server ...
        due = db.now_millis() - 60_000
        self._sync({"since": 0, "reminders": [reminder_json(
            "nag-1", "", "Take the pill", due - 1000,
            dueAt=due, nagIntervalMinutes=2)], "logs": []})
        store.mark_fired("nag-1", due)
        store.set_nag_started("nag-1", db.now_millis())
        self.assertEqual(1, len([r for r in store.nagging_now() if r["id"] == "nag-1"]))

        # ... then the phone answers it: sync arrives with due_at advanced.
        self._sync({"since": 0, "reminders": [reminder_json(
            "nag-1", "", "Take the pill", db.now_millis(),
            dueAt=due + 24 * 3600 * 1000, nagIntervalMinutes=2)], "logs": []})

        # The server's nag cycle for the old occurrence must be over.
        self.assertEqual(0, len([r for r in store.nagging_now() if r["id"] == "nag-1"]))

    def test_unrelated_edit_keeps_a_running_nag(self):
        due = db.now_millis() - 60_000
        self._sync({"since": 0, "reminders": [reminder_json(
            "nag-2", "", "Stretch", due - 1000,
            dueAt=due, nagIntervalMinutes=2)], "logs": []})
        store.mark_fired("nag-2", due)
        store.set_nag_started("nag-2", db.now_millis())

        # A title-only edit (same occurrence) must not kill the nag cycle.
        self._sync({"since": 0, "reminders": [reminder_json(
            "nag-2", "", "Stretch properly", db.now_millis(),
            dueAt=due, nagIntervalMinutes=2)], "logs": []})
        self.assertEqual(1, len([r for r in store.nagging_now() if r["id"] == "nag-2"]))


class LoginThrottleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
        os.environ["CHKT_BACKUP_DIR"] = os.path.join(_tmp, "backups")
        cls.app = create_app()
        client = cls.app.test_client()
        setup_html = client.get("/setup").get_data(as_text=True)
        csrf = re.search(r'name="csrf" value="([^"]+)"', setup_html).group(1)
        client.post("/setup", data={
            "csrf": csrf, "username": "devtest",
            "password": "local-dev-smoke-test-1", "confirm": "local-dev-smoke-test-1",
        })

    def setUp(self):
        auth._failures.clear()
        self.client = self.app.test_client()

    def _login(self, password):
        html = self.client.get("/login").get_data(as_text=True)
        csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        return self.client.post("/login", data={
            "csrf": csrf, "username": "devtest", "password": password,
        }).get_data(as_text=True)

    def test_sixth_wrong_password_is_throttled_not_judged(self):
        for _ in range(5):
            self.assertIn("Wrong username or password", self._login("wrong-wrong-wrong"))
        self.assertIn("Too many attempts", self._login("wrong-wrong-wrong"))
