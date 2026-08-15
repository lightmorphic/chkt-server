"""Quiet hours: same overnight-span logic as the app's QuietHours.contains."""
import datetime
import os
import tempfile
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
_tmp = tempfile.mkdtemp(prefix="chkt-test-")
os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")

from app import db  # noqa: E402
from app.settings_store import quiet_hours, quiet_hours_now, set_quiet_hours  # noqa: E402


class QuietHoursTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_disabled_is_never_quiet(self):
        set_quiet_hours(enabled=False, start="22:00", end="07:00")
        self.assertFalse(quiet_hours_now(datetime.datetime(2026, 1, 1, 23, 30)))

    def test_overnight_span_inside_window(self):
        set_quiet_hours(enabled=True, start="22:00", end="07:00")
        self.assertTrue(quiet_hours_now(datetime.datetime(2026, 1, 1, 23, 30)))
        self.assertTrue(quiet_hours_now(datetime.datetime(2026, 1, 1, 6, 0)))

    def test_overnight_span_outside_window(self):
        set_quiet_hours(enabled=True, start="22:00", end="07:00")
        self.assertFalse(quiet_hours_now(datetime.datetime(2026, 1, 1, 12, 0)))

    def test_same_day_span(self):
        set_quiet_hours(enabled=True, start="13:00", end="14:00")
        self.assertTrue(quiet_hours_now(datetime.datetime(2026, 1, 1, 13, 30)))
        self.assertFalse(quiet_hours_now(datetime.datetime(2026, 1, 1, 15, 0)))

    def test_boundaries_are_start_inclusive_end_exclusive(self):
        set_quiet_hours(enabled=True, start="13:00", end="14:00")
        self.assertTrue(quiet_hours_now(datetime.datetime(2026, 1, 1, 13, 0)))
        self.assertFalse(quiet_hours_now(datetime.datetime(2026, 1, 1, 14, 0)))

    def test_round_trip(self):
        set_quiet_hours(enabled=True, start="21:15", end="06:45")
        self.assertEqual(quiet_hours(), {"enabled": True, "start": "21:15", "end": "06:45"})


if __name__ == "__main__":
    unittest.main()
