"""Mirror of the Android RepeatRuleTest — same cases, same expected results,
so the two implementations can never quietly disagree."""
import unittest
from datetime import datetime

from app.repeat_rules import next_after


def dt(y, m, d, h, mi):
    return datetime(y, m, d, h, mi).astimezone()


class RepeatRuleTest(unittest.TestCase):
    def test_none_never_repeats(self):
        self.assertIsNone(next_after("", dt(2026, 8, 10, 9, 0), dt(2026, 8, 10, 9, 1)))

    def test_daily_keeps_time_of_day(self):
        self.assertEqual(dt(2026, 8, 11, 9, 0),
                         next_after("DAILY", dt(2026, 8, 10, 9, 0), dt(2026, 8, 10, 9, 0)))

    def test_weekly_next_chosen_weekday(self):
        nxt = next_after("WEEKLY:MON,FRI", dt(2026, 8, 10, 9, 0), dt(2026, 8, 10, 9, 0))
        self.assertEqual(dt(2026, 8, 14, 9, 0), nxt)
        after = next_after("WEEKLY:MON,FRI", dt(2026, 8, 10, 9, 0), nxt)
        self.assertEqual(dt(2026, 8, 17, 9, 0), after)

    def test_monthly_31_clamps(self):
        self.assertEqual(dt(2026, 9, 30, 9, 0),
                         next_after("MONTHLY:31", dt(2026, 8, 31, 9, 0), dt(2026, 8, 31, 9, 0)))

    def test_monthly_last(self):
        self.assertEqual(dt(2026, 2, 28, 8, 0),
                         next_after("MONTHLY:LAST", dt(2026, 1, 31, 8, 0), dt(2026, 1, 31, 8, 0)))

    def test_yearly_feb29(self):
        self.assertEqual(dt(2027, 2, 28, 10, 0),
                         next_after("YEARLY:02-29", dt(2026, 2, 28, 10, 0), dt(2026, 3, 1, 0, 0)))

    def test_every_no_drift(self):
        self.assertEqual(dt(2026, 8, 10, 12, 0),
                         next_after("EVERY:6h", dt(2026, 8, 10, 6, 0), dt(2026, 8, 10, 7, 30)))

    def test_every_catches_up(self):
        self.assertEqual(dt(2026, 8, 11, 9, 0),
                         next_after("EVERY:1d", dt(2026, 8, 1, 9, 0), dt(2026, 8, 10, 10, 0)))

    def test_garbage_is_none(self):
        for raw in ("WEEKLY:", "MONTHLY:99", "YEARLY:13-40", "EVERY:0d", "EVERY:xyz", "BANANA"):
            self.assertIsNone(next_after(raw, dt(2026, 8, 10, 9, 0), dt(2026, 8, 10, 9, 1)), raw)


if __name__ == "__main__":
    unittest.main()
