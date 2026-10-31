# CLAUDE.md

Adaptive exam-prep tutor (hackathon). The teacher supplies a PDF. The system builds a quiz bank, tracks each
student's mastery per concept, finds the misconception in each reason, and shows the class-wide weak concepts.

**North star: six functions only.** Concept graph with prerequisites, mastery probability updated per answer,
question difficulty from answers, reason to misconception, one database, teacher sees class-wide weak concepts.
Anything else is out of scope (SPEC.md section 0).

## Status (2026-10-31)
Backend `tutor/`, two Streamlit apps and the exam layer are built (163 tests). Keys are in `.env`; `tutor.smoke` passes
(Gemini writer, Groq checker/judge). The AI pipeline built `bank/electricity_llm` (28 questions, concept map exact).
**Two apps:** teacher `ui/teacher_app.py` (localhost:8501, password `TEACHER_PASSWORD` in `.env`: upload a PDF, create an
exam with a seat limit, get the student link, class report with scores) and student `ui/student_app.py` (0.0.0.0:8502,
link `http://<lan-ip>:8502/?exam=CODE`: take the exam, see the score at the end). Start both with `./run.sh`.
Open: AI judge finds the intended misconception 58% of the time on synthetic reasons (target 80%, never wrong, never
flags sound reasons); Gemini is often 503 (fallback to Groq qwen is configured); real tester data.

## Read on demand (not every session)
- `SPEC.md`: design contract. `PLAN.md`: build order and milestones.
- Do not read `claude-token-optimizer/`, `hallmark/`, `claude-frontend-skills/`, `agent-tutor-skill/`, `graphify/`: vendored tools, not part of the build.
- Design skills `hallmark` and `distinctive-frontend` are installed in `~/.claude/skills/` (2026-10-31). Hallmark's hook installer and image generation are NOT enabled; never run `hallmark/skills/hallmark/scripts/install-hook.mjs` (it edits Claude settings) without being asked.

## Commands
- Python: `.venv/bin/python` (3.12). Tests: `.venv/bin/pytest -q`
- Build a bank: `.venv/bin/python -m tutor.build_bank demo/Electricity_Basics.pdf --name <name>`
- Run both apps: `./run.sh` (teacher on localhost:8501, student on 0.0.0.0:8502). Teacher password is `TEACHER_PASSWORD` in `.env`
- Fake class and text report: `.venv/bin/python -m tutor.simulate --n 14 --report`
- Check keys and models: `.venv/bin/python -m tutor.smoke`. Keys live in `.env`: never print or paste them.

## Rules
- Logic lives in `tutor/`. The Streamlit apps in `ui/` only call `tutor.service/exams/scoring/stats/jobs`. The student app must never import the dashboard (a test checks it).
- The brain (mastery, rounds, service, judge, build pipeline) is not changed by the exam layer: exams only choose the bank and filter the report.
- No feedback to a student during the test. A right answer with a flawed reason counts as wrong.
- Simulated students are always `is_simulated=1` and shown as simulated.

---

**Last Updated**: 2026-10-31
**Optimized with**: [Claude Token Optimizer](https://github.com/nadimtuhin/claude-token-optimizer)
