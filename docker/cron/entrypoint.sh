#!/bin/sh
# Install the schedule from the environment, then run crond in the foreground.
set -e

HOUR="${DAILY_UPDATE_HOUR:-6}"
MINUTE="${DAILY_UPDATE_MINUTE:-0}"
TARGET="${BACKEND_URL:-http://backend:5432}"

echo "${MINUTE} ${HOUR} * * * curl -s --max-time 900 '${TARGET}/api/download/daily?auto_parse=true&triggered_by=cron' >> /data/daily_update.log 2>&1" > /etc/crontabs/root

echo "Daily update scheduled at ${HOUR}:$(printf '%02d' "${MINUTE}") ${TZ:-UTC} -> ${TARGET}"
crond -f -l 8
