#!/usr/bin/env bash
# Starts the web app the way a class needs it: two servers over the same database.
#   Teacher (private):  http://localhost:8081                    only this computer can open it; it asks for the teacher password
#   Students (network): http://<this computer's address>:8080    the exam link only; this server has no teacher pages at all
# The teacher's exam cards show the student link with this computer's current address, so it stays right if the Wi-Fi changes.
cd "$(dirname "$0")" || exit 1
trap 'kill 0' INT TERM EXIT
TUTOR_MODE=student .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8080 --log-level warning &
TUTOR_MODE=teacher STUDENT_PORT=8080 .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8081 --log-level warning &
wait
