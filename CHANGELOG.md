# Changelog

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
