# Security policy

## Reporting a vulnerability

Email **security@lightmorphic.co.uk** with what you found, how to reproduce
it, and the impact you expect. You'll get a reply within a week. Please
hold off on public disclosure until a fix ships.

## Design notes

- Single-account server with scrypt-hashed password and optional TOTP 2FA.
- Sessions: HttpOnly, SameSite=Lax, Secure cookies; CSRF tokens on every
  state-changing form.
- Device sync uses random per-device access keys, stored as SHA-256 hashes,
  revocable at any time.
- Login and 2FA are rate-limited (5 failures per address per 15 minutes),
  and a TOTP code that has signed in once can't be replayed.
- All stored credentials (SMTP, VAPID keys, TOTP seed) are encrypted at
  rest with a key derived from `SECRET_KEY`. Note that the auto-generated
  `SECRET_KEY` lives in the same `/data` volume as the database, so a copy
  of the whole volume includes both — protect backups of `./data`
  accordingly, or supply `SECRET_KEY` via the environment instead.
- Strict Content-Security-Policy; no external scripts, styles, fonts, or
  requests of any kind from the web UI.
- The container serves plain HTTP on port 8321, meant for a private
  network (Tailscale, home LAN). For the public internet use the Caddy
  overlay (`docker-compose.https.yml`): it stops publishing 8321, serves
  everything over HTTPS, and supports `CHKT_SETUP_TOKEN` so only you can
  claim a fresh install's account.
- The container drops all Linux capabilities and forbids privilege
  escalation (see docker-compose.yml).
