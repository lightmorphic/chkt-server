# Changelog

## [1.1.32]

### Changed
- The line above the headline on chkt.org has moved below the buttons.
  Whatever it contained, sitting above an h1 made it eyebrow text, which
  the site had just finished removing everywhere else. In its new place
  it qualifies the download it sits under, and says something more
  useful while it's there: the Android version floor is real (8.0), and
  "server optional" answers a question the old wording didn't.

## [1.1.31]

### Changed
- The install block on chkt.org is the compose stack itself, ready to
  paste into Dockge, Portainer or a compose.yaml of your own, instead of
  a git clone that nobody running a stack manager wants. Values match the
  shipped docker-compose.yml exactly: same image, port, data mount and
  hardening.

## [1.1.30]

### Fixed
- chkt.org told people to install the app from F-Droid. It isn't on
  F-Droid (their API returns 404 for the package), so that instruction is
  gone and the install step points at the GitHub releases page.
- Two other claims on the site overstated what CHKT controls: the voice
  widget said the words "never leave" the phone, and the spec list called
  the voice "offline". Both depend on which speech engine and recogniser
  the user has installed, so both now say exactly that.
- Words not yet spoken on the demo's alert screen failed AA contrast
  against the yellow (2.49:1). They sit at 5.06:1 now.

### Added
- Site plumbing for search and answer engines: canonical link, robots.txt,
  sitemap.xml, Open Graph and Twitter cards with a locally generated share
  image, and JSON-LD for the software, the publisher and the FAQ.
- An FAQ answering the six questions people actually ask before
  installing: whether the server is required, Play Services, cost, which
  voice, whether it will wake you, and calendar apps.
- Accessibility and interface polish: skip link, safe-area padding,
  balanced heading wrap, tabular timings, touch-action on controls,
  en-GB locale, and a named form control.

## [1.1.29]

### Changed
- chkt.org redesigned. The old page was a light marketing template with a
  bolted-on demo and too much air; this one is built around the product's
  most recognisable image — a bright yellow alert glowing in a dark room —
  so the page is dark with brand yellow as its only accent. The demo is
  now the whole hero and genuinely interactive: type what you want to be
  told, pick any of the three real alert styles, and the page performs the
  actual sequence with a live trace, a timeline of true timings, and
  working Done and Snooze. Alert style changes the demo the way it changes
  the app — voice only skips the tone, notification only never speaks.
  Features moved from twelve sparse cards to a packed grid, and the
  emptiness is gone: every row fills 97-100% of its width at phone,
  tablet and desktop. Still one file, still no request to anywhere.

## [1.1.28]

### Changed
- **The followed calendar is two-way now.** Reminders CHKT publishes
  (every timed one, or just those wearing your calendar tag) are written
  onto the followed calendar as events, seconds after they're created or
  edited — so a reminder entered on the phone shows in Fastmail almost
  immediately, and an event entered in Fastmail is on the phone within a
  minute. Deleting the event on the calendar deletes the reminder;
  deleting or untagging the reminder withdraws the event; a reminder
  edited here since its last push wins over a remote deletion. With this,
  subscribing the calendar service to CHKT's own calendar is redundant —
  remove that account or everything shows twice. CHKT's own CalDAV server
  is unchanged for clients that want it directly (DAVx⁵, Thunderbird).

## [1.1.27]

### Added
- **Follow a calendar.** Point CHKT at a calendar on your calendar
  service — Fastmail, iCloud, Nextcloud, anything CalDAV — and events you
  create there become reminders here within a minute, with the can't-miss
  defaults: notification and voice, repeating every 5 minutes for an
  hour. This is the fast direction: your service updates its own calendar
  the instant you save, and CHKT checks it every 60 seconds, instead of
  waiting for the service to push outwards on whatever schedule it
  fancies (measured in many minutes for some). Edits there follow here;
  deleting the event removes the reminder; answering or snoozing here
  doesn't touch the event there. Followed reminders are never republished
  onto CHKT's own calendar, so nothing shows up twice. Configure it under
  Settings → Follow a calendar; Save doubles as a connection test.

## [1.1.26]

### Changed
- The version badge now links to chkt.org, the project's own site, rather
  than the GitHub repository.
- chkt.org itself grew up: an interactive demo of an alert — the
  notification, a synthesized ding, the full-screen alert and the reminder
  spoken by the browser's own voice, entirely self-contained so the page
  still makes no external requests — plus the copy brought in line with
  the app that ships (three alert styles, sound-then-voice, tags, and the
  CalDAV calendar).

## [1.1.25]

Security-and-quality audit release: two independent reviews (security and
code quality) of the whole codebase, every finding verified and fixed or
consciously accepted. Highlights below; SECURITY.md gained a section on
the login-throttle trade-off behind a proxy.

### Fixed
- A calendar event with a nonsense date (month 13, hour 25) crashed the
  request with a 500 on the CalDAV endpoint — the one surface exposed to
  the internet. Bad dates now read as "no usable time" and the event is
  refused cleanly (403), with a regression test.
- Every page was rendering without its inline layout styles: the strict
  Content-Security-Policy (deliberately no unsafe-inline) had been
  silently discarding all ~40 style attributes in the templates. They are
  proper CSS classes now, so checkbox rows, panel widths and headings
  render as designed — and the CSP stays strict.
- A sync pull could permanently miss a change committed while the sync
  request was in flight: the "now" watermark the client advances to was
  minted after the change snapshot, leaving a crack between them. The
  watermark is minted first now; overlap is safe, a gap was not.
- Signing in with a wrong username answered measurably faster than a
  wrong password, quietly confirming the one valid username to anyone
  timing the difference. Both cases now cost the same scrypt check.
- The update banner's instructions referenced a deleted deploy script and
  a build-from-source flow; it now gives the pull-based update command.
- An invalid reminder form (unparseable date) silently re-rendered as if
  saved; it now says what went wrong.
- Re-enabling a reminder with a stale snooze no longer fires the moment
  it's switched on, off a snooze pressed weeks ago.
- A crafted repeat unit like "hd" passed a substring check and stored an
  unparseable rule that never fired; the unit is now matched exactly.

### Changed
- First-run /setup on the HTTPS posture (CHKT_INSECURE_COOKIES unset)
  now requires CHKT_SETUP_TOKEN, so a stranger can't claim a fresh
  internet-facing install before its owner. Private-network installs
  (CHKT_INSECURE_COOKIES=1) are unchanged.
- HSTS header on HTTPS responses.
- Housekeeping from the audit: dead constants, an unused CSS variable and
  rule, a pointless CSRF header on a GET, and a stray tzinfo in the
  repeat engine are gone; the iCalendar UID is escaped like every other
  text field; new tests cover /state, version comparison, and the
  malformed-date refusal (91 tests total).

## [1.1.24]

### Added
- The reminder list keeps itself current. Changes that arrive behind the
  page's back — a phone sync, a calendar app writing over CalDAV, another
  tab — used to sit invisible until you refreshed by hand. The list now
  checks for changes the moment you come back to the tab, and every 45
  seconds while it's visible, and reloads itself when something moved.

## [1.1.23]

### Fixed
- The version badge sat in the bottom-right corner, exactly underneath
  the add button, which covered it. Moved to the bottom left.
- Newly released versions weren't offered by the in-app update check:
  the banner reads GitHub releases, and 1.1.15 through 1.1.22 shipped as
  tags and images without one. Those releases are backfilled, and from
  now on the publish workflow creates the release itself, so a version
  can't ship invisible to the checker again.

## [1.1.22]

### Fixed
- Switching the calendar tag filter on left already-subscribed calendar
  apps showing the old, unfiltered set on days they had already fetched —
  seen as "today shows only tagged reminders, future days show
  everything". Changing the setting changes which reminders are published
  without touching any reminder row, and the change markers clients watch
  (ctag and sync token) were built purely from row timestamps, so
  subscribers were told nothing had changed and kept their stale copies.
  Both markers now carry a settings generation: saving a different tag
  bumps it, subscribed clients see a changed calendar, re-list it in full,
  and drop what no longer belongs. A sync token from before the change is
  refused per RFC 6578, which tells the client to do exactly that full
  resync.

## [1.1.21]

### Added
- A version badge in the bottom-right corner of every page, so you can see
  what the server is running without going to Settings. Clicking it opens
  the project's page on GitHub, where the releases and changelog live.
  Signed-in pages only — the login screen doesn't advertise the version.

## [1.1.20]

### Changed
- **Tags are lowercase, everywhere.** "Cal" and "cal" were two different
  tags that looked identical in a list, which is a trap rather than a
  feature. Existing tags are lowercased on upgrade (and their reminders
  marked changed, so phones pull the tidied version rather than pushing
  the old one back), and every route in — the web form, sync, and events
  arriving over CalDAV — passes through one rule.
- **The tag box is chips and autocomplete.** Start typing and the tags you
  already have appear; click one and it becomes a chip. A word that isn't
  a tag yet takes a deliberate "add as a new tag" click, so a typo can't
  quietly become a tag that sits in the list forever looking almost right.
  Plain comma-separated text still works with JavaScript off.
- **The calendar tag is chosen from tags that exist**, rather than typed.
  Naming a tag nothing wears published an empty calendar and read as a
  broken feature. Supersedes 1.1.19, which approached this from the wrong
  end by offering a tag that didn't exist yet: make the tag on a reminder,
  then choose it in Settings.

## [1.1.19]

### Added
- The calendar tag is always offered when editing a reminder, whether or
  not anything wears it yet, and the page says plainly what it does:
  "Tag a reminder #cal to put it on your calendar." Suggestions otherwise
  come only from tags already in use, which made the one tag that decides
  what reaches your calendar the one tag nothing could suggest. The phone
  app picks it up by itself once a single reminder has it and syncs.

## [1.1.18]

### Added
- **Only publish reminders with a chosen tag.** Settings → Calendar takes a
  tag (say `cal`); fill it in and only reminders wearing it reach the
  calendar. A wall of daily repeats stays out of the way while a weekly
  rehearsal doesn't — and it's a tag, so you can set it from the phone
  today without waiting for an app update. Leave it empty and every timed
  reminder is published, as before. Capitals don't matter, an event you
  add from a calendar app gets the tag automatically so it stays visible,
  and taking the tag off a reminder removes it from subscribed calendars
  the same way deleting it would.

### Fixed
- Redirects sent CalDAV clients from `https://` to `http://`. Behind
  Tailscale serve, Funnel, Caddy or any other TLS terminator the app is
  spoken to over plain HTTP, so it built its redirects with the wrong
  scheme and a client following one landed where nothing was listening.
  The forwarded scheme is now honoured (the forwarded host deliberately
  isn't, so a spoofed header can't rewrite CHKT's own URLs).

## [1.1.17]

### Fixed
- A reminder's length was wiped by the next sync from a phone. Every
  released version of the app predates the field, so it never sends it,
  and the merge read "absent" as "zero" — set a length on the calendar,
  edit anything on your phone, and the event collapsed back to a moment.
  Absent now means unchanged, the same way the server already protects
  its own in-progress re-alert state, which the app likewise never sends.

## [1.1.16]

### Added
- **Calendar (CalDAV).** CHKT publishes your reminders as a calendar any
  calendar app can subscribe to — DAVx⁵ on Android, Thunderbird,
  Evolution or Apple Calendar on a desktop — and it works both ways: an
  event added to the CHKT calendar comes back as a reminder that gives a
  notification and speaks, and repeats every 5 minutes for an hour until
  it's answered. Subscribe to `/dav/` with any username and a device
  access key as the password (Settings shows the address). Reminders
  carry their repeat rule across as an `RRULE`, and their alert settings
  survive a round trip through a calendar app rather than being reset.
- Reminders have a length. It defaults to nothing — a reminder is a
  moment — but set one and the calendar shows a block of that size, so a
  meeting looks like a meeting. Settable in the app and on the web, and
  it rides the sync contract as `durationMinutes`.
- An all-day event has no time of day, so Settings has the hour that
  reminders made from one should alert (09:00 unless you change it).

### Changed
- History now takes every ended reminder, not just one-times: a repeating
  or location reminder you switch off moves there too, instead of sitting
  at the bottom of the main list. Reuse works the same way. Matches the
  same change in the app.

## [1.1.15]

### Changed
- The timezone is now set with `CHKT_TZ` rather than `TZ`, for the same
  reason `CHKT_SECRET_KEY` replaced `SECRET_KEY` in 1.1.13: a plain name
  can be claimed by whatever runs compose, which then overrides your
  `.env` without saying so. A timezone that silently isn't yours means
  every reminder fires at the wrong hour. Every setting CHKT reads from
  `.env` is now `CHKT_`-prefixed.
- Added `.env.example`, an annotated list of every setting with its
  default, and a matching table in the README, so the knobs are in one
  place rather than scattered through prose.

## [1.1.14]

### Added
- History page: one-time reminders leave the main list once they're done
  (answered or switched off) and live under the new History tab instead.
  Look back over them, or open one, give it a new date, and it comes
  back — a finished reminder opens with Active re-ticked and a stale
  date rolled forward to today, so "pick a date, Save" is the whole
  gesture. Matching History screen in the app (1.0.17).

## [1.1.13]

### Fixed
- The secret key could be silently taken from the surrounding
  environment. Compose lets the environment it runs in override a
  stack's `.env`, so a stack manager that has its own `SECRET_KEY` set
  passed that key to CHKT — CHKT then never generated its own, and
  saved settings appeared to reset whenever that other key changed. The
  compose file now reads `CHKT_SECRET_KEY`, which nothing else is likely
  to define. Set `CHKT_SECRET_KEY` in `.env` if you supply your own key;
  leaving it unset is still the recommended arrangement.

## [1.1.12]

### Fixed
- The container could fail to start with a mount error about
  `/etc/localtime` ("not a directory"). It bind-mounted the host's clock
  files, which doesn't work on hosts where `/etc/localtime` isn't a plain
  file or `/etc/timezone` doesn't exist. Timezone is now set with `TZ` in
  `.env` (e.g. `TZ=Europe/London`), and the image carries the zoneinfo
  database so any zone resolves. Existing installs that were working keep
  working; set `TZ` to be explicit about it.

## [1.1.11]

### Changed
- CHKT is now published as a container image
  (`ghcr.io/lightmorphic/chkt-server`) built for amd64 and arm64 on every
  release. Installing and updating are ordinary pulls, so nothing is
  compiled on your server and machines without build tooling work too.
  `docker compose up -d` for a fresh install, `docker compose pull &&
  docker compose up -d` to update. Building from the source you cloned is
  still one flag away, via the new `docker-compose.build.yml` override.
- The published port and the data location can now be set in `.env`
  (`CHKT_PORT`, `CHKT_DATA`) instead of editing the compose file, and
  `CHKT_VERSION` pins a specific release for deliberate upgrades or for
  rolling one back.
- Removed `deploy.sh`; it drove Docker over ssh on one particular host.

### Fixed
- The runbook's advice for a lost `SECRET_KEY` understated it: every
  setting is encrypted, not only the SMTP password and 2FA seed, so all
  of them reset. It now says so, and suggests leaving `SECRET_KEY` unset
  so the key lives in `data/` where backups already cover it.

## [1.1.10]

### Fixed
- Answering a nagging reminder on the phone didn't stop the server's
  re-alert cycle: the sync merge preserved the server's nag state (the
  1.1.8 fix) even when the incoming record showed the occurrence had been
  answered or snoozed, and the mismatched fire-tracking then degenerated
  into a push every 20 seconds until the nag timeout, ending in a spurious
  MISSED log. A sync that advances, snoozes, or disables a reminder now
  ends the server's nag cycle for it; an unrelated edit still doesn't.
- Repeating reminders crossing a daylight-saving change landed an hour
  off for that day (the repeat engine stepped fixed-offset datetimes);
  arithmetic is now done in wall-clock time and re-localised, matching
  the app.
- Every page load added a duplicate push subscription row (and a
  duplicate push per fire, invisibly collapsed by the browser); one row
  per endpoint now.
- The stats page showed a stray ", " when there was no completion rate.

### Security
- Login and 2FA are rate-limited: 5 failures per address per 15 minutes,
  closing off sustained online guessing of the password or 6-digit code.
- TOTP codes are single-use; a code that already signed in can't be
  replayed inside its validity window.
- The login, setup, and logout forms now carry CSRF tokens like every
  other form.
- New optional `CHKT_SETUP_TOKEN`: on a public install, first-run account
  creation requires the token, so a stranger can't claim a fresh server.
- The HTTPS overlay no longer leaves plain-HTTP port 8321 published on
  the host; everything goes through Caddy.
- The container drops all Linux capabilities and forbids privilege
  escalation; gunicorn updated to 23.0.0 (request-smuggling fix,
  CVE-2024-6827).
- Web-push subscriptions must be HTTPS endpoints; the push engine can't
  be pointed at arbitrary URLs.
- SECURITY.md now describes the deployment model accurately (the old
  text claimed a localhost-only bind that was never true).

### Housekeeping
- Old fire records and sent mail are pruned automatically (7/30 days).
- Removed dead code (unused JSON helpers, unused imports) and the stale
  "VPS" wording in deploy.sh.

## [1.1.9]

### Fixed
- A repeating reminder stayed pinned at the top of the list long after
  its time passed, still showing today instead of its real next
  occurrence: the list sorted by the raw stored due time, which only
  advances once the reminder is answered or nag-times-out. Now sorts by
  the actual next alert instead, matching the same fix on the app
  (chkt 1.0.13).

## [1.1.8]

### Fixed
- The web dashboard's live-alert polling silently died forever once the
  login session expired: the redirect to `/login` was treated as a
  successful response, so it tried to parse the login page as JSON,
  failed quietly, and never announced another alert. Now detects the
  redirect and shows a "signed out" banner with a link to sign back in.
- Re-alert nagging stopped after the first alert, and a fired reminder
  could get stuck showing as still due long after its time passed. Root
  cause: the sync merge always overwrote `nag_started_at` with null on
  any incoming reminder (the app never sends it, it isn't in the JSON
  contract), so a routine sync push moments after an alert fired would
  silently cancel the in-progress re-alert cycle. Fixed by preserving the
  server's own value across a sync merge instead of accepting the
  client's null default.

## [1.1.7]

### Fixed
- Reminder times shown an hour off from the phone: the container had no
  timezone of its own, so it rendered every time in UTC regardless of
  where the server actually is. Now mounts the host's `/etc/localtime`
  and `/etc/timezone` read-only so the two agree.
- Missing favicon: added a `/favicon.ico` and a real `.ico` file
  alongside the SVG icon, since some browsers request that path
  directly and ignore the `<link rel="icon">` tag.

## [1.1.6]

### Removed
- Offsite backup to a private GitHub repository. Local daily backups plus
  the existing "Download everything" zip and JSON import already cover
  restoring a server; the GitHub piece was extra setup for no real benefit.

## [1.1.5]

### Added
- Gunicorn access logging (method, path, status), so a support session can
  actually see what a request did instead of finding nothing in the logs.

## [1.1.4]

### Fixed
- The Weekly repeat day-of-week checkboxes were visually split from
  their labels (checkbox in one row, day name in another) — caused by
  reusing the generic `.row` form-field class, which forces `flex:1;
  min-width:8rem` onto each child. Given its own `.weekday-picker`
  class instead.

## [1.1.3]

### Changed
- Web dashboard styling now matches the app: reminder titles read in
  plain off-white/light-grey text instead of link-blue, tags are the
  accent yellow, and each reminder has a filled/outline circle (tap to
  toggle active) instead of only showing an "off" badge when disabled.
- The "Add reminder" button is now a floating button fixed to the
  bottom-right corner (matching the app's FAB), instead of a link at
  the bottom of the list that required scrolling all the way down.

### Added
- `POST /reminder/<id>/toggle` — flips a reminder's active state,
  backing the new circle indicator.

## [1.1.2]

### Added
- Custom repeat interval now supports whole years ("every 3 years"),
  matching the app. Calendar-based, not a fixed timedelta, so leap
  years don't drift it (29 Feb clamps to 28 Feb, same as YEARLY).

## [1.1.1]

### Changed
- Alert choice simplified to match the app: notification + voice, voice
  only, or notification only. Ringing and the pre-tone chime are gone;
  the "stop after" nag options no longer need them either.
- Notes are shown on the alert overlay but no longer read aloud — only
  the title is spoken.
- Existing reminders saved under the old ring-based alert modes migrate
  automatically to their closest new equivalent on next start.

## [1.1.0]

### Added
- Quiet hours: a do-not-disturb schedule for CHKT itself. Reminders still
  fire and appear during the window, they just don't ring, speak, or
  vibrate (push notifications arrive silently too).
- Add a reminder by voice on the new-reminder form (Web Speech API), a
  direct match for the app's tap-to-record widget and the same structured
  phrases ("remind me at 2pm to feed the cat"). Runs entirely client-side.
- Per-reminder vibration now actually vibrates supporting browsers when an
  alert fires in an open tab (previously stored and synced but unused).
- Zero-config Docker install: CHKT now generates and keeps its own secret
  key in the data volume if one isn't supplied, so `docker compose up -d
  --build` alone is enough to try it.
- Optional `docker-compose.https.yml` + `Caddyfile.example` for a public
  install with automatic HTTPS on a real domain.
- A proper marketing/install page (`docs/index.html`, GitHub Pages).

## [1.0.0] - unreleased

First release.

### Added
- Tags replace lists, matching the app: home shows everything coming up in
  time order with tag filtering; sync and export carry tags (v1 files still
  import, list names become tags).
- Full web UI for reminder lists and reminders, installable as a PWA.
- In-browser alerts: tone + spoken reminders (speech synthesis) on open
  pages, web push notifications otherwise.
- Sync API for the CHKT Android app: newest-wins merge, deletion
  tombstones, append-only completion logs, per-device revocable access keys.
- Server-side due-reminder engine mirroring the app's repeat rules.
- Single-account auth: scrypt passwords, optional TOTP 2FA, hardened
  sessions and CSRF protection.
- Settings stored encrypted at rest (SMTP, GitHub backup, push keys), with
  test buttons for email and GitHub.
- Daily local backups with pruning, offsite copies to a private GitHub
  repository, zip-everything download, and merge/replace restore.
- JSON and markdown export.
- Completion statistics.
- Guided one-question-at-a-time flow for creating reminders, matching the
  app; the full form remains for editing.
- Per-reminder nag re-alerts (1/2/5 min) with automatic stop, vibration and
  Do Not Disturb flags, delete-once-dismissed, and an active toggle, all
  synced with the app.
- A default "Reminders" list is created on first-run setup.
- Update notice on Settings when a newer server release exists on GitHub
  (checked at most daily, fails silently offline).
- Docker packaging with healthcheck; single-worker by design.
