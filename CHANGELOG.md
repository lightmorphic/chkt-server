# Changelog

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
