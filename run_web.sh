#!/usr/bin/env bash
# Starts the web app. Three ways to run it:
#
#   ./run_web.sh                  a class on one Wi-Fi: two servers over one database
#                                   Teacher (private):  http://localhost:8081     only this computer; asks for the teacher password
#                                   Students (network): http://<this computer's address>:8080/e/CODE     no teacher pages at all
#   ./run_web.sh --public         the whole app on ONE public https address (a free Cloudflare quick tunnel; needs the
#                                 `cloudflared` program, see README.md "A public link"): students open <address>/e/CODE, the
#                                 teacher signs in at <address>/teacher. The teacher sign-in is then reachable from the
#                                 internet, protected by the teacher password (5 tries a minute per address).
#   ./run_web.sh --public-students   the same tunnel, but only the student server is public; the teacher stays on this computer
#
# Every server and the tunnel is kept running: if one stops (a crash, or a kill on purpose to load new code) it starts again a
# second later and nothing else is disturbed. The public address is new every time a tunnel opens and works only while this
# script runs; the exam cards in the teacher screen follow it (data/public_url). Stop everything with ./stop_web.sh
cd "$(dirname "$0")" || exit 1

mode="${1:-}"
case "$mode" in
  ""|--public|--public-students) ;;
  *) echo "Usage: ./run_web.sh [--public | --public-students]" >&2; exit 2 ;;
esac

tool=""
if [ -n "$mode" ]; then
  tool="${CLOUDFLARED:-$(command -v cloudflared || ls -1d "$HOME"/.cache/cloudflared/*/cloudflared 2>/dev/null | tail -1)}"
  if [ ! -x "$tool" ]; then
    echo "cloudflared was not found. See README.md, 'A public link'." >&2
    exit 1
  fi
fi

mkdir -p data
echo $$ > data/web.pid        # to stop it when it runs in the background: ./stop_web.sh
trap 'rm -f data/web.pid data/public_url; kill 0' INT TERM EXIT
rm -f data/public_url

# runs a command again whenever it stops
keep_running() {
  while true; do
    "$@"
    sleep 1
  done
}

# keeps a tunnel to a local port open and writes its public address and process id to data/public_url
keep_tunnel() {
  while true; do
    : > data/tunnel.log
    "$tool" tunnel --no-autoupdate --url "http://127.0.0.1:$1" >> data/tunnel.log 2>&1 &
    local pid=$! found=""
    for _ in $(seq 1 60); do
      found=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' data/tunnel.log | head -1)
      [ -n "$found" ] && break
      sleep 1
    done
    if [ -n "$found" ]; then
      printf '%s\n%s\n' "$found" "$pid" > data/public_url
      echo "Public address: $found"
    else
      echo "The public address did not appear within a minute (see data/tunnel.log)." >&2
    fi
    wait "$pid"
    rm -f data/public_url
    echo "The tunnel stopped. Opening a new one: the public address will change." >&2
    sleep 2
  done
}

if [ "$mode" = "--public" ]; then
  keep_running env COOKIE_SECURE=1 TUTOR_MODE=all .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8080 --log-level warning &
  keep_tunnel 8080 &
else
  keep_running env TUTOR_MODE=student .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8080 --log-level warning &
  keep_running env TUTOR_MODE=teacher STUDENT_PORT=8080 .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8081 --log-level warning &
  if [ "$mode" = "--public-students" ]; then
    keep_tunnel 8080 &
  fi
fi

public=""
if [ -n "$mode" ]; then
  for _ in $(seq 1 70); do
    if [ -s data/public_url ]; then public=$(head -1 data/public_url); break; fi
    sleep 1
  done
fi
if [ "$mode" = "--public" ]; then
  echo "Students: ${public:-http://<this-computer-address>:8080}/e/CODE"
  echo "Teacher:  ${public:-http://localhost:8080}/teacher"
else
  echo "Teacher:  http://localhost:8081"
  echo "Students: http://<this-computer-address>:8080/e/CODE${public:+     public: $public/e/CODE}"
fi
wait
