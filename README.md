# CHKT Server

The self-hosted companion to [CHKT](https://github.com/lightmorphic/chkt),
the talking reminders app. Run it in Docker on your own server and every
feature of the phone app is there in the browser too:

- **Everything the app does**: tags, flexible repeats, four alert styles,
  re-alert until answered with an automatic stop, Do Not Disturb control,
  quiet hours, location reminders, snooze chosen at alert time, and a
  voice "add by speaking" button, installable as an app (PWA) with desktop
  notifications and spoken alerts.
- **Sync**, your phone and browser always match. Off by default on the
  phone; one server address and access key turns it on.
- **Backups that leave the building**, daily snapshots kept locally and
  pushed to a private GitHub repository.

GPL-3.0, no tracking, no third-party services beyond what you choose to
configure.

## Install

Requirements: Docker with the compose plugin.

```bash
git clone https://github.com/lightmorphic/chkt-server
cd chkt-server
docker compose up -d --build
```

That's it, no configuration file needed to try it. CHKT generates its own
secret key on first start and saves it in `./data`, so it survives
restarts and rebuilds. Open `http://<this-machine>:8321` and the first
visit walks you through creating your account. Everything else, email
alerts, offsite backups, two-factor sign-in, device keys, quiet hours, is
configured on the Settings and Devices pages, with a test button beside
anything that can be tested.

### Putting it on the internet with a domain

The steps above are enough for your home network or a Tailscale-style
private network. To serve it publicly with a real domain and automatic
HTTPS, add the Caddy override:

```bash
cp Caddyfile.example Caddyfile
# edit Caddyfile: put your domain in place of chkt.example.com,
# and point that domain's DNS A record at this server first

docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
```

Caddy requests and renews the certificate itself; there's nothing else to
set up.

### If you do want to set your own secret key

Only needed if you're migrating an existing server to a new machine and
want to keep the same key (so encrypted settings still decrypt):

```bash
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" > .env
docker compose up -d --build
```

`SECRET_KEY` is the only secret that ever lives in the environment. Every
other credential you enter is stored encrypted with a key derived from it,
so a stolen copy of the database alone gives up nothing. **Don't lose or
change it once it's set**: stored settings can't be decrypted without it.

## Connect your phone

1. Open **Devices**, create an access key, copy it.
2. In the CHKT app: **Settings → Sync**, enter your server address and the
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
