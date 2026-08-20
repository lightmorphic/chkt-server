"""The Devices page polls /devices/status to show a connecting phone
without a manual refresh; this proves the endpoint actually reflects a
real /api/ping the way the app's Test Connection button makes."""
import os
import re
import tempfile
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
_tmp = tempfile.mkdtemp(prefix="chkt-test-")
os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
os.environ["CHKT_BACKUP_DIR"] = os.path.join(_tmp, "backups")
os.environ["CHKT_INSECURE_COOKIES"] = "1"

from app import create_app  # noqa: E402


class DevicesStatusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # See the matching comment in test_sync_api.py: re-assert this
        # class's own db path here, not just at import time, so the whole
        # suite is order-independent under `discover`.
        os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
        os.environ["CHKT_BACKUP_DIR"] = os.path.join(_tmp, "backups")
        cls.app = create_app()
        cls.client = cls.app.test_client()
        # Create the one account this server supports, the way a browser
        # does: fetch the form for its CSRF token, then submit with it.
        setup_html = cls.client.get("/setup").get_data(as_text=True)
        csrf = re.search(r'name="csrf" value="([^"]+)"', setup_html).group(1)
        cls.client.post("/setup", data={
            "csrf": csrf,
            "username": "devtest", "password": "local-dev-smoke-test-1",
            "confirm": "local-dev-smoke-test-1",
        })

    def _csrf(self):
        html = self.client.get("/devices").get_data(as_text=True)
        return re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    def test_requires_login(self):
        client = self.app.test_client()  # fresh, no session
        r = client.get("/devices/status", follow_redirects=False)
        self.assertEqual(302, r.status_code)

    def test_new_device_starts_with_no_sync(self):
        csrf = self._csrf()
        before_ids = {k["id"] for k in self.client.get("/devices/status").get_json()["keys"]}
        self.client.post("/devices", data={"csrf": csrf, "label": "Test phone"})
        after = self.client.get("/devices/status").get_json()["keys"]
        fresh = [k for k in after if k["id"] not in before_ids]
        self.assertEqual(1, len(fresh))
        self.assertIsNone(fresh[0]["last_used_at"])

    def test_a_real_ping_updates_status_live(self):
        csrf = self._csrf()
        html = self.client.post("/devices", data={"csrf": csrf, "label": "Second phone"},
                                follow_redirects=True).get_data(as_text=True)
        # The fresh key is shown exactly once, right after creation.
        key = re.search(r'user-select:all;word-break:break-all">([^<]+)<', html).group(1)

        before = self.client.get("/devices/status").get_json()
        target = [k for k in before["keys"] if k["last_used_at"] is None]
        self.assertTrue(target, "expected the freshly created key to show no sync yet")

        # Exactly what the app's Test Connection button does.
        ping = self.client.get("/api/ping", headers={"Authorization": "Bearer " + key})
        self.assertEqual(200, ping.status_code)

        after = self.client.get("/devices/status").get_json()
        updated = [k for k in after["keys"] if k["id"] == target[0]["id"]][0]
        self.assertIsNotNone(updated["last_used_at"])


if __name__ == "__main__":
    unittest.main()
