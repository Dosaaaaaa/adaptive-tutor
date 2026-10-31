#!/usr/bin/env bash
# Starts the web app the way a class needs it: two servers over the same database.
#   Teacher (private):  http://localhost:8081                    only this computer can open it; it asks for the teacher password
#   Students (network): http://<this computer's address>:8080    the exam link only; this server has no teacher pages at all
#
#   ./run_web.sh            students on the local network
#   ./run_web.sh --public   also a public https link that works from any network (a free Cloudflare quick tunnel; needs the
#                           `cloudflared` program, see README.md "A public link"). The link is new every time and works only
#                           while this script runs. The teacher's exam cards then show the public link.
cd "$(dirname "$0")" || exit 1
mkdir -p data
echo $$ > data/web.pid        # to stop it when it runs in the background: kill $(cat data/web.pid)
trap 'rm -f data/web.pid; kill 0' INT TERM EXIT

tool=""
if [ "$1" = "--public" ]; then
  tool="${CLOUDFLARED:-$(command -v cloudflared || ls -1d "$HOME"/.cache/cloudflared/*/cloudflared 2>/dev/null | tail -1)}"
  if [ ! -x "$tool" ]; then
    echo "cloudflared was not found. See README.md, 'A public link'." >&2
    exit 1
  fi
fi

TUTOR_MODE=student .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8080 --log-level warning &

public=""
if [ -n "$tool" ]; then
  : > data/tunnel.log
  "$tool" tunnel --no-autoupdate --url http://127.0.0.1:8080 >> data/tunnel.log 2>&1 &
  for _ in $(seq 1 60); do
    public=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' data/tunnel.log | head -1)
    [ -n "$public" ] && break
    sleep 1
  done
  [ -n "$public" ] || echo "The public link did not appear within a minute (see data/tunnel.log). The class can still use the network link." >&2
fi

PUBLIC_URL="$public" TUTOR_MODE=teacher STUDENT_PORT=8080 .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8081 --log-level warning &
echo "Teacher:  http://localhost:8081"
echo "Students: http://<this computer's address>:8080/e/CODE${public:+     public: $public/e/CODE}"
wait
