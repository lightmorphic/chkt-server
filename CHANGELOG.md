# Changelog

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
