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
# The public address is new every time and works only while this script runs.
cd "$(dirname "$0")" || exit 1

mode="${1:-}"
case "$mode" in
  ""|--public|--public-students) ;;
  *) echo "Usage: ./run_web.sh [--public | --public-students]" >&2; exit 2 ;;
esac

mkdir -p data
echo $$ > data/web.pid        # to stop it when it runs in the background: kill $(cat data/web.pid)
trap 'rm -f data/web.pid; kill 0' INT TERM EXIT

tool=""
if [ -n "$mode" ]; then
  tool="${CLOUDFLARED:-$(command -v cloudflared || ls -1d "$HOME"/.cache/cloudflared/*/cloudflared 2>/dev/null | tail -1)}"
  if [ ! -x "$tool" ]; then
    echo "cloudflared was not found. See README.md, 'A public link'." >&2
    exit 1
  fi
fi

# opens the tunnel to a local port and prints the public address it was given (nothing if none appeared within a minute)
open_tunnel() {
  : > data/tunnel.log
  "$tool" tunnel --no-autoupdate --url "http://127.0.0.1:$1" >> data/tunnel.log 2>&1 &
  local found=""
  for _ in $(seq 1 60); do
    found=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' data/tunnel.log | head -1)
    [ -n "$found" ] && break
    sleep 1
  done
  [ -n "$found" ] || echo "The public address did not appear within a minute (see data/tunnel.log)." >&2
  printf '%s' "$found"
}

if [ "$mode" = "--public" ]; then
  public=$(open_tunnel 8080)
  # one server for everyone; the tunnel brings people in over https, so the teacher's cookie is marked secure
  PUBLIC_URL="$public" COOKIE_SECURE=1 TUTOR_MODE=all .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8080 --log-level warning &
  echo "Students: ${public:-http://<this-computer-address>:8080}/e/CODE"
  echo "Teacher:  ${public:-http://localhost:8080}/teacher"
  wait
  exit 0
fi

TUTOR_MODE=student .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8080 --log-level warning &
public=""
[ "$mode" = "--public-students" ] && public=$(open_tunnel 8080)
PUBLIC_URL="$public" TUTOR_MODE=teacher STUDENT_PORT=8080 .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8081 --log-level warning &
echo "Teacher:  http://localhost:8081"
echo "Students: http://<this-computer-address>:8080/e/CODE${public:+     public: $public/e/CODE}"
wait
