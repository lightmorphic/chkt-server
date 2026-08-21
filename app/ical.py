"""iCalendar (RFC 5545) for the narrow slice CHKT needs: one VEVENT per
reminder, in and out.

Times are written as FLOATING local time — no Z, no TZID. That is deliberate:
CHKT's repeat engine keeps the wall-clock time of day across a daylight-saving
change (a 09:00 daily reminder stays 09:00), and floating time is the
iCalendar value type with exactly those semantics. Anchoring to UTC instead
would show the right time in summer and an hour out in winter.

Reading is more forgiving than writing: UTC (trailing Z), a TZID a calendar
app supplied, floating, and all-day DATE values are all accepted, because
those come from whatever client the user happens to like.
"""
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PRODID = "-//Lightmorphic//CHKT//EN"

_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
_ICAL_DAYS = {"MON": "MO", "TUE": "TU", "WED": "WE", "THU": "TH",
              "FRI": "FR", "SAT": "SA", "SUN": "SU"}
_FROM_ICAL_DAYS = {v: k for k, v in _ICAL_DAYS.items()}
_EVERY_FREQ = {"m": "MINUTELY", "h": "HOURLY", "d": "DAILY", "w": "WEEKLY", "y": "YEARLY"}


# ---- text escaping and line folding ----

def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", r"\;")
                .replace(",", r"\,").replace("\r\n", r"\n")
                .replace("\n", r"\n").replace("\r", r"\n"))


def _unescape(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            out.append("\n" if nxt in "nN" else nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _fold(line: str) -> str:
    """Content lines are folded at 75 octets, continuations starting with a
    space. Folding counts bytes, not characters, or a multi-byte character
    can be split down the middle."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks, start = [], 0
    while start < len(raw):
        end = min(start + (75 if not chunks else 74), len(raw))
        # Never cut mid-character: back off to a UTF-8 boundary.
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(raw[start:end].decode("utf-8"))
        start = end
    return "\r\n ".join(chunks)


def _unfold(text: str) -> list:
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return [line for line in lines if line.strip()]


def _split_line(line: str):
    """'DTSTART;VALUE=DATE:20260821' -> ('DTSTART', {'VALUE': 'DATE'}, '20260821')"""
    name_part, _, value = line.partition(":")
    pieces = name_part.split(";")
    name = pieces[0].strip().upper()
    params = {}
    for piece in pieces[1:]:
        key, _, val = piece.partition("=")
        params[key.strip().upper()] = val.strip().strip('"')
    return name, params, value


# ---- time ----

def _local(millis: int) -> datetime:
    return datetime.fromtimestamp(millis / 1000)


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _utc_stamp(millis: int) -> str:
    return datetime.fromtimestamp(millis / 1000, timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_time(value: str, params: dict, all_day_hour: int):
    """Returns (epoch_millis, was_all_day). All-day events have no time of
    day, so they land on the hour the user chose for them."""
    value = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        parsed = datetime.strptime(value[:8], "%Y%m%d")
        parsed = parsed.replace(hour=all_day_hour)
        return int(parsed.timestamp() * 1000), True

    match = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", value)
    if not match:
        return None, False
    stamp = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
    if match.group(3) == "Z":
        stamp = stamp.replace(tzinfo=timezone.utc)
    elif "TZID" in params:
        try:
            stamp = stamp.replace(tzinfo=ZoneInfo(params["TZID"]))
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            pass  # Unknown zone: treat as local, the best guess available.
    return int(stamp.timestamp() * 1000), False


def _parse_duration(value: str):
    """PT1H30M / PT45M / P1D -> minutes. Anything else, or a negative
    duration, is a point in time."""
    match = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?",
                         value.strip().upper())
    if not match:
        return 0
    weeks, days, hours, minutes, seconds = (int(g or 0) for g in match.groups())
    total = weeks * 7 * 24 * 60 + days * 24 * 60 + hours * 60 + minutes + seconds // 60
    return max(0, total)


# ---- repeat rules <-> RRULE ----

def rrule_from_repeat(rule: str, due_at) -> str:
    """CHKT's repeat string as an RRULE. Empty for one-offs and anything
    that doesn't map."""
    rule = (rule or "").strip()
    if not rule:
        return ""
    kind, _, arg = rule.partition(":")

    if kind == "DAILY":
        return "FREQ=DAILY"
    if kind == "WEEKLY":
        days = [_ICAL_DAYS[d.strip().upper()[:3]] for d in arg.split(",")
                if d.strip().upper()[:3] in _ICAL_DAYS]
        return "FREQ=WEEKLY;BYDAY=" + ",".join(days) if days else ""
    if kind == "MONTHLY":
        if arg.strip().upper() == "LAST":
            return "FREQ=MONTHLY;BYMONTHDAY=-1"
        return f"FREQ=MONTHLY;BYMONTHDAY={int(arg)}" if arg.strip().isdigit() else ""
    if kind == "YEARLY":
        match = re.fullmatch(r"(\d{1,2})-(\d{1,2})", arg.strip())
        if match:
            return f"FREQ=YEARLY;BYMONTH={int(match.group(1))};BYMONTHDAY={int(match.group(2))}"
        return "FREQ=YEARLY" if due_at else ""
    if kind == "EVERY":
        match = re.fullmatch(r"(\d+)([mhdwy])", arg.strip().lower())
        if not match:
            return ""
        count, unit = int(match.group(1)), match.group(2)
        return f"FREQ={_EVERY_FREQ[unit]};INTERVAL={count}"
    return ""


def repeat_from_rrule(rrule: str, due_at) -> str:
    """An RRULE as the closest CHKT repeat string. CHKT has no vocabulary
    for the exotic end of RFC 5545 (BYSETPOS, COUNT, UNTIL and friends), so
    those collapse onto the plain repeat and the extra conditions are lost —
    better a reminder that repeats too often than one that never fires."""
    parts = {}
    for piece in (rrule or "").split(";"):
        key, _, value = piece.partition("=")
        if key:
            parts[key.strip().upper()] = value.strip().upper()
    freq = parts.get("FREQ", "")
    if not freq:
        return ""
    try:
        interval = max(1, int(parts.get("INTERVAL", "1")))
    except ValueError:
        interval = 1

    if freq == "MINUTELY":
        return f"EVERY:{interval}m"
    if freq == "HOURLY":
        return f"EVERY:{interval}h"
    if freq == "DAILY":
        return "DAILY" if interval == 1 else f"EVERY:{interval}d"
    if freq == "WEEKLY":
        days = [_FROM_ICAL_DAYS[d[-2:]] for d in parts.get("BYDAY", "").split(",")
                if d[-2:] in _FROM_ICAL_DAYS]
        if days and interval == 1:
            return "WEEKLY:" + ",".join(sorted(days, key=_DAYS.index))
        if interval > 1:
            # A fortnightly Tuesday can't be said in CHKT's grammar; keep the
            # interval, which is the part that governs when it next fires.
            return f"EVERY:{interval}w"
        return "WEEKLY:" + _DAYS[_local(due_at).weekday()] if due_at else ""
    if freq == "MONTHLY":
        if interval > 1:
            return ""  # No monthly interval in CHKT's grammar; treat as one-off.
        day = parts.get("BYMONTHDAY", "")
        if day == "-1":
            return "MONTHLY:LAST"
        if day.isdigit():
            return f"MONTHLY:{int(day)}"
        return f"MONTHLY:{_local(due_at).day}" if due_at else ""
    if freq == "YEARLY":
        if interval > 1:
            return f"EVERY:{interval}y"
        month, day = parts.get("BYMONTH", ""), parts.get("BYMONTHDAY", "")
        if month.isdigit() and day.isdigit():
            return f"YEARLY:{int(month):02d}-{int(day):02d}"
        return f"YEARLY:{_local(due_at):%m-%d}" if due_at else ""
    return ""


# ---- reminder -> VEVENT ----

def reminder_to_ics(reminder: dict) -> str:
    """One reminder as a complete VCALENDAR. Reminders with no due time
    (location-only ones) have nothing to put on a calendar."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{reminder['id']}",
        f"DTSTAMP:{_utc_stamp(reminder.get('updated_at') or reminder.get('created_at') or 0)}",
        f"SUMMARY:{_escape(reminder.get('title') or '')}",
    ]

    due_at = reminder.get("due_at")
    if due_at:
        lines.append(f"DTSTART:{_stamp(_local(due_at))}")
        minutes = int(reminder.get("duration_minutes") or 0)
        # No DTEND at all means zero length (RFC 5545 §3.6.1), which is what
        # a plain reminder is: a moment, not a block.
        if minutes > 0:
            lines.append(f"DTEND:{_stamp(_local(due_at) + timedelta(minutes=minutes))}")

    if reminder.get("notes"):
        lines.append(f"DESCRIPTION:{_escape(reminder['notes'])}")

    tags = [t.strip() for t in (reminder.get("tags") or "").split(",") if t.strip()]
    if tags:
        lines.append("CATEGORIES:" + ",".join(_escape(t) for t in tags))

    rrule = rrule_from_repeat(reminder.get("repeat_rule"), due_at)
    if rrule:
        lines.append(f"RRULE:{rrule}")

    if not reminder.get("enabled", 1):
        lines.append("STATUS:CANCELLED")

    # CHKT's own settings, so a round trip through a calendar app doesn't
    # quietly reset how a reminder alerts. Unknown X- properties are
    # preserved by well-behaved clients and ignored by the rest.
    lines += [
        f"X-CHKT-ALERT-MODE:{reminder.get('alert_mode') or 'NOTIFY_AND_SPEAK'}",
        f"X-CHKT-NAG-INTERVAL:{int(reminder.get('nag_interval_minutes') or 0)}",
        f"X-CHKT-NAG-STOP-AFTER:{int(reminder.get('nag_stop_after_minutes') or 60)}",
        f"X-CHKT-VIBRATE:{1 if reminder.get('vibrate', 1) else 0}",
        f"X-CHKT-RESPECT-DND:{1 if reminder.get('respect_dnd') else 0}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


# ---- VEVENT -> reminder fields ----

def ics_to_fields(text: str, all_day_hour: int = 9) -> dict:
    """The reminder fields carried by the first VEVENT in `text`. Returns {}
    when there is no usable event. Callers layer these onto an existing
    reminder or onto the defaults for a newly-created one."""
    in_event = False
    props = {}
    for line in _unfold(text):
        upper = line.strip().upper()
        if upper == "BEGIN:VEVENT":
            in_event = True
            continue
        if upper == "END:VEVENT":
            break
        if not in_event:
            continue
        name, params, value = _split_line(line)
        props.setdefault(name, (params, value))

    if not props:
        return {}

    fields = {}
    if "UID" in props:
        fields["uid"] = props["UID"][1].strip()
    if "SUMMARY" in props:
        fields["title"] = _unescape(props["SUMMARY"][1]).strip()
    if "DESCRIPTION" in props:
        fields["notes"] = _unescape(props["DESCRIPTION"][1]).strip()
    if "CATEGORIES" in props:
        cats = [_unescape(c).strip() for c in props["CATEGORIES"][1].split(",")]
        fields["tags"] = ", ".join(c for c in cats if c)

    due_at = None
    if "DTSTART" in props:
        params, value = props["DTSTART"]
        due_at, all_day = _parse_time(value, params, all_day_hour)
        if due_at is not None:
            fields["due_at"] = due_at
            fields["all_day"] = all_day

    minutes = 0
    if "DURATION" in props:
        minutes = _parse_duration(props["DURATION"][1])
    elif "DTEND" in props and due_at:
        end_at, end_all_day = _parse_time(props["DTEND"][1], props["DTEND"][0], all_day_hour)
        if end_at and end_at > due_at:
            # An all-day event's DTEND is the day AFTER it finishes, and its
            # length isn't a meaningful block on the reminder anyway.
            minutes = 0 if end_all_day else int((end_at - due_at) / 60000)
    fields["duration_minutes"] = minutes

    if "RRULE" in props:
        fields["repeat_rule"] = repeat_from_rrule(props["RRULE"][1], due_at)

    if "STATUS" in props and props["STATUS"][1].strip().upper() == "CANCELLED":
        fields["enabled"] = 0

    def _int_prop(name):
        raw = props.get(name, ({}, ""))[1].strip()
        return int(raw) if raw.lstrip("-").isdigit() else None

    if "X-CHKT-ALERT-MODE" in props:
        fields["alert_mode"] = props["X-CHKT-ALERT-MODE"][1].strip().upper()
    for prop, field in (("X-CHKT-NAG-INTERVAL", "nag_interval_minutes"),
                        ("X-CHKT-NAG-STOP-AFTER", "nag_stop_after_minutes"),
                        ("X-CHKT-VIBRATE", "vibrate"),
                        ("X-CHKT-RESPECT-DND", "respect_dnd")):
        value = _int_prop(prop)
        if value is not None:
            fields[field] = value
    return fields
