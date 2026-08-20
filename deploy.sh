#!/usr/bin/env bash
# Deploy CHKT Server to the homelab. One command: ./deploy.sh
#
# Target: the homelab, reached over Tailscale via the "homelab" ssh alias.
#
# This runs the *same* install path every user runs — docker compose up -d
# --build against the repo's own docker-compose.yml. The homelab is just an
# ordinary installation: its host-specific values (port, data location,
# secret key) live in its .env, which this script never overwrites, so
# nothing here diverges from what a stranger's clone does.
set -euo pipefail

HOST="homelab"
DIR="chkt-server"

echo "Syncing code to $HOST:$DIR ..."
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude 'data' --exclude '.env' \
  ./ "$HOST:$DIR/"

echo "Building and starting ..."
ssh "$HOST" DIR="$DIR" bash -s <<'REMOTE'
set -euo pipefail
cd "$HOME/$DIR"

# The .env is the only thing that makes this host different, and it holds
# the secret key. Never generate one here: a fresh .env would fall back to
# the default ./data and start the app with an empty database while the
# real one sits untouched elsewhere. Better to stop and say so.
if [ ! -f .env ]; then
  echo "No .env in $HOME/$DIR — refusing to deploy." >&2
  echo "This host needs one, e.g.:" >&2
  echo "  CHKT_PORT=4010" >&2
  echo "  CHKT_DATA=/opt/chkt-server/data" >&2
  echo "  CHKT_INSECURE_COOKIES=1" >&2
  echo "  SECRET_KEY=<the existing key — do not invent a new one>" >&2
  exit 1
fi

PORT="$(sed -n 's/^CHKT_PORT=//p' .env | head -n1)"
PORT="${PORT:-8321}"
DATA="$(sed -n 's/^CHKT_DATA=//p' .env | head -n1)"
DATA="${DATA:-./data}"

if [ ! -d "$DATA" ]; then
  echo "CHKT_DATA points at $DATA, which does not exist — refusing to deploy." >&2
  echo "Compose would create it empty and the app would start with no data." >&2
  exit 1
fi

# A leftover stack file defining the same container_name would fight this
# deploy, and changes made only in it never reach anybody else's install.
if [ -f /opt/stacks/chkt-server/compose.yaml ]; then
  echo "WARNING: /opt/stacks/chkt-server/compose.yaml still exists." >&2
  echo "         It defines container_name chkt-server too, so whichever" >&2
  echo "         ran last wins. Delete that directory — this repo's" >&2
  echo "         docker-compose.yml is the single definition now." >&2
fi

docker compose up -d --build
sleep 3
curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null && echo "Healthy on port $PORT, data in $DATA."
REMOTE

echo "Done. Rollback: check out an older commit here and rerun this script."
