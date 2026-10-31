# Adaptive Exam-Prep Tutor: Spec (v1, demo scope)

## 0. North star: do not drift

> Generic AI tutors answer questions. They do not record what a student knows.
> Teams must add these functions to the current tutor method:
> 1. Make a concept graph for one syllabus. Show which concepts must come before others.
> 2. Calculate the probability of mastery for each concept. Update it after each answer.
> 3. Measure the difficulty of each question from the answers of students.
> 4. Ask the student for the reason for each answer. Find the misconception in that reason.
> 5. Keep the data of all students in one database.
> 6. Show the teacher the weak concepts of the full class.

**Out of scope** (decided; do not add): spaced repetition, vector search or embeddings, outside learning
resources, logins, any teacher approval step, mobile app. Every module below traces to functions 1 to 6
(table in section 13). If a task does not trace to one, skip it.

**The teacher's only job: supply a PDF.** Concepts, graph, questions, answers and misconceptions are
generated and checked automatically.

## 1. Demo scope

| Item | Demo value | Scale value (config only) |
|---|---|---|
| PDF | `demo/Electricity_Basics.pdf`, 5 pages | 30 to 40 pages |
| Concepts (`MAX_CONCEPTS`) | 5 | 12 to 15 |
| Questions per concept | 6 = 2 recall, 2 apply, 1 tiebreak, 1 simple | same |
| Bank size | 30 questions, 4 options each | 72 to 90 |
| Rounds | 3 | 3 |
| Students | 10 to 16 real, plus simulated ones labelled as such | 30 to 60 |
| Questions per student | 20 (rounds 1 and 2) plus 2 per weak concept (round 3, at most 10) | 24 to 30 per round |

Demo graph (parent comes before child): C1 Current to C2 Voltage and to C3 Resistance; C2 and C3 to
C4 Ohm's law; C4 to C5 Series circuits. Ground truth: `demo/expected.json`.

## 2. System at a glance

```
OFFLINE, once per PDF (cached by PDF hash)
 PDF -> extract text (page markers) -> 1 concepts + prerequisite edges
     -> 2 three misconceptions per concept -> 3 six questions per concept
     -> 4 AUTOMATIC CHECKS (second model family) -> bank/<hash>/*.json + build_report.md

RUNTIME
 Student page (Streamlit)  -> round engine -> answers + reason -> SQLite (tutor.db)
        mastery (BKT, code, instant)  <-- after every answer
        reason judge (LLM, batched)   <-- at the end of each round
 Teacher page (Streamlit)  <- reads SQLite only: cards, concept map, question table, mistakes
```

## 3. Stack and layout

- Python **3.12** in `.venv` (system default is 3.14.4. I have not verified wheels for this stack on 3.14).
- Streamlit (UI, multipage), SQLite from the standard library (WAL mode), pydantic, `requests`, PyMuPDF, pytest.
  **Built as a thin HTTP client, not the `openai` SDK**: the three free providers share the same
  `/chat/completions` protocol, so one small wrapper (`tutor/llm.py`) gives explicit control of retries and
  `Retry-After`, and is easy to test. The provider base URLs are from memory: `smoke` confirms them once keys exist.
  The concept map is a DOT string given to `st.graphviz_chart` (rendered in the browser, no system Graphviz needed).

```
Hackton/
  SPEC.md  PLAN.md  .env.example  .gitignore  requirements.txt
  demo/      Electricity_Basics.pdf  expected.json  make_demo_pdf.py
  tutor/     config.py llm.py extract.py quotes.py build_bank.py gates.py mastery.py
             rounds.py judge.py stats.py db.py simulate.py eval.py smoke.py  prompts/*.txt
  ui/        Home.py  pages/1_Student.py  pages/2_Teacher.py
  bank/<pdf_hash>/   concepts.json misconceptions.json questions.json build_report.md   (committed)
  data/      tutor.db   (git-ignored)
  tests/
```

Commands: `python -m tutor.smoke` (keys, JSON mode, model list) | `python -m tutor.build_bank <pdf>` |
`python -m tutor.simulate --n 14 --seed 7` | `python -m tutor.eval` | `streamlit run ui/Home.py`.

## 4. Providers, keys, limits

| Role | Provider | Used for |
|---|---|---|
| Generator | Google Gemini (AI Studio free key) | build stages 1 to 3, synthetic reasons for tests |
| Verifier and runtime judge | Groq (an open-weight model) | build stage 4, the reason judge |
| Fallback | OpenRouter `:free` | only when one of the above fails; never for student text |

Rules for `tutor/llm.py` (one wrapper for all providers):
1. One function: `call_json(role, prompt, schema) -> dict`. Parse, validate with pydantic, repair once, then raise.
2. **Disk cache** keyed by hash of (model, prompt). Rebuilds and tests cost no quota.
3. **Throttle and backoff**: honour `Retry-After` on HTTP 429. Free tiers also cap tokens per minute.
4. Send only the pages a step needs. Whole-PDF calls only for concepts and graph, and for blind solving.
5. At start-up, assert that the verifier's model family differs from the generator's.
6. Model names are **not hard-coded now**: free-tier model lists change. `smoke` lists the available
   models, runs a JSON-mode test and writes `GEN_MODEL` and `VERIFY_MODEL` to `.env`.
7. **API keys are read only from `.env`**, never from the shell environment. (A stale `GEMINI_API_KEY` exported by
   another tool in `~/.bashrc` was picked up by the first `smoke` run, which is why.) `.env` also wins over the shell
   for models and providers. `smoke` tells you when it ignores a shell key.
8. Student text goes only to the judge provider. Students use nicknames, never real names. I have not
   verified any provider's data terms: check them before using real student text.

Budget: build about 40 to 50 calls once. Runtime at most 3 judge calls per student (one per round).

## 5. Build pipeline (offline)

### 5.1 Steps

| # | Step | Calls | Output |
|---|---|---|---|
| 0 | Extract text per page with PyMuPDF. Insert `[PAGE n]` markers. | 0 | `pages.json` |
| 1 | Concepts (at most `MAX_CONCEPTS`), each with page and a quote, plus prerequisite edges | 1 | `concepts.json` |
| 2 | Three misconceptions per concept, each with the PDF quote that contradicts it | 5 | `misconceptions.json` |
| 3 | Six questions per concept (section 5.3) | 5 | `questions.json` |
| 4 | Automatic checks and repair (section 5.2) | about 30 | `build_report.md` |

Question prompts embed the rules from `~/.claude/skills/learn/references/quiz-rules.md` (no hints, no
"(Recommended)", plausible distractors, neutral option text, mixed question types).

### 5.2 Automatic checks (they replace the teacher)

| Check | How | Fail action |
|---|---|---|
| Grounding | Every quote (concept, misconception contrast, correct answer) appears in the PDF text. Match after NFKC normalisation, whitespace collapse and lower-casing. | Regenerate item |
| Graph | No cycles, every concept connected, at most `MAX_CONCEPTS`, every edge has a reason | Auto-repair: drop the weakest edge on a cycle; merge extra concepts |
| Blind solve | The verifier model sees the PDF and the question, not the key. Three runs, majority must equal the key. | Regenerate question |
| One right answer | Verifier marks each option "supported by the PDF" yes or no. Exactly one yes, and it is the key. | Rewrite the distractors |
| Distractor tags | Every tag is `correct`, `other` or a valid misconception id (**blocks**). Having at least one misconception-tagged distractor is only a **warning**: numeric and formula questions have no natural tag (the gold bank has 23 of 30 tagged). | Retag or rewrite |
| Leak and duplicate | One call over the whole bank: no question reveals another's answer, and no two questions test the same fact | Drop the later question |
| Option rules (code) | 4 options, unique, no "all/none of the above", correct option not the longest, lengths within 2x | Fix or regenerate |

Up to 3 attempts per question, then drop it. If a concept ends with fewer than 1 question per round, mark it
`low_confidence` in the report. The build never blocks on a human. Target: at least 90% of the 30
questions pass.

### 5.3 Question set per concept

| kind | Round | Purpose |
|---|---|---|
| `recall` x2 | 1 | Does the student know the fact? |
| `apply` x2 | 2 | Can the student use it in a new situation (numbers, scenario)? |
| `tiebreak` x1 | 3 | Fresh question at the same level |
| `simple` x1 | 3 | Easier check, to tell "partial" from "missing" |

### 5.4 Bank contract (`questions.json`, one item)

```json
{
  "id": "C5-apply-1", "concept_id": "C5", "kind": "apply", "round": 2,
  "stem": "A 12 V cell drives two resistors in series, 4 ohm and 8 ohm. What is the potential difference across the 8 ohm resistor?",
  "options": [
    {"key": "A", "text": "8 V", "tag": "correct"},
    {"key": "B", "text": "12 V", "tag": "M5.3"},
    {"key": "C", "text": "6 V",  "tag": "M5.2"},
    {"key": "D", "text": "4 V",  "tag": "other"}
  ],
  "answer_key": "A",
  "rationale": "R total = 12 ohm, I = 1 A, V = I x R = 8 V.",
  "evidence": {"page": 5, "quote": "Across the 8 Ω resistor: V = 1 × 8 = 8 V."},
  "checks": {"grounded": true, "blind_votes": ["A", "A", "A"], "supported_options": ["A"], "leak": false}
}
```

`concepts.json`: `{concepts: [{id, name, summary, page, quote}], edges: [{parent, child, why}]}`.
`misconceptions.json`: `[{id: "M5.1", concept_id, statement, contrast_quote}]`.
Option order is shuffled per student at runtime. The stored `option_order` and `chosen_tag` keep results comparable.

## 6. Round engine (`rounds.py`)

- Round 1 = all `recall` questions (10). Round 2 = all `apply` questions (10).
- After round 2, the judge runs (section 8). A concept is a **clean sweep** if all 4 answers are *credited*
  correct. Round 3 = the `tiebreak` and `simple` questions of every concept that is not a clean sweep.
  No flagged concept means the student is finished.
- Order: interleave concepts and shuffle (seeded by student and round), so two questions on one concept are
  never back to back.
- **No feedback during the test.** Show correct answers, rationales and PDF page numbers only on the results
  page after the last round. Otherwise round 2 measures memory of round 1.
- Every student gets the same questions (needed for difficulty). Only order differs.
- Answer screen: question, 4 options, a text box starting "I chose this because...", and a checkbox
  "I am guessing". Reason needs at least 6 words unless the guess box is ticked.
- State lives in the database, so a page reload resumes (`?sid=` in the URL).

## 7. Learner model (`mastery.py`): function 2

Bayesian Knowledge Tracing, learning rate 0 inside the test (no feedback is shown, so nothing is learned).
Defaults (assumptions, to be tuned on simulation): `p0 = 0.30`, `guess = 0.25`, `slip = 0.10`.

```
credited_correct -> logit += w * ln((1 - slip) / guess)      = ln 3.6
credited_wrong   -> logit += w * ln(slip / (1 - guess))      = ln 0.1333
w = 0.5 if the student ticked "I am guessing" else 1
p = sigmoid(logit);  start logit = ln(p0 / (1 - p0))
```

- Updated **after every answer** from the answer log (replay, so it is idempotent). `mastery_log` stores p
  after each answer, for the live panel and the audit trail.
- "Right for the wrong reason" (section 8) is credited **wrong**.
- Every concept is measured directly, so there is **no propagation** along the graph in v1. The graph is used
  for the dashboard.
- State: `p >= 0.85` Understood, `0.40 <= p < 0.85` Shaky, else Missing. Thresholds in `config.py`.

Unit-test fixtures (defaults, no guess ticks):

| Credited answers | p | State |
|---|---|---|
| 4 of 4 | 0.986 | Understood (no round 3) |
| 3 of 4 | 0.727 | Shaky, goes to round 3 |
| 2 of 4 | 0.090 | Missing, goes to round 3 |
| 3 of 4, then 2 of 2 in round 3 (5 of 6) | 0.972 | Understood |
| 3 of 4, then 1 of 2 (4 of 6) | 0.561 | Shaky |
| 3 of 6 | 0.045 | Missing |

A pure guesser gets 4 of 4 with chance 0.4%, and 5 or more of 6 with chance 0.5%.
A knower with a 10% slip rate gets 4 of 4 with chance 66%, which is why round 3 exists.

## 8. Reason judge (`judge.py`): function 4

**Inputs per answer:** question stem, chosen option, whether it is correct, the correct option, the student's
reason, the guess flag. **Per concept:** the misconception list (ids and statements) and the concept's page text.

**Output (JSON list):** `{answer_id, verdict: sound|misconception|guess|unclear, misconception_id: "M5.1"|"OTHER"|null,
other_text, evidence_quote, confidence}`.

**Prompt rules:** choose only an id from the list, or `OTHER`. Judge the reasoning, not the option. Copy
`evidence_quote` exactly from the student's text. An empty or vague reason ("idk", "I just picked it") is
`guess` or `unclear`. A correct choice with reasoning that contradicts the PDF is `misconception`.

**Validation in code (the AI is not trusted):**
1. `evidence_quote` must appear in the student's reason (normalised), otherwise verdict becomes `unclear`.
2. `confidence < 0.6` becomes `unclear`. An unknown id becomes `OTHER`.
3. Calls are batched: one call per student per round. If the call fails or returns nothing usable, the **lexical judge**
   (no AI, `source = lexical`) labels that round instead, so the test never stops. It compares the reason with each
   misconception *and* with the question's explanation, so a correct reason that shares words with a misconception is
   not flagged. It is weak by design and every row records its `source` (`llm`, `lexical`, `rule`, `none`).
4. `credit = is_correct AND verdict != misconception`.

| Choice | Reason | Meaning | Mastery |
|---|---|---|---|
| Wrong | matches that option's tag | Confirmed misconception | down |
| Right | sound | Understood | up |
| **Right** | **flawed** | **Right for the wrong reason** | **counted wrong** |
| Wrong | "I guessed" | Guess | normal wrong |
| Any | too vague | Unclear | choice only |

Wrong options carry a misconception tag from the bank, so even without the AI the choice names a likely
misconception. The AI adds what the tag cannot see: the actual words and the right-for-wrong-reason cases.
`OTHER` texts are kept, and repeated ones are shown to the teacher.

## 9. Question difficulty (`stats.py`): function 3

Per question: `n` students who saw it, `k` correct (credited). `p = (k + 1) / (n + 2)`.
Label: Easy `p >= 0.75`, Medium `0.45 <= p < 0.75`, Hard `p < 0.45`. Always show `n`.

Flags (the data checks the AI-written bank):
- **Check this question**: `p < 0.25` with `n >= 8` (below chance: wrong key or a distractor that lures everyone).
- **Too easy**: `p > 0.95` with `n >= 10`.
- **Order broken**: a `simple` question has a lower `p` than the mean of its concept's recall and apply questions.
- Distractor counts per option tag.

Round 3 questions are seen only by students who struggled earlier, so their `p` is biased low. Show `n` and say so.

## 10. Database (`db.py`): function 5

One SQLite file, `data/tutor.db`, WAL mode, short transactions.

```sql
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);                       -- which bank this database holds
CREATE TABLE students(id TEXT PRIMARY KEY, nickname TEXT, class_code TEXT, is_simulated INTEGER DEFAULT 0,
                      group_tag TEXT, status TEXT DEFAULT 'in_progress',   -- 'done' when the last round is judged
                      judged_round INTEGER DEFAULT 0, round3_plan TEXT,    -- plan frozen once made, so a re-judge cannot change it
                      created_at TEXT, finished_at TEXT);
CREATE TABLE concepts(id TEXT PRIMARY KEY, name TEXT, summary TEXT, page INTEGER, quote TEXT);
CREATE TABLE edges(parent_id TEXT, child_id TEXT, why TEXT, PRIMARY KEY(parent_id, child_id)); -- parent comes first
CREATE TABLE misconceptions(id TEXT PRIMARY KEY, concept_id TEXT, statement TEXT, contrast_quote TEXT);
CREATE TABLE questions(id TEXT PRIMARY KEY, concept_id TEXT, kind TEXT, round INTEGER, stem TEXT,
                       options_json TEXT, answer_key TEXT, rationale TEXT, page INTEGER, quote TEXT, status TEXT);
CREATE TABLE answers(id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, question_id TEXT, round INTEGER,
                     seq INTEGER, chosen_key TEXT, chosen_tag TEXT, is_correct INTEGER, reason_text TEXT,
                     is_guess INTEGER, option_order TEXT, seconds REAL, created_at TEXT,
                     UNIQUE(student_id, question_id));
CREATE TABLE judgements(answer_id INTEGER PRIMARY KEY, verdict TEXT, misconception_id TEXT, other_text TEXT,
                        evidence_quote TEXT, confidence REAL, credit INTEGER, source TEXT, judged_at TEXT);
CREATE TABLE mastery_log(student_id TEXT, concept_id TEXT, answer_id INTEGER, p_after REAL,
                         PRIMARY KEY(student_id, answer_id));
```

`group_tag` records the reading condition of real testers (section 12). `is_simulated` marks fake students; the
dashboard shows them separately and never mixes them in silently.

## 11. Teacher dashboard (`ui/pages/2_Teacher.py`): function 6

Principle: **concept-first, plain words, counts not probabilities.** The main screen has three parts.

```
CLASS REPORT: Electricity Basics        14 students (10 real, 4 simulated)
 Re-teach these first
 +-------------------------------------------------------------------------+
 | 1. Resistance                                RED  Missing: 11 of 14      |
 |    START HERE: this is the first gap for 9 students                      |
 |    Most common mistake: "a thicker wire has more resistance" (6 students)|
 |    Also holds back: Ohm's law                              Re-read: page 3|
 |    [ What students wrote ]                                               |
 +-------------------------------------------------------------------------+
 | 2. Potential difference     ORANGE  Shaky: 7 of 14    ...                |
 Concept map (read left to right)
   [Current 12/14] -> [Voltage 7/14]     -> [Ohm's law 3/14] -> [Series 2/14]
                   -> [Resistance 3/14]  ->
   (node colour = class status, number = students who understood it)
 Tabs: Questions | Mistakes | Students | Data and build
```

Rules:
- **Class status** of a concept: share of students in state Understood. `>= 75%` green "Class has it",
  `50% to 75%` orange "Shaky", `< 50%` red "Missing". Thresholds in `config.py`.
- **Root gap** (per student): concept not Understood while every parent is Understood. `root_share` = share of
  students for whom it is a root gap. **START HERE** when `root_share >= 0.30`. This separates a true cause
  from fallout further along the graph.
- **Ranking:** `root_share` descending, then share of students not Understood. Show the top 3 with
  share >= 25%. If none, show "No concept needs re-teaching".
- **Most common mistake:** misconception with the most distinct students (verdict `misconception`), with its
  statement. "What students wrote" shows the stored `evidence_quote` texts without names.
- **Also holds back:** direct children that are not green.
- Tabs: **Questions** (section 9 table, hardest first, flags), **Mistakes** (counts per misconception, `OTHER`
  clusters), **Students** (student x concept grid, nicknames), **Data and build** (row counts, CSV export,
  `build_report.md`: how many questions were generated, passed, repaired, dropped).
- **Readability test (acceptance):** show the screen for 10 seconds, ask "what should the teacher re-teach?".
  The answer must match the top card.

## 12. Simulation, evaluation, and real data

**`simulate.py`** (needed to build and test the dashboard before real students exist). A student gets a latent
mastery per concept (more likely if the parents are mastered). Answers use `guess=0.25`, `slip=0.10`. A
non-master picks a distractor from a personal favourite misconception 70% of the time. Reasons come from
templates. All rows have `is_simulated=1`.

**`eval.py`** (no teacher needed):
1. Bank: gate pass rate, concept and edge match against `expected.json`.
2. Mastery: on 200 simulated students, agreement of Understood vs not with the latent truth (target >= 85%),
   and the same with rounds 1 and 2 only (shows the value of round 3).
3. Judge: the generator writes student-voice reasons for each misconception (varied length, typos), plus sound
   and vague ones. Targets: misconception id recovered >= 80%, sound reasons falsely flagged <= 10%.

**Real data:** 10 to 16 people take the test in groups with a known reading condition, so the dashboard can be
checked against what we *know*: `read_all` (4 to 5), `read_p1_3` (read pages 1 to 3 only, 4 to 5), `cold`
(read nothing, 4 to 5). Expected: the `read_p1_3` group is weak on C4 and C5. Label results "real, n=...".

## 13. Traceability and acceptance

| # | Function | Module | Demo moment | Acceptance test |
|---|---|---|---|---|
| 1 | Concept graph with prerequisites | `build_bank` step 1, `gates` | Graph appears from the PDF | No cycles. At least 4 of 5 expected edges. All 5 concepts found. |
| 2 | Mastery probability, updated per answer | `mastery.py`, `mastery_log` | Live bars move after each answer | Fixtures in section 7 pass to 3 decimals |
| 3 | Question difficulty from answers | `stats.py` | Questions tab | With 14 students every round-1 and round-2 question has n = 14 and a label |
| 4 | Reason, then misconception | `judge.py` | A wrong answer with a reason gets a named misconception and a quote | Judge targets in section 12. Right-for-wrong-reason is not credited. |
| 5 | One database | `db.py` | Data tab shows row counts | All students, answers and judgements in `tutor.db`. CSV export works. |
| 6 | Teacher sees class-wide weak concepts | `2_Teacher.py` | Cards and concept map | Top card = weakest root concept in simulated data. Readability test passes. |

## 14. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Free API output quality is poor, or limits are hit | Cache, throttle, provider fallback. Plan B: generate the demo bank with Claude Code and run it through the same checks. |
| A free model is retired mid-project | `smoke` re-picks models. The cache keeps old results. |
| Not enough real testers | Simulated students, clearly labelled. Never present them as real. |
| Judge mislabels a reason | Closed list, quoted evidence, confidence gate, eval report, teacher sees the quote. |
| 16 users at once on SQLite | WAL mode and short writes. Test with 16 browser tabs. |
| Wi-Fi or API down on demo day | Bank and a seeded `tutor.db` are committed. A screen recording as backup. |
| A single correct answer can be a guess (25%) | Two questions per round, two rounds, round 3 tie-break, and the reason box. |
