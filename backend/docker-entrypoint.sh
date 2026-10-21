#!/bin/sh
# Wait for the database, then make sure the schema exists before serving.
#
# main_ltm_fw.py only calls create_all() under __main__, so gunicorn would
# otherwise start against an empty database. Doing it here runs it exactly
# once, rather than racing across four workers.
set -e

echo "Waiting for database at ${DB_HOST:-db}:${DB_PORT:-3306}..."
for i in $(seq 1 60); do
    if python -c "
import socket, sys, os
s = socket.socket()
s.settimeout(2)
try:
    s.connect((os.getenv('DB_HOST', 'db'), int(os.getenv('DB_PORT', '3306'))))
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "Database is up after ${i}s"
        break
    fi
    [ "$i" = "60" ] && echo "WARNING: database still unreachable after 60s; starting anyway"
    sleep 1
done

echo "Ensuring schema exists..."
python -c "
from main_ltm_fw import app
from model import db
with app.app_context():
    db.create_all()
print('Schema ready')
" || echo "WARNING: create_all failed; continuing (dump restore may provide the schema)"

exec "$@"
