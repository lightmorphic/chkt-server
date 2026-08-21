"""CalDAV: discovery, reading the calendar, and events added by a calendar
app coming back as reminders with CHKT's defaults."""
import base64
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
from app import caldav, db, ical, store  # noqa: E402
from app.auth import new_access_key  # noqa: E402
from app.settings_store import put as setting_put  # noqa: E402

CAL = caldav.CALENDAR_PATH


def _reminder(rid, title, due_at, **kw):
    now = db.now_millis()
    record = {
        "id": rid, "tags": "", "title": title, "notes": "", "due_at": due_at,
        "duration_minutes": 0, "repeat_rule": "", "alert_mode": "NOTIFY_AND_SPEAK",
        "pre_tone": 0, "enabled": 1, "vibrate": 1, "respect_dnd": 0,
        "nag_interval_minutes": 0, "nag_stop_after_minutes": 60, "nag_started_at": None,
        "delete_after_dismissed": 0, "snoozed_until": None,
        "location_trigger": "NONE", "latitude": None, "longitude": None,
        "radius_metres": 150.0, "created_at": now, "updated_at": now, "deleted_at": None,
    }
    record.update(kw)
    return record


EVENT_ICS = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\n"
    "UID:{uid}\r\nSUMMARY:{summary}\r\nDTSTART:{start}\r\n{extra}"
    "END:VEVENT\r\nEND:VCALENDAR\r\n"
)


class CalDavTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
        os.environ["CHKT_BACKUP_DIR"] = os.path.join(_tmp, "backups")
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.key = new_access_key("caldav-test")
        cls.auth = {"Authorization": "Basic " + base64.b64encode(
            f"chkt:{cls.key}".encode()).decode()}
        store.upsert_reminder(_reminder("timed", "Water plants", 1_900_000_000_000,
                                        duration_minutes=30, tags="home"))
        store.upsert_reminder(_reminder("placeonly", "Buy milk", None,
                                        location_trigger="ARRIVE"))

    def _dav(self, path, method, body="", **headers):
        head = dict(self.auth)
        head.update(headers)
        return self.client.open(path, method=method, data=body, headers=head)

    # ---- auth ----

    def test_01_unauthenticated_is_challenged(self):
        r = self.client.open(CAL, method="PROPFIND")
        self.assertEqual(401, r.status_code)
        self.assertIn("Basic", r.headers.get("WWW-Authenticate", ""))

    def test_02_wrong_key_rejected(self):
        bad = {"Authorization": "Basic " + base64.b64encode(b"chkt:nope").decode()}
        self.assertEqual(401, self.client.open(CAL, method="PROPFIND", headers=bad).status_code)

    # ---- discovery ----

    def test_03_options_advertises_caldav(self):
        r = self.client.open(CAL, method="OPTIONS")
        self.assertIn("calendar-access", r.headers.get("DAV", ""))

    def test_04_well_known_redirects(self):
        r = self.client.get("/.well-known/caldav")
        self.assertEqual(301, r.status_code)
        self.assertEqual(caldav.ROOT_PATH, r.headers["Location"])

    def test_05_root_points_at_the_principal(self):
        r = self._dav(caldav.ROOT_PATH, "PROPFIND")
        self.assertEqual(207, r.status_code)
        self.assertIn(caldav.PRINCIPAL_PATH, r.get_data(as_text=True))

    def test_06_home_lists_the_calendar(self):
        r = self._dav(caldav.HOME_PATH, "PROPFIND", Depth="1")
        body = r.get_data(as_text=True)
        self.assertIn(CAL, body)
        self.assertIn("calendar", body)

    # ---- reading ----

    def test_07_calendar_lists_timed_reminders_only(self):
        r = self._dav(CAL, "PROPFIND", Depth="1")
        body = r.get_data(as_text=True)
        self.assertIn("timed.ics", body)
        # A location-only reminder has no moment to draw on a calendar.
        self.assertNotIn("placeonly.ics", body)

    def test_08_get_event_is_icalendar(self):
        r = self._dav(CAL + "timed.ics", "GET")
        body = r.get_data(as_text=True)
        self.assertEqual(200, r.status_code)
        self.assertIn("text/calendar", r.headers["Content-Type"])
        self.assertIn("SUMMARY:Water plants", body)
        self.assertIn("DTSTART:", body)
        self.assertIn("DTEND:", body)          # 30 minutes long
        self.assertTrue(r.headers["ETag"])

    def test_09_zero_length_reminder_has_no_dtend(self):
        store.upsert_reminder(_reminder("moment", "Take pill", 1_900_000_100_000))
        body = self._dav(CAL + "moment.ics", "GET").get_data(as_text=True)
        self.assertIn("DTSTART:", body)
        self.assertNotIn("DTEND", body)

    def test_10_multiget_returns_calendar_data(self):
        report = ('<?xml version="1.0"?><C:calendar-multiget xmlns:D="DAV:" '
                  'xmlns:C="urn:ietf:params:xml:ns:caldav"><D:prop><D:getetag/>'
                  '<C:calendar-data/></D:prop>'
                  f'<D:href>{CAL}timed.ics</D:href></C:calendar-multiget>')
        body = self._dav(CAL, "REPORT", report, Depth="1").get_data(as_text=True)
        self.assertIn("BEGIN:VEVENT", body)
        self.assertIn("Water plants", body)

    # ---- writing ----

    def test_11_new_event_becomes_a_reminder_with_defaults(self):
        ics = EVENT_ICS.format(uid="fromcal", summary="Dentist",
                               start="20260910T143000", extra="DURATION:PT45M\r\n")
        r = self._dav(CAL + "fromcal.ics", "PUT", ics)
        self.assertEqual(201, r.status_code)

        saved = store.get_reminder("fromcal")
        self.assertEqual("Dentist", saved["title"])
        self.assertEqual(45, saved["duration_minutes"])
        # The defaults the user asked for: spoken as well as shown, and
        # nagging every 5 minutes for an hour.
        self.assertEqual("NOTIFY_AND_SPEAK", saved["alert_mode"])
        self.assertEqual(5, saved["nag_interval_minutes"])
        self.assertEqual(60, saved["nag_stop_after_minutes"])
        self.assertEqual(1, saved["enabled"])

    def test_12_all_day_event_lands_on_the_chosen_hour(self):
        ics = EVENT_ICS.format(uid="allday", summary="Passport expires",
                               start="20260911", extra="")
        ics = ics.replace("DTSTART:", "DTSTART;VALUE=DATE:")
        self.assertEqual(201, self._dav(CAL + "allday.ics", "PUT", ics).status_code)

        saved = store.get_reminder("allday")
        from datetime import datetime
        when = datetime.fromtimestamp(saved["due_at"] / 1000)
        self.assertEqual(caldav._all_day_hour(), when.hour)
        self.assertEqual(0, saved["duration_minutes"])

    def test_13_repeating_event_maps_onto_a_repeat_rule(self):
        ics = EVENT_ICS.format(uid="weekly", summary="Standup",
                               start="20260914T090000",
                               extra="RRULE:FREQ=WEEKLY;BYDAY=MO,WE\r\n")
        self._dav(CAL + "weekly.ics", "PUT", ics)
        self.assertEqual("WEEKLY:MON,WED", store.get_reminder("weekly")["repeat_rule"])

    def test_14_event_without_a_start_is_refused(self):
        ics = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:x\r\nSUMMARY:No time\r\n"
               "END:VEVENT\r\nEND:VCALENDAR\r\n")
        self.assertEqual(403, self._dav(CAL + "notime.ics", "PUT", ics).status_code)
        self.assertIsNone(store.get_reminder("notime"))

    def test_15_edit_keeps_chkt_settings_it_wasnt_told_about(self):
        store.upsert_reminder(_reminder("kept", "Original", 1_900_000_200_000,
                                        nag_interval_minutes=2, respect_dnd=1))
        ics = EVENT_ICS.format(uid="kept", summary="Renamed in the calendar",
                               start="20260915T080000", extra="")
        self.assertEqual(204, self._dav(CAL + "kept.ics", "PUT", ics).status_code)

        saved = store.get_reminder("kept")
        self.assertEqual("Renamed in the calendar", saved["title"])
        self.assertEqual(2, saved["nag_interval_minutes"])
        self.assertEqual(1, saved["respect_dnd"])

    def test_16_round_trip_preserves_alert_settings(self):
        original = store.get_reminder("kept")
        ics = ical.reminder_to_ics(original)
        self.assertEqual(204, self._dav(CAL + "kept.ics", "PUT", ics).status_code)
        saved = store.get_reminder("kept")
        for field in ("alert_mode", "nag_interval_minutes", "nag_stop_after_minutes",
                      "vibrate", "respect_dnd", "duration_minutes", "due_at"):
            self.assertEqual(original[field], saved[field], field)

    def test_17_delete_tombstones_and_leaves_the_calendar(self):
        self.assertEqual(204, self._dav(CAL + "fromcal.ics", "DELETE").status_code)
        self.assertIsNotNone(store.get_reminder("fromcal")["deleted_at"])
        self.assertEqual(404, self._dav(CAL + "fromcal.ics", "GET").status_code)
        listing = self._dav(CAL, "PROPFIND", Depth="1").get_data(as_text=True)
        self.assertNotIn("fromcal.ics", listing)

    def test_18_stale_etag_is_refused(self):
        r = self._dav(CAL + "timed.ics", "PUT",
                      EVENT_ICS.format(uid="timed", summary="Clobber",
                                       start="20260916T080000", extra=""),
                      **{"If-Match": '"1"'})
        self.assertEqual(412, r.status_code)
        self.assertEqual("Water plants", store.get_reminder("timed")["title"])

    # ---- incremental sync ----

    def test_19_sync_collection_reports_changes_and_deletions(self):
        report = ('<?xml version="1.0"?><D:sync-collection xmlns:D="DAV:">'
                  "<D:sync-token/><D:prop><D:getetag/></D:prop></D:sync-collection>")
        body = self._dav(CAL, "REPORT", report).get_data(as_text=True)
        self.assertIn("sync-token", body)
        self.assertIn("timed.ics", body)
        # The deleted one comes back as a 404 response, telling the client to drop it.
        self.assertIn("fromcal.ics", body)
        self.assertIn("404 Not Found", body)


class CalendarTagTest(unittest.TestCase):
    """With a tag set in Settings, the calendar narrows to reminders wearing
    it — so a wall of daily repeats stays out of the calendar while the
    weekly rehearsal doesn't."""

    @classmethod
    def setUpClass(cls):
        os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.key = new_access_key("tag-test")
        cls.auth = {"Authorization": "Basic " + base64.b64encode(
            f"chkt:{cls.key}".encode()).decode()}
        store.upsert_reminder(_reminder("tagged", "Acting group", 1_900_000_300_000,
                                        tags="hobby, Cal", repeat_rule="WEEKLY:TUE"))
        store.upsert_reminder(_reminder("untagged", "Take pills", 1_900_000_400_000,
                                        repeat_rule="DAILY"))
        setting_put("calendar_tag", "cal")

    @classmethod
    def tearDownClass(cls):
        setting_put("calendar_tag", "")

    def _dav(self, path, method, body="", **headers):
        head = dict(self.auth)
        head.update(headers)
        return self.client.open(path, method=method, data=body, headers=head)

    def test_01_only_tagged_reminders_are_published(self):
        body = self._dav(CAL, "PROPFIND", "", Depth="1").get_data(as_text=True)
        self.assertIn("tagged.ics", body)
        self.assertNotIn("untagged.ics", body)

    def test_02_the_tag_is_case_insensitive(self):
        # Set on the reminder as "Cal", typed in Settings as "cal".
        self.assertEqual(200, self._dav(CAL + "tagged.ics", "GET").status_code)

    def test_03_an_untagged_reminder_is_not_reachable(self):
        self.assertEqual(404, self._dav(CAL + "untagged.ics", "GET").status_code)

    def test_04_new_events_get_the_tag_so_they_stay_visible(self):
        ics = EVENT_ICS.format(uid="newtag", summary="Added in Fastmail",
                               start="20261001T190000", extra="")
        self.assertEqual(201, self._dav(CAL + "newtag.ics", "PUT", ics).status_code)
        self.assertIn("cal", [t.casefold() for t in
                              store.tag_list(store.get_reminder("newtag"))])
        self.assertIn("newtag.ics", self._dav(CAL, "PROPFIND", "", Depth="1").get_data(as_text=True))

    def test_05_untagging_removes_it_from_a_subscribed_client(self):
        report = ('<?xml version="1.0"?><D:sync-collection xmlns:D="DAV:">'
                  "<D:sync-token/><D:prop><D:getetag/></D:prop></D:sync-collection>")
        body = self._dav(CAL, "REPORT", report).get_data(as_text=True)
        # A reminder without the tag is reported gone, the same as a deleted
        # one, so the calendar app drops its copy.
        self.assertIn("untagged.ics", body)
        self.assertIn("404 Not Found", body)


class TagSuggestionTest(unittest.TestCase):
    """The calendar tag is offered on the edit page before anything wears
    it — otherwise it's the one tag the suggestions can never show you."""

    @classmethod
    def setUpClass(cls):
        os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
        cls.app = create_app()
        cls.client = cls.app.test_client()
        setup = cls.client.get("/setup").get_data(as_text=True)
        match = re.search(r'name="csrf" value="([^"]+)"', setup)
        if match:
            cls.client.post("/setup", data={
                "csrf": match.group(1), "username": "devtest",
                "password": "local-dev-smoke-test-1", "confirm": "local-dev-smoke-test-1"})
        else:
            login = cls.client.get("/login").get_data(as_text=True)
            cls.client.post("/login", data={
                "csrf": re.search(r'name="csrf" value="([^"]+)"', login).group(1),
                "username": "devtest", "password": "local-dev-smoke-test-1"})

    @classmethod
    def tearDownClass(cls):
        setting_put("calendar_tag", "")

    def test_calendar_tag_is_suggested_even_when_unused(self):
        setting_put("calendar_tag", "cal")
        page = self.client.get("/reminder/new").get_data(as_text=True)
        self.assertIn("#cal", page)
        self.assertIn("put it on your calendar", page)

    def test_nothing_extra_when_no_tag_is_set(self):
        setting_put("calendar_tag", "")
        page = self.client.get("/reminder/new").get_data(as_text=True)
        self.assertNotIn("put it on your calendar", page)


class ForwardedSchemeTest(unittest.TestCase):
    """Behind a TLS proxy the app is spoken to over plain HTTP. A redirect
    that forgets that sends CalDAV clients from https to http, where nothing
    is listening."""

    @classmethod
    def setUpClass(cls):
        os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
        cls.client = create_app().test_client()

    def test_redirect_keeps_the_scheme_the_client_used(self):
        r = self.client.open("/dav", method="PROPFIND",
                             headers={"X-Forwarded-Proto": "https", "Host": "example.ts.net"})
        self.assertEqual(308, r.status_code)
        self.assertTrue(r.headers["Location"].startswith("https://"), r.headers["Location"])


class IcalMappingTest(unittest.TestCase):
    def test_repeat_rules_round_trip(self):
        due = 1_900_000_000_000
        for rule in ("DAILY", "WEEKLY:MON,THU", "MONTHLY:15", "MONTHLY:LAST",
                     "YEARLY:08-10", "EVERY:3d", "EVERY:2w", "EVERY:90m"):
            rrule = ical.rrule_from_repeat(rule, due)
            self.assertTrue(rrule, rule)
            self.assertEqual(rule, ical.repeat_from_rrule(rrule, due), rule)

    def test_one_off_has_no_rrule(self):
        self.assertEqual("", ical.rrule_from_repeat("", 1))
        self.assertEqual("", ical.repeat_from_rrule("", 1))

    def test_folded_lines_survive_the_round_trip(self):
        long_title = "Remember " + "the milk and " * 12 + "nothing else"
        ics = ical.reminder_to_ics(_reminder("long", long_title, 1_900_000_000_000))
        self.assertTrue(any(line.startswith(" ") for line in ics.split("\r\n")))
        self.assertEqual(long_title, ical.ics_to_fields(ics)["title"])
