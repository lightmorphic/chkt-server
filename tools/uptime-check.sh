#!/usr/bin/env bash
# Tiny uptime check for Chkt Server. Run from cron on ANY OTHER machine
# (checking a server from itself proves nothing), e.g. every 5 minutes:
#
#   */5 * * * * /path/to/uptime-check.sh https://chkt.example.com you@example.com
#
# Emails once when the site goes down and once when it recovers, using the
# machine's own mail command.
set -u

URL="${1:?usage: uptime-check.sh <url> <email>}"
EMAIL="${2:?usage: uptime-check.sh <url> <email>}"
STATE="/tmp/chkt-uptime-state"

if curl -sf --max-time 15 "$URL/healthz" > /dev/null; then
    if [ -f "$STATE" ]; then
        rm -f "$STATE"
        echo "Chkt is back up at $(date)." | mail -s "Chkt: back up" "$EMAIL"
    fi
else
    if [ ! -f "$STATE" ]; then
        touch "$STATE"
        echo "Chkt at $URL stopped answering at $(date)." | mail -s "Chkt: DOWN" "$EMAIL"
    fi
fi
