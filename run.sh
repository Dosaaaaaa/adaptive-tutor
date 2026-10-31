#!/usr/bin/env bash
# Starts both apps.
#   Teacher app  http://localhost:8501   private: only this computer can open it, and it asks for the teacher password
#   Student app  http://<this computer's address>:8502/?exam=CODE   what students open (the link is shown on each exam)
cd "$(dirname "$0")" || exit 1
trap 'kill 0' INT TERM EXIT
.venv/bin/streamlit run ui/teacher_app.py --server.port 8501 --server.address localhost &
.venv/bin/streamlit run ui/student_app.py --server.port 8502 --server.address 0.0.0.0 &
wait
