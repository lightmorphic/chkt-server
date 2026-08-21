"""CalDAV: the CHKT calendar, as any calendar app can see it.

Subscribing to this from DAVx5 on a phone or Thunderbird on a desktop puts
every timed reminder in the calendar, and anything added there comes back as
a reminder. It is deliberately a single fixed collection — this is one
person's reminders, not a calendar server — so there is no MKCALENDAR, no
principal discovery beyond the one principal, and no free/busy.

Auth is HTTP Basic with a device access key as the password (any username);
the same keys the phone app uses, created on the Devices page. Basic sends
that key on every request, so this belongs behind HTTPS exactly like the
rest of the server.
"""
import base64
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from flask import Blueprint, Response, request

from . import db, ical, store
from .auth import verify_access_key
from .settings_store import get as setting_get

bp = Blueprint("caldav", __name__)

ROOT_PATH = "/dav/"
PRINCIPAL_PATH = "/dav/principals/me/"
HOME_PATH = "/dav/calendars/me/"
CALENDAR_PATH = "/dav/calendars/me/chkt/"

NS = {
    "DAV:": "D",
    "urn:ietf:params:xml:ns:caldav": "C",
    "http://calendarserver.org/ns/": "CS",
}
DAV_HEADER = "1, 2, 3, calendar-access"
# New events arriving from a calendar app become reminders that behave the
# way the user asked for: spoken as well as shown, and repeated every five
# minutes for an hour until they answer.
NEW_EVENT_DEFAULTS = {
    # Every NOT NULL column belongs here: a calendar app sends an event, not
    # a reminder, so anything it doesn't mention has to come from somewhere.
    "tags": "",
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


# ---- auth ----

def _authed() -> bool:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    _, _, password = decoded.partition(":")
    return bool(password) and verify_access_key(password)


def _unauthorized():
    return Response("Access key required.", 401, {
        "WWW-Authenticate": 'Basic realm="CHKT"',
        "Content-Type": "text/plain; charset=utf-8",
    })


@bp.after_request
def _dav_headers(resp):
    resp.headers.setdefault("DAV", DAV_HEADER)
    return resp


# ---- the calendar's contents ----

def _all_day_hour() -> int:
    """All-day events have no time of day, so they need one. Settable, and
    9am if it has never been set."""
    raw = setting_get("calendar_all_day_hour", "9").strip()
    return int(raw) if raw.isdigit() and 0 <= int(raw) <= 23 else 9


def _events():
    """Reminders that can sit on a calendar: everything with a time. A
    location-only reminder has no moment to draw."""
    return [r for r in store.reminders() if r.get("due_at")]


def _etag(reminder) -> str:
    return '"%d"' % (reminder.get("updated_at") or 0)


def _href(reminder) -> str:
    return CALENDAR_PATH + reminder["id"] + ".ics"


def _sync_token() -> str:
    rows = store.reminders(include_deleted=True)
    latest = max((r.get("updated_at") or 0 for r in rows), default=0)
    return "http://chkt.lightmorphic/ns/sync/%d" % latest


def _token_value(token: str) -> int:
    tail = (token or "").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else 0


# ---- XML plumbing ----

def _prefixed(tag: str) -> str:
    """'{DAV:}getetag' -> 'D:getetag', keeping the namespaces we declare on
    the multistatus root. Anything else is emitted with its own xmlns so a
    client at least gets valid XML back."""
    if not tag.startswith("{"):
        return tag
    uri, _, local = tag[1:].partition("}")
    prefix = NS.get(uri)
    return f"{prefix}:{local}" if prefix else f'{local} xmlns="{uri}"'


def _prop_xml(tag: str, value) -> str:
    name = _prefixed(tag)
    if value is None or value == "":
        # Self-closing: an empty property that exists, e.g. a resourcetype
        # with no sub-types, is different from one that is missing.
        return f"<{name}/>"
    closing = name.split(" ", 1)[0]
    return f"<{name}>{value}</{closing}>"


def _response_xml(href: str, props: dict, requested) -> str:
    """One <response>: the props we know in a 200 propstat, everything else
    the client asked for in a 404 one, which is what RFC 4918 wants and what
    stops fussier clients retrying forever."""
    wanted = list(props.keys()) if requested is None else requested
    found = {tag: props[tag] for tag in wanted if tag in props}
    missing = [tag for tag in wanted if tag not in props]

    parts = [f"<D:response><D:href>{xml_escape(href)}</D:href>"]
    if found or not missing:
        body = "".join(_prop_xml(tag, value) for tag, value in found.items())
        parts.append(f"<D:propstat><D:prop>{body}</D:prop>"
                     "<D:status>HTTP/1.1 200 OK</D:status></D:propstat>")
    if missing:
        body = "".join(f"<{_prefixed(tag)}/>" for tag in missing)
        parts.append(f"<D:propstat><D:prop>{body}</D:prop>"
                     "<D:status>HTTP/1.1 404 Not Found</D:status></D:propstat>")
    parts.append("</D:response>")
    return "".join(parts)


def _multistatus(responses, extra: str = "") -> Response:
    declarations = " ".join(f'xmlns:{prefix}="{uri}"' for uri, prefix in NS.items())
    body = ('<?xml version="1.0" encoding="utf-8"?>'
            f"<D:multistatus {declarations}>" + "".join(responses) + extra + "</D:multistatus>")
    return Response(body, 207, {"Content-Type": "application/xml; charset=utf-8"})


def _requested_props(body: bytes):
    """The prop names asked for, or None for 'everything you have'."""
    if not body or not body.strip():
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    prop = root.find("{DAV:}prop")
    if prop is None:
        return None
    return [child.tag for child in prop]


def _depth() -> str:
    return request.headers.get("Depth", "0").strip()


# ---- property sets per resource ----

_PRIVILEGES = ("<D:privilege><D:read/></D:privilege>"
               "<D:privilege><D:write/></D:privilege>"
               "<D:privilege><D:write-content/></D:privilege>"
               "<D:privilege><D:bind/></D:privilege>"
               "<D:privilege><D:unbind/></D:privilege>")


def _collection_props(kind: str) -> dict:
    props = {
        "{DAV:}resourcetype": "<D:collection/>",
        "{DAV:}current-user-principal": f"<D:href>{PRINCIPAL_PATH}</D:href>",
        "{DAV:}principal-URL": f"<D:href>{PRINCIPAL_PATH}</D:href>",
        "{DAV:}owner": f"<D:href>{PRINCIPAL_PATH}</D:href>",
        "{urn:ietf:params:xml:ns:caldav}calendar-home-set": f"<D:href>{HOME_PATH}</D:href>",
        "{DAV:}current-user-privilege-set": _PRIVILEGES,
    }
    if kind == "principal":
        props["{DAV:}displayname"] = "CHKT"
    elif kind == "home":
        props["{DAV:}displayname"] = "CHKT calendars"
    elif kind == "calendar":
        props.update({
            "{DAV:}resourcetype": "<D:collection/><C:calendar/>",
            "{DAV:}displayname": "CHKT",
            "{DAV:}sync-token": xml_escape(_sync_token()),
            "{DAV:}supported-report-set": (
                "<D:supported-report><D:report><C:calendar-query/></D:report></D:supported-report>"
                "<D:supported-report><D:report><C:calendar-multiget/></D:report></D:supported-report>"
                "<D:supported-report><D:report><D:sync-collection/></D:report></D:supported-report>"),
            "{urn:ietf:params:xml:ns:caldav}supported-calendar-component-set":
                '<C:comp name="VEVENT"/>',
            "{urn:ietf:params:xml:ns:caldav}calendar-description":
                "Reminders from CHKT. Anything added here becomes a reminder.",
            "{http://calendarserver.org/ns/}getctag": xml_escape(_sync_token()),
        })
    return props


def _event_props(reminder: dict, with_data: bool) -> dict:
    props = {
        "{DAV:}resourcetype": None,
        "{DAV:}getetag": _etag(reminder),
        "{DAV:}getcontenttype": "text/calendar; charset=utf-8; component=VEVENT",
    }
    if with_data:
        props["{urn:ietf:params:xml:ns:caldav}calendar-data"] = xml_escape(
            ical.reminder_to_ics(reminder))
    return props


# ---- discovery ----

@bp.route("/.well-known/caldav", methods=["GET", "PROPFIND", "OPTIONS"])
def well_known():
    """Where clients look when handed just the server address."""
    return Response("", 301, {"Location": ROOT_PATH, "DAV": DAV_HEADER})


@bp.route(ROOT_PATH, methods=["OPTIONS", "PROPFIND"])
@bp.route(PRINCIPAL_PATH, methods=["OPTIONS", "PROPFIND"])
@bp.route(HOME_PATH, methods=["OPTIONS", "PROPFIND"])
def collections():
    if request.method == "OPTIONS":
        return _options()
    if not _authed():
        return _unauthorized()

    path = request.path
    kind = {ROOT_PATH: "root", PRINCIPAL_PATH: "principal", HOME_PATH: "home"}[path]
    requested = _requested_props(request.get_data())
    responses = [_response_xml(path, _collection_props(kind), requested)]

    # Depth 1 on the calendar home is how a client finds the calendar itself.
    if kind == "home" and _depth() == "1":
        responses.append(_response_xml(CALENDAR_PATH, _collection_props("calendar"), requested))
    return _multistatus(responses)


def _options():
    return Response("", 200, {
        "DAV": DAV_HEADER,
        "Allow": "OPTIONS, GET, HEAD, PUT, DELETE, PROPFIND, REPORT",
    })


# ---- the calendar collection ----

@bp.route(CALENDAR_PATH, methods=["OPTIONS", "PROPFIND", "REPORT"])
def calendar():
    if request.method == "OPTIONS":
        return _options()
    if not _authed():
        return _unauthorized()
    if request.method == "REPORT":
        return _report()

    requested = _requested_props(request.get_data())
    responses = [_response_xml(CALENDAR_PATH, _collection_props("calendar"), requested)]
    if _depth() != "0":
        responses += [_response_xml(_href(r), _event_props(r, with_data=False), requested)
                      for r in _events()]
    return _multistatus(responses)


def _report():
    body = request.get_data()
    try:
        root = ET.fromstring(body) if body.strip() else None
    except ET.ParseError:
        return Response("Malformed report.", 400)
    if root is None:
        return Response("Empty report.", 400)

    requested = _requested_props(body)
    wants_data = requested is None or \
        "{urn:ietf:params:xml:ns:caldav}calendar-data" in requested

    if root.tag == "{DAV:}sync-collection":
        return _sync_report(root, requested, wants_data)

    if root.tag == "{urn:ietf:params:xml:ns:caldav}calendar-multiget":
        wanted = {href.text.strip() for href in root.findall("{DAV:}href") if href.text}
        by_href = {_href(r): r for r in _events()}
        responses = []
        for href in wanted:
            reminder = by_href.get(href)
            if reminder is None:
                responses.append(f"<D:response><D:href>{xml_escape(href)}</D:href>"
                                 "<D:status>HTTP/1.1 404 Not Found</D:status></D:response>")
            else:
                responses.append(_response_xml(href, _event_props(reminder, wants_data), requested))
        return _multistatus(responses)

    # calendar-query, and anything else we don't recognise: the whole
    # calendar. Filtering to a time range is an optimisation, and one
    # person's reminders are small enough not to need it.
    return _multistatus([_response_xml(_href(r), _event_props(r, wants_data), requested)
                         for r in _events()])


def _sync_report(root, requested, wants_data):
    """Incremental sync: what changed since the client's token. Deletions
    come back as 404 responses, which is how a client learns to drop them."""
    token_el = root.find("{DAV:}sync-token")
    since = _token_value(token_el.text if token_el is not None else "")
    changed = store.changed_since(since)["reminders"]

    responses = []
    for reminder in changed:
        gone = reminder.get("deleted_at") or not reminder.get("due_at")
        if gone:
            responses.append(f"<D:response><D:href>{xml_escape(_href(reminder))}</D:href>"
                             "<D:status>HTTP/1.1 404 Not Found</D:status></D:response>")
        else:
            responses.append(_response_xml(_href(reminder),
                                           _event_props(reminder, wants_data), requested))
    return _multistatus(responses, f"<D:sync-token>{xml_escape(_sync_token())}</D:sync-token>")


# ---- one event ----

@bp.route(CALENDAR_PATH + "<rid>.ics",
          methods=["OPTIONS", "GET", "HEAD", "PUT", "DELETE", "PROPFIND"])
def event(rid):
    if request.method == "OPTIONS":
        return _options()
    if not _authed():
        return _unauthorized()

    reminder = store.get_reminder(rid)
    live = reminder and not reminder.get("deleted_at") and reminder.get("due_at")

    if request.method == "PUT":
        return _put(rid, reminder)

    if request.method == "DELETE":
        if not live:
            return Response("", 404)
        if not _etag_ok(reminder):
            return Response("", 412)
        store.soft_delete("reminders", rid)
        return Response("", 204)

    if not live:
        return Response("", 404)

    if request.method == "PROPFIND":
        return _multistatus([_response_xml(_href(reminder),
                                           _event_props(reminder, with_data=True),
                                           _requested_props(request.get_data()))])

    return Response(ical.reminder_to_ics(reminder), 200, {
        "Content-Type": "text/calendar; charset=utf-8",
        "ETag": _etag(reminder),
    })


def _etag_ok(reminder) -> bool:
    """If-Match guards against overwriting a change the client hasn't seen."""
    header = request.headers.get("If-Match", "").strip()
    return header in ("", "*", _etag(reminder))


def _put(rid, existing):
    live = existing and not existing.get("deleted_at")
    if request.headers.get("If-None-Match", "").strip() == "*" and live:
        return Response("", 412)
    if live and not _etag_ok(existing):
        return Response("", 412)

    fields = ical.ics_to_fields(request.get_data(as_text=True), _all_day_hour())
    if not fields or not fields.get("title") or not fields.get("due_at"):
        # A calendar entry with no title or no time isn't a reminder CHKT
        # could ever fire.
        return Response("An event needs a title and a start time.", 403)

    now = db.now_millis()
    if live:
        record = dict(existing)
    else:
        record = dict(NEW_EVENT_DEFAULTS)
        record.update({"id": rid, "created_at": now})

    for key in ("title", "notes", "tags", "due_at", "duration_minutes",
                "repeat_rule", "alert_mode", "nag_interval_minutes",
                "nag_stop_after_minutes", "vibrate", "respect_dnd", "enabled"):
        if key in fields:
            record[key] = fields[key]
    record["alert_mode"] = store.normalize_alert_mode(record.get("alert_mode"))
    record["deleted_at"] = None
    record["updated_at"] = now
    store.upsert_reminder(record)

    saved = store.get_reminder(rid)
    return Response("", 204 if live else 201, {"ETag": _etag(saved)})
