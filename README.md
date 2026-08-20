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
- **Backups**, daily local snapshots plus a one-click "download everything"
  zip you can save wherever you like.

GPL-3.0, no tracking, no third-party services beyond what you choose to
configure.

## Install

Requirements: Docker with the compose plugin.

```bash
git clone https://github.com/lightmorphic/chkt-server
cd chkt-server
docker compose up -d
```

That pulls a prebuilt image, so nothing is compiled on your server and it
works on machines with no build tooling. Prefer to build it yourself from
the source you just cloned? Add the build override:

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

Either way, no configuration file is needed to try it. CHKT generates its own
secret key on first start and saves it in `./data`, so it survives
restarts and rebuilds. Open `http://<this-machine>:8321` and the first
visit walks you through creating your account. Everything else, email
alerts, backups, two-factor sign-in, device keys, quiet hours, is
configured on the Settings and Devices pages, with a test button beside
anything that can be tested.

### Set your timezone

CHKT shows and fires reminders in the container's timezone, which is UTC
unless you say otherwise. If that isn't your timezone, put yours in
`.env`:

```bash
echo "TZ=Europe/London" >> .env      # or your zone from the tz database
```

Then `docker compose up -d`. Without it, a 9am reminder is 9am UTC, which
won't match the phone.

### If port 8321 is taken, or your data lives elsewhere

Both are optional and both go in `.env` beside the compose file:

```bash
echo "CHKT_PORT=4010" >> .env                     # host port; inside stays 8321
echo "CHKT_DATA=/opt/chkt-server/data" >> .env    # where the database lives
```

Then `docker compose up -d --build` as usual. Leave them unset and you get
8321 and `./data`, as above. Changing `CHKT_DATA` later points the app at a
different folder — move the old one across first, or it starts empty.

### Putting it on the internet with a domain

The steps above are enough for your home network or a Tailscale-style
private network. To serve it publicly with a real domain and automatic
HTTPS, add the Caddy override:

```bash
cp Caddyfile.example Caddyfile
# edit Caddyfile: put your domain in place of chkt.example.com,
# and point that domain's DNS A record at this server first

# On the public internet a stranger could reach a fresh install's setup
# page before you do. This token means only you can create the account:
echo "CHKT_SETUP_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(16))')" >> .env

docker compose -f docker-compose.yml -f docker-compose.https.yml up -d
```

Caddy requests and renews the certificate itself; there's nothing else to
set up. With the override active, only Caddy is reachable from outside —
the app's plain-HTTP port isn't published. On first visit, create your
account at `https://your.domain/setup?setup_token=<the token from .env>`.

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
