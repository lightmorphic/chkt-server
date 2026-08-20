# CHKT Server runbook

Plain-language instructions for looking after the server. Commands run in
the `chkt-server` folder on the machine that hosts it.

## Is it up?

Open the site, or:

```bash
curl -s http://127.0.0.1:8321/healthz
```

`{"ok": true}` means the app and its database are answering.

## Restart it

```bash
docker compose restart chkt
```

## It's misbehaving, see what it's saying

```bash
docker compose logs --tail 100 chkt
```

## Update to a new version

```bash
docker compose pull
docker compose up -d
```

## Roll back a bad update

Pin the version you want in `.env` and bring it back up:

```bash
echo "CHKT_VERSION=1.1.9" >> .env    # the version that worked
docker compose up -d
```

Released versions are listed at
https://github.com/lightmorphic/chkt-server/releases.

Your data is safe during a rollback: it lives in `data/`, outside the
container.

## Restore a backup

Backups are dated JSON files in `data/backups/`. To restore one:

1. Sign in → **Settings** → **Import / restore**.
2. Choose the backup file. Pick **Merge** to add it to what's there, or
   **Replace everything** to go back exactly to that day.
3. Click Import (it asks for a second click to confirm).

Test this occasionally with Merge and a recent file. A backup you've never
restored is a hope, not a backup.

## Move to a new server

Copy the whole folder (including `data/` and `.env`) to the new machine and
run `docker compose up -d`. That's everything: settings, reminders,
account, backups.

## Lost the SECRET_KEY?

Reminders, tags, history and backups are fine — none of them are
encrypted. What you lose is everything on the Settings page: it is all
stored encrypted, so with a new key it reads as blank and reverts to
defaults. The old values stay in the database, just unreadable.

Set a new key (or simply leave `SECRET_KEY` unset and let CHKT generate
one into `data/.secret_key`), restart, then:

1. Re-enter the Settings page, including SMTP host, port, from-address
   and password, and quiet hours.
2. Re-enrol two-factor sign-in if you had it.
3. Re-subscribe browser notifications on each device — the web-push
   keypair is regenerated, so existing subscriptions go silent.

You are not locked out: your username and password live outside the
encrypted settings.

Safest place for the key is nowhere at all — leave `SECRET_KEY` unset and
it lives in `data/`, which your backups already cover. A key set in `.env`
disappears the day someone tidies that file.

## Something fires twice

The container must run as a single instance, check nothing has started a
second copy: `docker ps | grep chkt` should show exactly one.
