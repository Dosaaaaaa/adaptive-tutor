# Build plan

Companion to `SPEC.md`. The spec says *what*. This file says *in what order*, *who does it*, and *how we know it works*.
Rough estimates: the main uncertainty is how well the free AI models follow the output formats.

## 0. Status (2026-10-31, late): web app

**The Streamlit screens now have a full web replacement: `api/` (FastAPI) and `web/` (React + Vite + TypeScript), same brain.**
Run: `.venv/bin/uvicorn api.main:app --port 8080`, open http://localhost:8080 (teacher password in `.env`). The Streamlit apps
still work and are not required.

- Student: front door, join by link, one question at a time with a reason or "I am guessing", score and concept breakdown at the end.
- Teacher: sign in, exams with PDF upload, seat limit, link and build progress, then the class report (re-teach cards, concept map,
  scores, question difficulty, mistakes, data, test students).
- Checked: 199 Python tests, 38 front-end tests, Hallmark lint clean, axe-core clean on 14 screens in light and dark, real-browser
  runs of both journeys on desktop and phone width. README covers Docker and CI; the code is committed locally, not pushed.
- On GitHub: private repo https://github.com/Dosaaaaaa/adaptive-tutor, CI green (Python tests; front end types, tests, build).
  An opening logo screen (4 seconds, once per tab) was added. For a class on one Wi-Fi run `./run_web.sh` (students :8080, teacher :8081).
- Open: add the second collaborator (needs their GitHub username), a firewall rule so phones can open the student link
  (`sudo ufw allow from <subnet> to any port 8080 proto tcp`), where to host it online, the judge re-evaluation.

## 0a. Earlier status (2026-10-31, evening)

**Built and tested: 163 tests, real browser runs of both apps.**

| Question | Answer |
|---|---|
| Where do I upload a PDF of new concepts? | Teacher app (http://localhost:8501, password in `.env`) > Exams > Create a new exam > "Upload a PDF". The quiz is built in the background (about 13 minutes for 5 pages). The same file uploaded again is ready at once. |
| How do students get in? | Each exam has a link: `http://<this computer's address>:8502/?exam=CODE`. They pick a nickname, take the exam, and see their score at the end. |
| Who sees the dashboard? | Only the teacher: it is a separate app that listens on this computer only, and it asks for the password. The student app has no route to it. |
| How many students? | The teacher sets the number of places when creating the exam. The link refuses more students than that. |
| Is the brain changed? | No. `mastery`, `rounds`, `service`, `judge` and the build pipeline are untouched. The exam layer adds a table, an exam filter on the report, and new modules (`exams`, `scoring`, `jobs`). |

Open (superseded): the first judge check said 58%, but that came from flawed synthetic reasons; on valid reasons it named the right
misconception 26 of 26 and never flagged a sound reason. A fresh run of the evaluation is still pending. Gemini is often unavailable (503): the fallback to Groq `qwen3.8-27b` is set in `.env`.
Not verified: reaching the student link from another device (this computer's firewall was not tested), and a real build
started from the upload button with the live AI (the reuse path and the background process are tested). Real tester data.

## 1. Do now (you, about 30 minutes)

- [ ] **Make the API keys** (details in section 2) and put them in `.env`. Never paste a key into chat.
- [ ] **Open `demo/Electricity_Basics.pdf`.** Confirm you are happy with it as the demo document.
- [ ] **Tell me three facts:** the hackathon deadline, how many people are on the team, and where the demo runs
      (your laptop, a projector, remote).
- [ ] **Line up 10 to 16 testers** for one 15-minute slot each, in three groups (section 6). This is the slowest
      part of the project, so start it first.
- [ ] **Decide on `git init` inside `Hackton/`.** The home folder is the git root today. A `.gitignore` already
      protects `.env`, but a separate repo is cleaner for submission.

## 2. Keys to create

| Key | Where | Needed? | Used for |
|---|---|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey (sign in with Google, "Create API key") | **Yes** | Generator: concepts, misconceptions, questions |
| `GROQ_API_KEY` | https://console.groq.com/keys (the signup may ask for phone verification) | **Yes** | Verifier (build checks) and the reason judge |
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys | Optional | Fallback only. Low daily cap. Never gets student text. |

Do **not** create keys for Mistral (its free tier reportedly needs opt-in to training), or anything for
embeddings, vector databases or OCR: we do not use them.

How to hand them over safely: `cp .env.example .env`, paste the keys into `.env`. I run `python -m tutor.smoke`,
which prints only OK or FAIL and model names, never the keys.

Please also read the **rate-limit numbers** shown in each dashboard (requests per minute, per day, tokens per
minute) and tell me. Public sources disagree, so I will set the throttle from your real numbers.

## 3. Milestones: what you will see

| M | Done when | Block |
|---|---|---|
| **M1 Bank built** | One command turns the PDF into 5 concepts, 5 edges and about 30 questions. At least 27 pass the automatic checks. `build_report.md` says what was rejected and why. | 0 to 2 |
| **M2 You can take the test** | In the browser you do rounds 1 to 3. Rows appear in the database. The learner-model panel shows mastery moving after each answer. | 3 |
| **M3 Reasons understood** | A flawed reason gets a named misconception and a quote. A right answer with a wrong reason is not credited. `eval` prints the judge scores. | 4 |
| **M4 Teacher screen** | The dashboard on 14 simulated students: ranked cards, START HERE, concept map, question table. A stranger passes the 10-second test. | 5 |
| **M5 Real class, rehearsed** | 10 to 16 real answer sets in the database. The 3-minute demo runs end to end. Backups are ready. | 6, 7 |

## 4. Work blocks

Priority: **P0** = needed for functions 1 to 6. **P1** = should have. **P2** = nice to have.

| Block | Tasks | Est. | Who | Needs |
|---|---|---|---|---|
| **0 Setup** | `.venv` (3.12), `requirements.txt`, package skeleton, `smoke` (keys, JSON mode, model list), freeze JSON and DB contracts (SPEC 5.4, 10) | 0.5 h | Claude. You: keys | Keys |
| **1 Bank generation** (P0) | `llm.py` (cache, throttle, repair), `extract.py`, `quotes.py`, build steps 1 to 3, first `bank/` | 2.5 h | Claude | Block 0 |
| **2 Checks** (P0 and P1) | Grounding, graph, blind solve (P0). One-right-answer, tags, leak and duplicate, option rules (P1). Repair loop, `build_report.md`, `eval` for the bank | 2.5 h | Claude | Block 1 |
| **3 Student runtime** (P0) | `db.py`, `mastery.py` plus unit tests, `rounds.py`, `1_Student.py`, results page, learner-model side panel | 3.5 h | Claude | First bank from Block 1 |
| **4 Reason judge** (P0) | `judge.py` with validation, wire into rounds (round 3 selection), `OTHER` capture, judge eval with synthetic reasons | 3 h | Claude | Block 3 |
| **5 Teacher side** (P0) | `simulate.py`, `stats.py`, `2_Teacher.py` (cards, map, questions) now. Mistakes, Students and Data tabs (P1). | 4 h | Claude | Schema only, so it runs **in parallel** with 3 and 4 |
| **6 Real data** | Run the app for testers. Ingest, fix problems, check the dashboard against the known reading groups | 1 h me, 1 evening you | Both | M2 and M3 |
| **7 Polish** | Seed `tutor.db`, commit the bank, screen recording, rehearse, fix wording on the dashboard | 2.5 h | Both | M4 |

**Totals:** about 19 h of work in sequence, about 13 h on the critical path (0, 1, 3, 4, 6, 7) because blocks 2 and 5
run alongside. The dependency that matters: **blocks 2, 3 and 5 only need the contracts frozen in block 0.**
With teammates, split into three tracks: Bank (1, 2), Student (3, 4), Teacher (5). They meet at the database.

**Suggested schedule (if two days are available):**
- Day 1: blocks 0 to 3. End state: M1 and M2.
- Day 2: blocks 4 and 5, then start testers in the evening. End state: M3 and M4.
- Morning of day 3: blocks 6 and 7. End state: M5.

**If you have one day:** P0 only, skip tester groups (use simulated plus 4 to 5 teammates). It is tight at about 13 h.

## 5. Order of risk: check the biggest unknown first

1. **End of block 1: look at the generated questions.** If the free models write poor questions, switch early to
   Plan B (I generate the demo bank in Claude Code, then run it through the same checks). Do not find this out on day 2.
2. **Block 2:** the blind-solve pass rate tells us how trustworthy the bank is. Aim for at least 90%.
3. **Block 4:** the judge scores. Below 80% misconception recovery, tighten the prompt and the misconception texts.

## 6. Real data collection

Three groups, so the dashboard can be checked against something we *know*. The class code sets the group tag.

| Class code | Group | Condition | People | Expected on the dashboard |
|---|---|---|---|---|
| `DEMO-ALL` | `read_all` | Read all 5 pages for 5 minutes first | 4 to 5 | Mostly green |
| `DEMO-P13` | `read_p1_3` | Read pages 1 to 3 only | 4 to 5 | C4 and C5 weak |
| `DEMO-COLD` | `cold` | Read nothing | 4 to 5 | Weak across the map, with natural misconceptions |

- Everyone uses a **nickname**. No real names, no personal details in the reason box.
- **Same room:** run `streamlit run ui/Home.py --server.address 0.0.0.0`. Testers open `http://<laptop-ip>:8501`.
- **Remote testers:** need a tunnel (none is installed here yet; I will set one up). Free hosting such as Streamlit
  Community Cloud keeps its disk only temporarily, so it can lose the SQLite file.
- Report these as "real, n = ...". Simulated students are always labelled and never counted as real.

## 7. Demo, 3 minutes

| Time | Show | Function |
|---|---|---|
| 0:00 | Drop in the PDF. The concept graph and the build report appear (30 questions generated, N checked, M repaired). | 1 |
| 0:40 | A student answers a few questions. Mastery bars move after each answer. | 2 |
| 1:15 | One answer with a flawed reason. A named misconception and the student's own words appear. | 4 |
| 1:50 | Teacher dashboard: top card, START HERE, concept map. | 5, 6 |
| 2:30 | Questions tab: the hardest question, with how many students saw it. | 3 |
| 2:50 | Closing line: no teacher approved anything. The only input was a PDF. | all |

## 8. Cut list if time runs short (in this order)

1. Students tab. 2. Distractor-count table. 3. CSV export. 4. Round-3 value chart in `eval`. 5. OpenRouter fallback.
6. Leak and duplicate check (keep grounding and blind solve).

**Never cut** anything that traces to functions 1 to 6.

## 9. Decisions I made for you (tell me if you disagree)

- Demo topic: **electricity basics** (general, school level, with well-known misconceptions, and the same kind of
  syllabus the problem statement mentions).
- Streamlit for both screens. Python 3.12. SQLite.
- No feedback until the end of the test. A reason is required on every answer (6 or more words, or tick "guessing").
- Mastery defaults `p0 = 0.30`, `guess = 0.25`, `slip = 0.10`. Class thresholds 75% and 50%.
- No spaced repetition, no vector search, no outside resources. They are not in the six functions.
