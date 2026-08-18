"""Mirror of the Android ReminderOrderingTest: a repeating reminder whose
fire time has passed should sort by its next occurrence, not the stale
past time still in due_at until it's answered or nag-timed-out."""
import unittest
from datetime import datetime

from app.store import next_alert_millis


def ms(y, m, d, h, mi):
    return int(datetime(y, m, d, h, mi).astimezone().timestamp() * 1000)


class NextAlertMillisTest(unittest.TestCase):
    def test_future_due_time_sorts_by_itself(self):
        due = ms(2026, 8, 19, 9, 0)
        now = ms(2026, 8, 18, 10, 0)
        self.assertEqual(due, next_alert_millis({"due_at": due, "repeat_rule": "DAILY",
                                                   "snoozed_until": None}, now))

    def test_past_due_repeating_reminder_rolls_forward(self):
        due = ms(2026, 8, 18, 9, 0)
        now = ms(2026, 8, 18, 10, 0)
        expected = ms(2026, 8, 19, 9, 0)
        self.assertEqual(expected, next_alert_millis({"due_at": due, "repeat_rule": "DAILY",
                                                        "snoozed_until": None}, now))

    def test_still_mid_nag_past_due_rolls_forward_for_sorting(self):
        due = ms(2026, 8, 18, 9, 0)
        now = ms(2026, 8, 18, 9, 45)
        expected = ms(2026, 8, 19, 9, 0)
        self.assertEqual(expected, next_alert_millis({"due_at": due, "repeat_rule": "DAILY",
                                                        "snoozed_until": None}, now))

    def test_past_due_one_off_keeps_raw_time(self):
        due = ms(2026, 8, 18, 9, 0)
        now = ms(2026, 8, 18, 10, 0)
        self.assertEqual(due, next_alert_millis({"due_at": due, "repeat_rule": "",
                                                   "snoozed_until": None}, now))

    def test_snoozed_time_takes_priority(self):
        due = ms(2026, 8, 18, 9, 0)
        snoozed = ms(2026, 8, 18, 9, 10)
        now = ms(2026, 8, 18, 9, 5)
        self.assertEqual(snoozed, next_alert_millis({"due_at": due, "repeat_rule": "DAILY",
                                                       "snoozed_until": snoozed}, now))

    def test_no_due_date_sorts_none(self):
        self.assertIsNone(next_alert_millis({"due_at": None, "repeat_rule": "",
                                              "snoozed_until": None}, ms(2026, 8, 18, 10, 0)))


if __name__ == "__main__":
    unittest.main()
