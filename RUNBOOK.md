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
git pull
docker compose up -d --build
```

## Roll back a bad update

```bash
git log --oneline          # find the version that worked, e.g. abc1234
git checkout abc1234
docker compose up -d --build
```

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
run `docker compose up -d --build`. That's everything: settings, reminders,
account, backups.

## Lost the SECRET_KEY?

Reminders and lists are fine, but encrypted settings (SMTP password, 2FA)
can't be decrypted. Set a new `SECRET_KEY` in `.env`, restart, and re-enter
those settings on the Settings page.

## Something fires twice

The container must run as a single instance, check nothing has started a
second copy: `docker ps | grep chkt` should show exactly one.
