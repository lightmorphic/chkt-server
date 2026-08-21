# CHKT Server

The self-hosted companion to [CHKT](https://github.com/lightmorphic/chkt),
the talking reminders app. Run it in Docker on your own server and every
feature of the phone app is there in the browser too:

- **Everything the app does**: tags, flexible repeats, three alert styles,
  re-alert until answered with an automatic stop, Do Not Disturb control,
  quiet hours, location reminders, snooze chosen at alert time, and a
  voice "add by speaking" button, installable as an app (PWA) with desktop
  notifications and spoken alerts.
- **Calendar (CalDAV)**, subscribe to your reminders from any calendar app on
  any device, and anything you add to that calendar becomes a reminder.
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
works on machines with no build tooling. CHKT generates its own secret key
on first start and keeps it in the data folder, so there is nothing to set
up and nothing to lose track of. Prefer to build it yourself from
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

### Settings, if the defaults don't suit your machine

Everything is optional and lives in a `.env` file beside the compose file.
Copy the annotated example and edit what you need:

```bash
cp .env.example .env
docker compose up -d
```

| Setting | Default | What it's for |
|---|---|---|
| `CHKT_TZ` | `UTC` | Your timezone, e.g. `Europe/London`. Without it a 9am reminder is 9am UTC and won't match the phone. |
| `CHKT_PORT` | `8321` | Host port, if 8321 is taken. Inside the container it's always 8321. |
| `CHKT_DATA` | `./data` | Where the database, backups and key live. Move the old folder across first if you change it, or CHKT starts empty. |
| `CHKT_INSECURE_COOKIES` | `0` | Set to `1` when reaching CHKT over plain HTTP on a trusted network, or sign-in fails. |
| `CHKT_VERSION` | `latest` | Pin a release to upgrade deliberately, or to roll one back. |
| `CHKT_SECRET_KEY` | generated | Best left unset, see below. |

Every name starts with `CHKT_` on purpose: Docker Compose lets the
environment it runs in override your `.env`, so a plain name like
`SECRET_KEY` or `TZ` can be quietly claimed by whatever launched compose —
some stack managers set both for themselves.

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
echo "CHKT_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" >> .env
docker compose up -d
```

Note the name: `CHKT_SECRET_KEY`, not `SECRET_KEY`. Compose lets the
environment it runs in override your `.env`, and some stack managers run
compose with a `SECRET_KEY` of their own — which would silently become
CHKT's, and change under you.

The key is the only secret that ever lives in the environment. Every other
credential you enter is stored encrypted with a key derived from it, so a
stolen copy of the database alone gives up nothing. **Don't lose or change
it once it's set**: stored settings can't be decrypted without it. Which is
why leaving it unset, so CHKT keeps its own in `data/`, is the easier
arrangement for most people.

## Connect your phone

1. Open **Devices**, create an access key, copy it.
2. In the CHKT app: **Settings → Sync**, enter your server address and the
   key, flip sync on, press **Test connection**.

## Subscribe from a calendar app

Your reminders as a calendar, readable and writable, on whatever calendar app
you already use.

1. Open **Devices**, create an access key, copy it.
2. Point your calendar app at `https://your-server/dav/`. Any username will
   do; the password is the access key.
   - **Android**: DAVx⁵ → add account → "Login with URL and user name".
   - **Thunderbird**: New Calendar → On the Network → CalDAV.
   - **Evolution / Apple Calendar**: add a CalDAV account with that address.

Reminders appear as events at their due time, as long as a length as you gave
them (none by default, so a plain reminder is a moment rather than a block).
Repeats come across as proper recurring events.

Add an event to the CHKT calendar and it becomes a reminder: it shows a
notification and speaks, and repeats every 5 minutes for an hour until you
answer it. All-day events have no time of day, so they alert at the hour set
in **Settings → Calendar** (09:00 to begin with).

Two things worth knowing. The access key travels on every request, so use
HTTPS — the same as everything else here. And CHKT's repeat vocabulary is
smaller than iCalendar's: an exotic recurrence ("last Friday of the month",
"every other Tuesday") lands on the closest rule CHKT can express, which
errs towards repeating more often rather than never firing.

## Day-to-day

See [RUNBOOK.md](RUNBOOK.md) for restart, backup restore, rollback, and
what to do when something misbehaves, written for humans, no jargon.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
echo "SECRET_KEY=dev-only-$(date +%s)" >> .env   # app reads SECRET_KEY directly
.venv/bin/python run.py            # http://127.0.0.1:8321
.venv/bin/python -m unittest discover -s tests
```

## Licence

[GPL-3.0](LICENSE).
