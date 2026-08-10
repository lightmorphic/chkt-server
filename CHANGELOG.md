# Changelog

## [1.0.0] - unreleased

First release.

### Added
- Full web UI for reminder lists and reminders, installable as a PWA.
- In-browser alerts: tone + spoken reminders (speech synthesis) on open
  pages, web push notifications otherwise.
- Sync API for the Chkt Android app: newest-wins merge, deletion
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
