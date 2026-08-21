"""Following a remote calendar: events there become reminders here, edits
and deletions follow, and local answers survive unchanged events."""
import os
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
_tmp = tempfile.mkdtemp(prefix="chkt-test-")
os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
os.environ["CHKT_BACKUP_DIR"] = os.path.join(_tmp, "backups")
os.environ["CHKT_INSECURE_COOKIES"] = "1"

from app import create_app  # noqa: E402  (env must be set first)
from app import db, remote_cal, store  # noqa: E402
from app.settings_store import put as setting_put  # noqa: E402


def _event_ics(uid, summary, start, rrule=""):
    extra = f"RRULE:{rrule}\r\n" if rrule else ""
    return ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"
            f"UID:{uid}\r\nSUMMARY:{summary}\r\nDTSTART:{start}\r\n{extra}"
            "END:VEVENT\r\nEND:VCALENDAR\r\n")


def _future_stamp(hours=30):
    return time.strftime("%Y%m%dT%H0000", time.localtime(time.time() + hours * 3600))


class RemoteCalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["CHKT_DB"] = os.path.join(_tmp, "test.db")
        cls.app = create_app()
        setting_put("remote_cal_enabled", "1")
        setting_put("remote_cal_url", "https://caldav.example/cal/")
        setting_put("remote_cal_user", "me")
        setting_put("remote_cal_password", "app-password")
        setting_put("remote_cal_state", "")

    def _sync_with(self, etags, events):
        with mock.patch.object(remote_cal, "fetch_etags", return_value=etags), \
             mock.patch.object(remote_cal, "fetch_event",
                               side_effect=lambda base, href, u, p: events[href]):
            return remote_cal.sync_once()

    def test_01_a_new_event_becomes_a_cant_miss_reminder(self):
        status = self._sync_with({"/cal/a.ics": '"1"'},
                                 {"/cal/a.ics": _event_ics("u-a", "Dentist", _future_stamp())})
        self.assertIn("1 new", status)
        rid = remote_cal._reminder_id("/cal/a.ics")
        saved = store.get_reminder(rid)
        self.assertEqual("Dentist", saved["title"])
        self.assertEqual("NOTIFY_AND_SPEAK", saved["alert_mode"])
        self.assertEqual(5, saved["nag_interval_minutes"])
        self.assertEqual(60, saved["nag_stop_after_minutes"])
        self.assertEqual("calendar", saved["tags"])

    def test_02_unchanged_etag_leaves_local_answers_alone(self):
        rid = remote_cal._reminder_id("/cal/a.ics")
        answered = dict(store.get_reminder(rid))
        answered["snoozed_until"] = db.now_millis() + 600_000
        store.upsert_reminder(answered)

        self._sync_with({"/cal/a.ics": '"1"'}, {})  # same etag: no fetch at all
        self.assertIsNotNone(store.get_reminder(rid)["snoozed_until"])

    def test_03_an_edit_there_updates_here(self):
        self._sync_with({"/cal/a.ics": '"2"'},
                        {"/cal/a.ics": _event_ics("u-a", "Dentist, moved", _future_stamp(48))})
        rid = remote_cal._reminder_id("/cal/a.ics")
        self.assertEqual("Dentist, moved", store.get_reminder(rid)["title"])

    def test_04_deleting_there_removes_here(self):
        status = self._sync_with({}, {})
        self.assertIn("1 removed", status)
        rid = remote_cal._reminder_id("/cal/a.ics")
        self.assertIsNotNone(store.get_reminder(rid)["deleted_at"])

    def test_05_a_finished_one_off_is_not_imported(self):
        past = time.strftime("%Y%m%dT%H0000", time.localtime(time.time() - 48 * 3600))
        status = self._sync_with({"/cal/old.ics": '"1"'},
                                 {"/cal/old.ics": _event_ics("u-old", "Last week", past)})
        self.assertIsNone(store.get_reminder(remote_cal._reminder_id("/cal/old.ics")))
        self.assertIn("0 new", status)

    def test_06_a_past_start_with_a_repeat_rule_is_imported(self):
        past = time.strftime("%Y%m%dT%H0000", time.localtime(time.time() - 48 * 3600))
        self._sync_with({"/cal/wk.ics": '"1"'},
                        {"/cal/wk.ics": _event_ics("u-wk", "Weekly thing", past, "FREQ=WEEKLY;BYDAY=TU")})
        saved = store.get_reminder(remote_cal._reminder_id("/cal/wk.ics"))
        self.assertEqual("WEEKLY:TUE", saved["repeat_rule"])

    def test_07_followed_reminders_never_publish_back_out(self):
        from app import caldav
        self._sync_with({"/cal/b.ics": '"1"'},
                        {"/cal/b.ics": _event_ics("u-b", "From Fastmail", _future_stamp())})
        published = {r["id"] for r in caldav._events()}
        self.assertFalse(any(rid.startswith(remote_cal.ID_PREFIX) for rid in published))

    def test_08_propfind_parsing(self):
        xml = ('<?xml version="1.0"?><D:multistatus xmlns:D="DAV:">'
               '<D:response><D:href>/cal/</D:href><D:propstat><D:prop>'
               '<D:resourcetype><D:collection/></D:resourcetype></D:prop>'
               '<D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>'
               '<D:response><D:href>/cal/x.ics</D:href><D:propstat><D:prop>'
               '<D:getetag>"abc"</D:getetag></D:prop>'
               '<D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>'
               "</D:multistatus>")
        with mock.patch.object(remote_cal, "_request", return_value=xml.encode()):
            etags = remote_cal.fetch_etags("https://x/cal/", "u", "p")
        self.assertEqual({"/cal/x.ics": '"abc"'}, etags)
