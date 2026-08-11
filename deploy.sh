#!/usr/bin/env bash
# Deploy CHKT Server to the VPS. One command: ./deploy.sh
#
# Target: the homelab, reached over Tailscale via the "homelab" ssh alias.
set -euo pipefail

HOST="homelab"
DIR="chkt-server"

echo "Syncing code to $HOST:$DIR ..."
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude 'data' --exclude '.env' \
  ./ "$HOST:$DIR/"

echo "Building and starting ..."
ssh "$HOST" "set -e; cd $DIR
  if [ ! -f .env ]; then
    echo \"SECRET_KEY=\$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')\" > .env
    echo "CHKT_INSECURE_COOKIES=1" >> .env
    chmod 600 .env
    echo 'Generated a fresh SECRET_KEY (first deploy).'
  fi
  docker compose up -d --build
  sleep 3
  curl -sf http://127.0.0.1:8321/healthz && echo ', healthy.'"

echo "Done. Rollback: ssh $HOST 'cd $DIR && git checkout <old-commit>' then redeploy,"
echo "or simply rerun this script from an older checkout of this repo."
