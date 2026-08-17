"""Python twin of the Android RepeatRule engine, same string format, same
next-occurrence behaviour, so a reminder repeats identically wherever it lives.

Formats: "" | "DAILY" | "WEEKLY:MON,THU" | "MONTHLY:15" | "MONTHLY:LAST"
         | "YEARLY:08-10" | "EVERY:90m|12h|3d|2w" | "EVERY:3y"
"""
import calendar
import re
from datetime import datetime, timedelta

_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def next_after(rule: str, previous: datetime, after: datetime):
    """Next occurrence strictly after `after`, keeping previous's time of day.
    Returns None for one-off (empty) or unparseable rules."""
    rule = (rule or "").strip()
    if not rule:
        return None
    kind, _, arg = rule.partition(":")

    if kind == "DAILY":
        candidate = after.replace(hour=previous.hour, minute=previous.minute, second=0, microsecond=0)
        if candidate <= after:
            candidate += timedelta(days=1)
        return candidate

    if kind == "WEEKLY":
        wanted = {d.strip().upper()[:3] for d in arg.split(",") if d.strip()}
        wanted = {d for d in wanted if d in _DAYS}
        if not wanted:
            return None
        candidate = after.replace(hour=previous.hour, minute=previous.minute, second=0, microsecond=0)
        if candidate <= after:
            candidate += timedelta(days=1)
        for _ in range(8):
            if _DAYS[candidate.weekday()] in wanted:
                return candidate
            candidate += timedelta(days=1)
        return None

    if kind == "MONTHLY":
        last = arg.strip().upper() == "LAST"
        day = 31 if last else _int_or_none(arg)
        if day is None or not 1 <= day <= 31:
            return None
        year, month = after.year, after.month
        for _ in range(13):
            month_len = calendar.monthrange(year, month)[1]
            actual = month_len if last else min(day, month_len)
            candidate = datetime(year, month, actual, previous.hour, previous.minute, tzinfo=after.tzinfo)
            if candidate > after:
                return candidate
            month += 1
            if month > 12:
                month = 1
                year += 1
        return None

    if kind == "YEARLY":
        m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", arg.strip())
        if not m:
            return None
        month, day = int(m.group(1)), int(m.group(2))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        year = after.year
        for _ in range(2):
            month_len = calendar.monthrange(year, month)[1]
            candidate = datetime(year, month, min(day, month_len),
                                 previous.hour, previous.minute, tzinfo=after.tzinfo)
            if candidate > after:
                return candidate
            year += 1
        return None

    if kind == "EVERY":
        years_match = re.fullmatch(r"(\d+)y", arg.strip())
        if years_match:
            n = int(years_match.group(1))
            if n <= 0:
                return None
            candidate = previous
            while candidate <= after:
                candidate = _add_years(candidate, n)
            return candidate

        m = re.fullmatch(r"(\d+)([mhdw])", arg.strip())
        if not m:
            return None
        n = int(m.group(1))
        if n <= 0:
            return None
        step = {"m": timedelta(minutes=n), "h": timedelta(hours=n),
                "d": timedelta(days=n), "w": timedelta(weeks=n)}[m.group(2)]
        candidate = previous
        while candidate <= after:
            candidate += step
        return candidate

    return None


def _add_years(dt: datetime, n: int) -> datetime:
    """Calendar years, not a fixed timedelta, so leap years don't drift it.
    29 Feb clamps to 28 Feb in non-leap years, same as the YEARLY rule."""
    year = dt.year + n
    day = min(dt.day, calendar.monthrange(year, dt.month)[1])
    return dt.replace(year=year, day=day)


def _int_or_none(s):
    try:
        return int(s.strip())
    except (ValueError, AttributeError):
        return None
