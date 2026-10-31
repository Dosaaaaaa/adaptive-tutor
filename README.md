# Adaptive Tutor

An exam-prep tutor that **records what each student knows**, not just what they answered.

A teacher uploads one PDF. The system finds the concepts and how they depend on each other, writes and checks the
questions, and gives the class one link. Students answer one question at a time and say **why** they chose each answer.
The tutor tracks the probability of mastery per concept, spots the misconception behind a wrong reason, and shows the teacher
which concepts to teach again.

The six functions, and nothing else (`SPEC.md` section 0):

1. A concept graph for the syllabus, showing prerequisites.
2. A probability of mastery for every concept, updated after each answer.
3. The difficulty of every question, measured from students' answers.
4. A reason for every answer, and the misconception found in it.
5. All students' data in one database.
6. The weak concepts of the whole class, for the teacher.

Working live- "https://speaks-warrior-shortly-conversations.trycloudflare.com/"
## Run it

You need Python 3.12+ and Node 22+.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # then set TEACHER_PASSWORD and, to build quizzes from PDFs, the free AI keys
cd web && npm ci && npm run build && cd ..
.venv/bin/uvicorn api.main:app --port 8080
```

Open <http://localhost:8080>.

- **Teacher:** *Teacher sign in*, then upload a PDF, choose the number of seats and copy the student link.
  Building a quiz from a PDF takes several minutes and needs a free Gemini key and a free Groq key. Without keys you can still
  use the ready-made quiz and the built-in answer matcher.
- **Student:** open the link (or type the code on the front door), pick a nickname, answer with a reason each time.
  Nothing is revealed during the exam. The score and the concept-by-concept breakdown appear at the end.

No PDF handy? `demo/Electricity_Basics.pdf` is a 5-page example, and the exam form offers a ready-made quiz for it.

## Why a quiz takes minutes, and what makes it faster

Building a quiz from a PDF is about 15 AI calls to write the questions and a few more to check every one of them with a second
AI. On the free plans the limits, not the code, set the pace:

- Groq's free plan gives each model **8,000 tokens a minute and 200,000 a day**. Every call re-sends the PDF's text, so one
  build of a short PDF used to use up most of a day's allowance of the checking model, and the live exam's judge shares it.
- Gemini often answers "high demand" (HTTP 503) for minutes at a time.

What the build does about it: it checks up to 30 questions per call (the PDF is sent once, not once per dozen: about half the
tokens), stops asking a question once its vote is settled (same verdict, fewer calls), writes the concepts and rewrites failed
questions side by side (`BUILD_WORKERS`), switches to the fallback model after 2 failed tries instead of 5, treats a used-up daily
allowance as "switch now" instead of waiting, and can use a second checking model (`VERIFY_FALLBACK_MODEL`). The build report
(`bank/<name>/build_report.md`) lists the seconds per stage and the tokens used. Opening the same PDF again is instant.

What does not help much: asking a thinking model to think less (`GEN_REASONING`, `VERIFY_REASONING`). It halved the answer
tokens in a test, but the answer is only a tenth of what a call costs, so it is off unless you set it.

The real fix is a higher limit: putting a payment method on the Groq account (pay as you go, no monthly fee) lifts the limits
many times over, and a build of a short PDF then costs a few cents. After that, raise `GROQ_RPM` and `BUILD_WORKERS` in `.env`.

## Configuration

Everything is read from `.env` (copy `.env.example`). Environment variables win over `.env`, except the AI keys, which are
read **only** from `.env` so a stray key in your shell can never be used by accident.

| Setting | Meaning |
| --- | --- |
| `TEACHER_PASSWORD` | Password for the teacher area. Required to sign in. |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` | Free AI keys for building quizzes and judging reasons. |
| `TUTOR_MODE` | `all` (default), `teacher`, or `student`. A `student` instance has **no teacher routes at all** (they answer 404). |
| `PUBLIC_URL` | The address students use, so the shared links are right. |
| `STUDENT_PORT` | Port of the student-only instance. A private teacher instance then shows links to that port on this computer's current address. |
| `COOKIE_SECURE`, `TRUST_PROXY` | Set both to `1` behind HTTPS and your own reverse proxy. |
| `ALLOWED_ORIGINS` | Extra origins allowed to send state-changing requests. |
| `SESSION_SECRET` | Signs the teacher's session. Otherwise one is generated and kept in `data/session.key`. |
| `TUTOR_DB` | Path of the SQLite database (default `data/tutor.db`). |

## How it is built

```
tutor/   the brain: mastery (BKT), rounds, reason judge, quiz-bank pipeline, class report. Plain Python, no web code.
api/     FastAPI: student routes and teacher routes over the brain. Security, rate limits, serves the built front end.
web/     React + Vite + TypeScript single-page app. No UI framework, no chart library.
ui/      The original Streamlit apps, kept working for comparison. The web app replaces them.
```

- **Brain.** Three rounds per exam (recall, apply, then follow-ups only for concepts not cleanly answered). A right answer
  with a flawed reason counts as wrong. The reason judge picks from a closed list of misconceptions and must quote the
  student's own words as evidence; the quote is verified in code. Question difficulty is `(right + 1) / (answers + 2)`.
- **API.** Signed expiring cookie for the teacher, sliding-window rate limits, cross-site request check, strict
  content-security-policy, `no-store` on every `/api` response. A student's link carries a long random token and exposes only
  that student's own exam.
- **Front end.** Light and dark themes from design tokens (`web/src/styles/tokens.css`). The teacher's report is built around
  the **class concept map**, drawn left to right so prerequisites come first. State is kept in the address (tab, filters,
  chosen concept), so a reload or a shared link shows the same view. The teacher's screens load as separate chunks, so
  students download about 93 kB of script (gzip).
- **Opening screen.** The logo draws itself and holds for 4 seconds, once per browser tab (a reload does not wait for it, so
  an exam in progress is never delayed). It can be skipped with the button, Escape or a click. Add `?splash=1` to an address
  to see it again, `?splash=0` to hide it. With reduced motion it shows the finished logo without animating.

### Checked

- `pytest`: the brain, the API (26 tests of auth, privacy, limits, uploads, builds) and the legacy apps.
- `npm test`: the concept-map layout, text helpers and API error handling.
- Real-browser runs of the whole student exam and the teacher journey, on desktop and at phone width, in light and dark.
- axe-core on 14 screens in both colour modes: 0 violations. Colour pairings are checked numerically (4.5:1 for text,
  7:1 for body copy, 3:1 for control edges).

## Develop

```bash
.venv/bin/pytest -q                      # Python tests (install requirements-dev.txt and requirements-streamlit.txt)
cd web && npm test && npm run typecheck  # front-end tests and types
cd web && npm run dev                    # http://localhost:5173, forwards /api to the Python server on :8080
```

## Deploy

**Docker (one image):**

```bash
docker build -t adaptive-tutor .
docker run -p 8080:8080 -v tutor-data:/app/data -v "$PWD/.env:/app/.env:ro" adaptive-tutor
# or: docker compose up --build
```

The image is about 180 MB. It was built and run end to end for this repo: the app served, sign-in and the student exam worked, the class report
and CSV came back, and cross-site requests were refused. The container runs as a non-root user (uid 1000 by default) and reads `.env` from the mounted file. If your own user id is
not 1000, build with `--build-arg APP_UID=$(id -u)` (compose: `APP_UID=$(id -u) docker compose up --build`), otherwise it cannot
read a private `.env`.

**A class on one Wi-Fi.** `./run_web.sh` starts two servers over the same database:

- **Students:** `http://<this computer's address>:8080/e/CODE`. This server listens on the network and carries only the exam
  link: it has no teacher pages at all (they answer 404).
- **Teacher:** `http://localhost:8081`. This server listens on this computer only and asks for the password. Its exam cards
  show the student link with the computer's *current* address, so it stays right if the Wi-Fi changes.

If a phone cannot open the link although this computer can, the usual cause is the computer's firewall (on Ubuntu, `ufw` drops
incoming connections by default). Allow the class network on port 8080 only, for example
`sudo ufw allow from 10.83.254.0/24 to any port 8080 proto tcp` (use your own subnet), and remove it afterwards with
`sudo ufw delete allow from 10.83.254.0/24 to any port 8080 proto tcp`. Some guest and school networks also block devices from
talking to each other; a phone hotspot or a home router does not.

**A public link for any network** (free, no account). A Cloudflare quick tunnel gives the app a public https address. It works
from any network and needs no firewall change, but only while the script runs, and the address is new every time. It suits a demo
or a class session, not an exam left open for days (for that, use a host that stays on).

- `./run_web.sh --public` puts the **whole app** on one address: students open `<address>/e/CODE`, the teacher signs in at
  `<address>/teacher`, and the teacher's exam cards show the public student link. The teacher sign-in page is then reachable from
  the internet. What protects it: the teacher password (use a long one), 5 sign-in tries a minute per address, an https-only
  session cookie, and the checks on every request. Anyone who gets in can read every exam, so treat the password like a key.
- `./run_web.sh --public-students` tunnels only the student server. The teacher stays on this computer at `http://localhost:8081`.
- The launcher keeps each server and the tunnel running: if one stops it starts again a second later, so `kill`ing the server to load new code does not take the public link down. A tunnel that does have to be reopened gets a new address, which the exam cards then show (`data/public_url`).

- Install the tool once: download `cloudflared-linux-amd64` from <https://github.com/cloudflare/cloudflared/releases>, compare it
  with the SHA256 in the release notes, make it executable and put it at `~/.cache/cloudflared/<version>/cloudflared` (or on your
  `PATH`, or set `CLOUDFLARED`).
- Anyone with the address and an exam code can join, up to the exam's seat limit, so choose the seats with that in mind.
- Stop it with Ctrl+C, or `./stop_web.sh` if it runs in the background.

**On the internet.** Put it behind HTTPS (a reverse proxy or your host's TLS), then set `PUBLIC_URL`, `COOKIE_SECURE=1` and
`TRUST_PROXY=1`. The safest layout is two instances on one machine over the same database file: a private `TUTOR_MODE=teacher` instance only the
teacher can reach, and a public `TUTOR_MODE=student` instance that carries only the exam link.

## Working together

```bash
git clone https://github.com/Dosaaaaaa/adaptive-tutor.git && cd adaptive-tutor
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt -r requirements-streamlit.txt
cp .env.example .env        # each person uses their own .env with their own free AI keys
cd web && npm ci && npm run build && cd ..
.venv/bin/pytest -q && (cd web && npm test)
```

- Work on a branch and open a pull request into `main`. CI (`.github/workflows/ci.yml`) runs the Python tests and the front
  end's types, tests and build on every push to `main` and on every pull request; please wait for it to pass.
- **Never commit `.env`.** It, `data/`, uploaded PDFs and teacher-built quizzes (`bank/exam_*`) are git-ignored. If a key is ever
  pasted somewhere by mistake, revoke it and make a new one.
- `tutor/` is the brain and its behaviour is specified in `SPEC.md`; change it only with a matching change to the spec and tests.
  The six functions in `SPEC.md` section 0 are the whole scope.

## Privacy

Students are identified by a nickname only. No real names are stored. Teachers see nicknames next to results, and the answers
can be exported as CSV per exam.
