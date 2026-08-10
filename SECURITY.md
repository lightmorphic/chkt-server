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
- All stored credentials (SMTP, GitHub token, VAPID keys, TOTP seed) are
  encrypted at rest with a key derived from `SECRET_KEY`.
- Strict Content-Security-Policy; no external scripts, styles, fonts, or
  requests of any kind from the web UI.
- Intended deployment is behind a reverse proxy that terminates HTTPS; the
  app itself binds to localhost only.
