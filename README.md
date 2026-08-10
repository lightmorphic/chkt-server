# Chkt Server

The self-hosted companion to [Chkt](https://github.com/lightmorphic/chkt),
the talking reminders app. Run it in Docker on your own server and you get:

- The **full Chkt experience in any browser**, same lists, same reminders,
  installable as an app (PWA), with desktop notifications and spoken alerts.
- **Sync**, your phone and browser always match. Off by default on the
  phone; one server address + access key turns it on.
- **Backups that leave the building**, daily snapshots kept locally and
  pushed to a private GitHub repository.

GPL-3.0, no tracking, no third-party services beyond what you configure.

## Install

Requirements: Docker with the compose plugin.

```bash
git clone https://github.com/lightmorphic/chkt-server
cd chkt-server
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" > .env
docker compose up -d --build
```

Then put it behind your reverse proxy with HTTPS (it listens on
`127.0.0.1:8321`) and open it in a browser. The first visit creates your
account. Everything else, email alerts, offsite backups, two-factor
sign-in, device keys, is configured on the Settings and Devices pages,
with a test button beside anything that can be tested.

`SECRET_KEY` is the only secret that lives in the environment. Every other
credential you enter is stored encrypted with a key derived from it, so a
stolen copy of the database alone gives up nothing. **Don't lose or change
`SECRET_KEY`**: stored settings can't be decrypted without it.

## Connect your phone

1. Open **Devices**, create an access key, copy it.
2. In the Chkt app: **Settings → Sync**, enter your server address and the
   key, flip sync on, press **Test connection**.

## Day-to-day

See [RUNBOOK.md](RUNBOOK.md) for restart, backup restore, rollback, and
what to do when something misbehaves, written for humans, no jargon.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
echo "SECRET_KEY=dev-only-$(date +%s)" > .env
.venv/bin/python run.py            # http://127.0.0.1:8321
.venv/bin/python -m unittest discover -s tests
```

## Licence

[GPL-3.0](LICENSE).
