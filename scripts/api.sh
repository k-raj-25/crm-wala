#!/usr/bin/env bash
# Usage: scripts/api.sh start|stop|restart   (dev API on :5000, pid in /tmp/crm-api.pid)
cd "$(dirname "$0")/../backend" && . .venv/bin/activate && export FLASK_APP=wsgi.py
PID=/tmp/crm-api.pid
stop() { [ -f $PID ] && kill "$(cat $PID)" 2>/dev/null; rm -f $PID; }
start() { setsid nohup flask run -p 5000 > /tmp/crm-api.log 2>&1 < /dev/null & echo $! > $PID; for i in $(seq 1 30); do curl -sf localhost:5000/healthz >/dev/null && return 0; sleep 0.5; done; echo "API failed to start"; tail -20 /tmp/crm-api.log; return 1; }
case "$1" in start) start;; stop) stop;; restart) stop; sleep 1; start;; esac
