#!/usr/bin/env bash
# Stops what run_web.sh started: the launcher with its servers and tunnel, and a server restarted by hand (data/web-server.pid).
cd "$(dirname "$0")" || exit 1
for f in data/web.pid data/web-server.pid; do
  if [ -f "$f" ]; then
    pid=$(cat "$f")
    kill "$pid" 2>/dev/null && echo "stopped $f (pid $pid)"
    rm -f "$f"
  fi
done
