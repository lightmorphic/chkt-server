#!/usr/bin/env bash
# Deploy CHKT Server to the homelab. One command: ./deploy.sh
#
# Target: the homelab, reached over Tailscale via the "homelab" ssh alias.
#
# The homelab's stack file is authoritative for how the container runs:
# /opt/stacks/chkt-server/compose.yaml, with PORT and SECRET_KEY in a .env
# beside it and data at /opt/chkt-server/data. This script only syncs the
# source, builds the image that stack file names, and brings the stack up.
#
# It deliberately never runs "docker compose up" from the synced source.
# The repo's own docker-compose.yml is the *public* install file (publishes
# 8321, binds ./data) and uses the same container_name, so running it here
# would move the container back to 8321 and bind a fresh empty ./data,
# leaving the real database at /opt/chkt-server/data untouched but unused.
set -euo pipefail

HOST="homelab"
SRC="chkt-server-src"        # build context on the host: source only, no compose run
STACK="/opt/stacks/chkt-server"
IMAGE="chkt-server-chkt"     # must match "image:" in the stack file

echo "Syncing source to $HOST:$SRC ..."
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude 'data' --exclude '.env' \
  ./ "$HOST:$SRC/"

echo "Building and starting ..."
ssh "$HOST" SRC="$SRC" STACK="$STACK" IMAGE="$IMAGE" bash -s <<'REMOTE'
set -euo pipefail

if [ ! -f "$STACK/compose.yaml" ]; then
  echo "No stack file at $STACK/compose.yaml — this deploy expects the" >&2
  echo "homelab stack to be authoritative. Nothing changed." >&2
  exit 1
fi

PORT="$(sed -n 's/^PORT=//p' "$STACK/.env" 2>/dev/null | head -n1 || true)"
if [ -z "$PORT" ]; then
  echo "No PORT= in $STACK/.env. Nothing changed." >&2
  exit 1
fi

# The old deploy layout, if it is still lying around, defines the same
# container_name on a different port and data path. Warn loudly: running
# compose in there undoes this deploy and looks exactly like data loss.
if [ -f "$HOME/chkt-server/docker-compose.yml" ]; then
  echo "WARNING: $HOME/chkt-server/docker-compose.yml still exists." >&2
  echo "         It claims container_name chkt-server on port 8321 with its" >&2
  echo "         own ./data. Delete that directory so only the stack file" >&2
  echo "         defines this service." >&2
fi

docker build -t "$IMAGE" "$HOME/$SRC"
docker compose --project-directory "$STACK" -f "$STACK/compose.yaml" up -d
sleep 3
curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null && echo "Healthy on port $PORT."
REMOTE

echo "Done. Rollback: check out an older commit here and rerun this script."
