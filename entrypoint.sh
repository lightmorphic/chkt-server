#!/bin/sh
# Makes the container installable with zero setup: if SECRET_KEY isn't
# supplied via the environment, generate one once and keep it in the data
# volume so it survives restarts and rebuilds. Anyone who wants a specific
# key (e.g. moving a server) can still set SECRET_KEY in .env to skip this.
set -e

if [ -z "$SECRET_KEY" ]; then
  KEYFILE="/data/.secret_key"
  mkdir -p /data
  if [ ! -f "$KEYFILE" ]; then
    python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "$KEYFILE"
    chmod 600 "$KEYFILE"
  fi
  SECRET_KEY="$(cat "$KEYFILE")"
  export SECRET_KEY
fi

exec "$@"
