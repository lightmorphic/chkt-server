#!/usr/bin/env bash
# Deploy CHKT Server to the VPS. One command: ./deploy.sh
#
# Expects an SSH host alias "chkt-deploy" in ~/.ssh/config pointing at the
# server (LM002, 77.74.199.121) with its own deploy key, e.g.:
#
#   Host chkt-deploy
#       HostName 77.74.199.121
#       User root
#       IdentityFile ~/2-Data/SSH/lightmorphic-chkt-vps-deploy
#       IdentitiesOnly yes
#       IdentityAgent none
#
set -euo pipefail

HOST="chkt-deploy"
DIR="/srv/chkt-server"

echo "Syncing code to $HOST:$DIR ..."
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude 'data' --exclude '.env' \
  ./ "$HOST:$DIR/"

echo "Building and starting ..."
ssh "$HOST" "set -e; cd $DIR
  if [ ! -f .env ]; then
    echo \"SECRET_KEY=\$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')\" > .env
    chmod 600 .env
    echo 'Generated a fresh SECRET_KEY (first deploy).'
  fi
  docker compose up -d --build
  sleep 3
  curl -sf http://127.0.0.1:8321/healthz && echo ', healthy.'"

echo "Done. Rollback: ssh $HOST 'cd $DIR && git checkout <old-commit>' then redeploy,"
echo "or simply rerun this script from an older checkout of this repo."
