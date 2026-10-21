#!/bin/sh
# Loads the made-up demo data into the bundled database (docker compose --profile bundled-db).
# Run from the repo root after the stack is up:  ./demo/load-demo-data.sh
# Run it again after each daily update, which clears the parsed data.
set -e
cd "$(dirname "$0")/.."
[ -f .env ] && . ./.env
: "${DB_PASSWORD:?DB_PASSWORD is not set (copy .env.example to .env)}"

run() { docker compose --profile bundled-db exec -T -e MYSQL_PWD="$DB_PASSWORD" db mariadb -uroot "$1"; }
run fqdn_v3  < demo/seed_fqdn_demo.sql
run fqdn_tool < demo/seed_firewall_demo.sql
echo "Demo data loaded."
