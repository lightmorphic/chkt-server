"""End-to-end sync API tests against a temporary database: auth, push/pull,
newest-wins merge, tombstones, and append-only logs."""
import json
import os
import tempfile
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
_tmp = tempfile.mkdtemp(prefix="chkt-test-")
os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
os.environ["CHKT_BACKUP_DIR"] = os.path.join(_tmp, "backups")
os.environ["CHKT_INSECURE_COOKIES"] = "1"

from app import create_app  # noqa: E402  (env must be set first)
from app import db, store  # noqa: E402
from app.auth import new_access_key  # noqa: E402


def reminder_json(rid, list_id, title, updated_at, **kw):
    base = {
        "id": rid, "listId": list_id, "title": title, "notes": "",
        "dueAt": 1900000000000, "repeatRule": "", "alertMode": "RING_AND_SPEAK",
        "preTone": False, "enabled": True, "snoozedUntil": None,
        "vibrate": True, "respectDnd": False, "nagIntervalMinutes": 0,
        "nagStopAfterMinutes": 60, "deleteAfterDismissed": False,
        "locationTrigger": "NONE", "latitude": None, "longitude": None,
        "radiusMetres": 150.0, "createdAt": updated_at, "updatedAt": updated_at,
        "deletedAt": None,
    }
    base.update(kw)
    return base


class SyncApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.key = new_access_key("test device")

    def _sync(self, body, key=None):
        return self.client.post(
            "/api/sync", data=json.dumps(body),
            headers={"Authorization": "Bearer " + (key or self.key),
                     "Content-Type": "application/json"})

    def test_01_ping_requires_key(self):
        self.assertEqual(401, self.client.get("/api/ping").status_code)
        self.assertEqual(401, self.client.get(
            "/api/ping", headers={"Authorization": "Bearer wrong"}).status_code)
        r = self.client.get("/api/ping", headers={"Authorization": "Bearer " + self.key})
        self.assertEqual(200, r.status_code)
        self.assertTrue(r.get_json()["ok"])

    def test_02_push_then_pull(self):
        r = self._sync({
            "since": 0,
            "lists": [{"id": "L1", "name": "Test list", "position": 0,
                       "updatedAt": 1000, "deletedAt": None}],
            "reminders": [reminder_json("R1", "L1", "Feed the cat", 1000)],
            "logs": [],
        })
        self.assertEqual(200, r.status_code)
        # A second device syncing from zero receives the records.
        r2 = self._sync({"since": 0, "lists": [], "reminders": [], "logs": []})
        data = r2.get_json()
        self.assertIn("R1", [x["id"] for x in data["reminders"]])
        self.assertIn("L1", [x["id"] for x in data["lists"]])

    def test_03_newest_wins(self):
        # An older edit must not overwrite a newer one.
        self._sync({"since": 0, "lists": [],
                    "reminders": [reminder_json("R1", "L1", "Feed the cat TWICE", 2000)],
                    "logs": []})
        self._sync({"since": 0, "lists": [],
                    "reminders": [reminder_json("R1", "L1", "stale title", 1500)],
                    "logs": []})
        self.assertEqual("Feed the cat TWICE", store.get_reminder("R1")["title"])

    def test_04_tombstone_wins_and_stays(self):
        self._sync({"since": 0, "lists": [],
                    "reminders": [reminder_json("R1", "L1", "Feed the cat TWICE", 3000,
                                                deletedAt=3000)],
                    "logs": []})
        self.assertIsNotNone(store.get_reminder("R1")["deleted_at"])
        # The tombstone flows back out to other devices.
        r = self._sync({"since": 2500, "lists": [], "reminders": [], "logs": []})
        rec = [x for x in r.get_json()["reminders"] if x["id"] == "R1"][0]
        self.assertIsNotNone(rec["deletedAt"])

    def test_05_logs_append_only(self):
        self._sync({"since": 0, "lists": [], "reminders": [],
                    "logs": [{"id": "G1", "reminderId": "R1", "dueAt": 1,
                              "action": "DONE", "at": 5000}]})
        # Duplicate ids are ignored, not duplicated.
        self._sync({"since": 0, "lists": [], "reminders": [],
                    "logs": [{"id": "G1", "reminderId": "R1", "dueAt": 1,
                              "action": "DONE", "at": 5000}]})
        with db.connect() as conn:
            n = conn.execute("SELECT COUNT(*) c FROM completion_log WHERE id='G1'").fetchone()["c"]
        self.assertEqual(1, n)

    def test_06_malformed_records_skipped(self):
        r = self._sync({"since": 0, "lists": [{"bad": "record"}],
                        "reminders": [{"id": "X"}], "logs": [{"nope": 1}]})
        self.assertEqual(200, r.status_code)
        self.assertIsNone(store.get_reminder("X"))

    def test_07_healthz_open_but_harmless(self):
        r = self.client.get("/healthz")
        self.assertEqual(200, r.status_code)

    def test_08_nag_fields_round_trip(self):
        self._sync({"since": 0, "lists": [], "logs": [],
                    "reminders": [reminder_json("R2", "L1", "Nagging one", 6000,
                                                nagIntervalMinutes=5, nagStopAfterMinutes=30,
                                                vibrate=False, respectDnd=True,
                                                deleteAfterDismissed=True)]})
        r = self._sync({"since": 5500, "lists": [], "reminders": [], "logs": []})
        rec = [x for x in r.get_json()["reminders"] if x["id"] == "R2"][0]
        self.assertEqual(5, rec["nagIntervalMinutes"])
        self.assertEqual(30, rec["nagStopAfterMinutes"])
        self.assertFalse(rec["vibrate"])
        self.assertTrue(rec["respectDnd"])
        self.assertTrue(rec["deleteAfterDismissed"])

    def test_09_acknowledge_deletes_when_asked(self):
        from app import store
        store.acknowledge("R2", 1, "DONE")
        self.assertIsNotNone(store.get_reminder("R2")["deleted_at"])

    def test_08_web_requires_login(self):
        r = self.client.get("/", follow_redirects=False)
        self.assertEqual(302, r.status_code)
        self.assertIn("/setup", r.headers["Location"])


if __name__ == "__main__":
    unittest.main()
