"""Follow a calendar CHKT doesn't host: CHKT as the CalDAV *client*.

Exists because hosted calendar services (Fastmail and friends) write to
their OWN calendars instantly but push to an external CalDAV server —
CHKT's — whenever their engine feels like it, sometimes many minutes
later. Following the service's native calendar flips who waits for whom:
you save the event, their server has it that second, and CHKT pulls it on
CHKT's schedule — within a minute.

Followed events become reminders with the can't-miss defaults (notify and
speak, re-alert every 5 minutes for an hour), and the remote stays the
source of truth: edits and deletions there follow here. Local answers
(done, snooze) stick, because they don't change the remote copy's ETag.
"""
import base64
import json
import threading
import time
import urllib.request
from xml.etree import ElementTree as ET

from . import db, ical, store
from .settings_store import get as setting_get, put as setting_put

# Reminders born from a followed calendar carry this id prefix. The CalDAV
# side CHKT serves EXCLUDES them (see caldav._events): republishing them
# would hand the calendar service back copies of its own events.
ID_PREFIX = "fw-"
POLL_SECONDS = 60
_STATE_KEY = "remote_cal_state"

NEW_DEFAULTS = {
    "tags": "calendar",
    "notes": "",
    "duration_minutes": 0,
    "repeat_rule": "",
    "alert_mode": "NOTIFY_AND_SPEAK",
    "nag_interval_minutes": 5,
    "nag_stop_after_minutes": 60,
    "vibrate": 1,
    "respect_dnd": 0,
    "enabled": 1,
    "pre_tone": 0,
    "delete_after_dismissed": 0,
    "location_trigger": "NONE",
    "latitude": None,
    "longitude": None,
    "radius_metres": 150.0,
    "nag_started_at": None,
    "snoozed_until": None,
    "deleted_at": None,
}


def config():
    return {
        "enabled": setting_get("remote_cal_enabled") == "1",
        "url": setting_get("remote_cal_url", "").strip(),
        "username": setting_get("remote_cal_user", "").strip(),
        "password": setting_get("remote_cal_password", ""),
        "status": setting_get("remote_cal_status", "Never checked."),
    }


def _request(url, method, body, username, password, depth=None):
    req = urllib.request.Request(url, data=body.encode() if body else None, method=method)
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    req.add_header("Authorization", "Basic " + token)
    req.add_header("Content-Type", "application/xml; charset=utf-8")
    if depth is not None:
        req.add_header("Depth", str(depth))
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def _reminder_id(href: str) -> str:
    import hashlib
    return ID_PREFIX + hashlib.sha256(href.encode()).hexdigest()[:32]


def fetch_etags(url, username, password):
    """href -> etag for every event in the remote collection."""
    body = ('<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop>'
            "<D:getetag/><D:resourcetype/></D:prop></D:propfind>")
    raw = _request(url, "PROPFIND", body, username, password, depth=1)
    etags = {}
    for response in ET.fromstring(raw).findall("{DAV:}response"):
        href_el = response.find("{DAV:}href")
        if href_el is None or not href_el.text:
            continue
        href = href_el.text.strip()
        # The collection itself also answers; events are the .ics members.
        if not href.endswith(".ics"):
            continue
        for propstat in response.findall("{DAV:}propstat"):
            etag = propstat.find("{DAV:}prop/{DAV:}getetag")
            if etag is not None and etag.text:
                etags[href] = etag.text.strip()
    return etags


def fetch_event(base_url, href, username, password) -> str:
    from urllib.parse import urljoin
    return _request(urljoin(base_url, href), "GET", None, username, password).decode("utf-8", "replace")


def _import_one(href, ics_text, all_day_hour):
    fields = ical.ics_to_fields(ics_text, all_day_hour)
    if not fields.get("title") or not fields.get("due_at"):
        return None  # Not something CHKT could ever fire.
    # A one-off already over when first seen must not alert NOW about last
    # week; repeats are fine, their rule rolls forward.
    over_by = db.now_millis() - (fields["due_at"] + fields.get("duration_minutes", 0) * 60_000)
    if not fields.get("repeat_rule") and over_by > 0:
        return None

    rid = _reminder_id(href)
    now = db.now_millis()
    existing = store.get_reminder(rid)
    record = dict(existing) if existing and not existing.get("deleted_at") else dict(
        NEW_DEFAULTS, id=rid, created_at=now)
    for key in ("title", "notes", "due_at", "duration_minutes", "repeat_rule"):
        if key in fields:
            record[key] = fields[key]
    record["deleted_at"] = None
    record["updated_at"] = now
    store.upsert_reminder(record)
    return rid


def sync_once() -> str:
    """One pass against the followed calendar; returns a status sentence."""
    cfg = config()
    if not (cfg["enabled"] and cfg["url"] and cfg["password"]):
        return "Not configured."
    try:
        remote = fetch_etags(cfg["url"], cfg["username"], cfg["password"])
    except Exception as e:
        return f"Couldn't reach the calendar: {e.__class__.__name__}."

    raw_state = setting_get(_STATE_KEY, "") or "{}"
    try:
        state = json.loads(raw_state)
    except ValueError:
        state = {}

    added = changed = removed = 0
    all_day_hour = _all_day_hour()
    for href, etag in remote.items():
        known = state.get(href)
        if known and known.get("etag") == etag:
            continue
        try:
            ics_text = fetch_event(cfg["url"], href, cfg["username"], cfg["password"])
        except Exception:
            continue  # One bad event mustn't stall the rest; retried next pass.
        rid = _import_one(href, ics_text, all_day_hour)
        state[href] = {"etag": etag, "rid": rid}
        if rid:
            changed += 1 if known else 0
            added += 0 if known else 1

    for href in list(state.keys()):
        if href not in remote:
            rid = (state.pop(href) or {}).get("rid")
            if rid and store.get_reminder(rid):
                store.soft_delete("reminders", rid)
                removed += 1

    setting_put(_STATE_KEY, json.dumps(state))
    when = time.strftime("%H:%M")
    return f"Checked {when}: {added} new, {changed} updated, {removed} removed."


def _all_day_hour() -> int:
    raw = setting_get("calendar_all_day_hour", "9").strip()
    return int(raw) if raw.isdigit() and 0 <= int(raw) <= 23 else 9


_started = False


def _loop():
    while True:
        try:
            status = sync_once()
            if status != "Not configured.":
                setting_put("remote_cal_status", status)
        except Exception:
            pass  # The next minute gets another chance.
        time.sleep(POLL_SECONDS)


def start_follower():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="chkt-remote-cal").start()
