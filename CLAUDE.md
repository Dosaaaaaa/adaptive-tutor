# CLAUDE.md

Adaptive exam-prep tutor. A teacher uploads a PDF, students take the exam from a link, and the system tracks mastery per
concept, finds misconceptions, scores each student and shows the class where it is weak. Six functions only: SPEC.md section 0.

## Layout
- `tutor/` the brain. Do not change its logic. `api/` FastAPI web API. `web/` React front end. `ui/` Streamlit (legacy, running on 8501/8502: do not restart).
- Status and history: PLAN.md section 0. Design contract: SPEC.md.

## Commands
- Tests: `.venv/bin/pytest -q` and `cd web && npm test`
- Web app, one server: `.venv/bin/uvicorn api.main:app --port 8080` (serves `web/dist`). For a class: `./run_web.sh [--public | --public-students]` (default: students :8080 on the network, teacher :8081 private; --public: whole app, teacher included, on one Cloudflare quick-tunnel address). Streamlit: `./run.sh`
- Keys live only in `.env`. Never print or commit them.

## Rules
- Apps call `tutor.service/exams/scoring/stats/jobs` only. Student routes never touch dashboard code.
- No feedback during the test. A right answer with a flawed reason counts as wrong.
- Do not read: `claude-token-optimizer/ hallmark/ claude-frontend-skills/ agent-tutor-skill/ graphify/` (vendored, not part of the build).
- Skills `hallmark` and `distinctive-frontend` are installed. Never run hallmark's `install-hook.mjs` unasked.

---

**Last Updated**: 2026-10-31
**Optimized with**: [Claude Token Optimizer](https://github.com/nadimtuhin/claude-token-optimizer)
