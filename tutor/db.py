"""One SQLite database for everything (SPEC 10, function 5)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import config
from .models import Bank

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS students(
  id TEXT PRIMARY KEY, nickname TEXT NOT NULL, class_code TEXT, is_simulated INTEGER NOT NULL DEFAULT 0,
  group_tag TEXT, status TEXT NOT NULL DEFAULT 'in_progress', judged_round INTEGER NOT NULL DEFAULT 0,
  round3_plan TEXT, created_at TEXT NOT NULL, finished_at TEXT, exam_code TEXT);
CREATE TABLE IF NOT EXISTS exams(
  code TEXT PRIMARY KEY, title TEXT NOT NULL, bank_name TEXT, pdf_name TEXT, max_students INTEGER NOT NULL DEFAULT 30,
  status TEXT NOT NULL DEFAULT 'building', max_concepts INTEGER, pid INTEGER, log_path TEXT, error TEXT,
  created_at TEXT NOT NULL, closed_at TEXT);
CREATE TABLE IF NOT EXISTS concepts(id TEXT PRIMARY KEY, name TEXT, summary TEXT, page INTEGER, quote TEXT);
CREATE TABLE IF NOT EXISTS edges(parent_id TEXT, child_id TEXT, why TEXT, PRIMARY KEY(parent_id, child_id));
CREATE TABLE IF NOT EXISTS misconceptions(id TEXT PRIMARY KEY, concept_id TEXT, statement TEXT, contrast_quote TEXT);
CREATE TABLE IF NOT EXISTS questions(
  id TEXT PRIMARY KEY, concept_id TEXT, kind TEXT, round INTEGER, stem TEXT, options_json TEXT,
  answer_key TEXT, rationale TEXT, page INTEGER, quote TEXT, status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS answers(
  id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL REFERENCES students(id),
  question_id TEXT NOT NULL, round INTEGER, seq INTEGER, chosen_key TEXT, chosen_tag TEXT, is_correct INTEGER,
  reason_text TEXT, is_guess INTEGER DEFAULT 0, option_order TEXT, seconds REAL, created_at TEXT,
  UNIQUE(student_id, question_id));
CREATE TABLE IF NOT EXISTS judgements(
  answer_id INTEGER PRIMARY KEY REFERENCES answers(id), verdict TEXT, misconception_id TEXT, other_text TEXT,
  evidence_quote TEXT, confidence REAL, credit INTEGER, source TEXT, judged_at TEXT);
CREATE TABLE IF NOT EXISTS mastery_log(
  student_id TEXT, concept_id TEXT, answer_id INTEGER, p_after REAL, PRIMARY KEY(student_id, answer_id));
CREATE INDEX IF NOT EXISTS idx_answers_student ON answers(student_id);
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open the database (creates folder and tables). WAL mode and short writes suit ~20 browser tabs."""
    path = Path(path) if path else config.db_path()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a database made before exams existed up to date. Adds a column and an index; changes no data."""
    if "exam_code" not in {r[1] for r in conn.execute("PRAGMA table_info(students)")}:
        conn.execute("ALTER TABLE students ADD COLUMN exam_code TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_students_exam ON students(exam_code)")
    conn.commit()


def rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def load_bank_into_db(conn: sqlite3.Connection, bank: Bank, *, force: bool = False) -> bool:
    """Copy the bank into the database. Returns False when the same bank is already loaded.

    A different bank is refused while answers exist, because answers point at question ids.
    """
    ident = f'{bank.name}:{bank.manifest.get("pdf_sha256", "")}:{len(bank.questions)}'
    current = conn.execute("SELECT value FROM meta WHERE key='bank'").fetchone()
    if current and current["value"] == ident:
        return False
    has_answers = conn.execute("SELECT 1 FROM answers LIMIT 1").fetchone()
    if has_answers and not force:
        raise RuntimeError("The database already has answers for another bank. Use a new database or force=True.")
    with conn:
        for t in ("concepts", "edges", "misconceptions", "questions"):
            conn.execute(f"DELETE FROM {t}")
        conn.executemany("INSERT INTO concepts VALUES (?,?,?,?,?)",
                         [(c.id, c.name, c.summary, c.page, c.quote) for c in bank.concepts])
        conn.executemany("INSERT INTO edges VALUES (?,?,?)", [(e.parent, e.child, e.why) for e in bank.edges])
        conn.executemany("INSERT INTO misconceptions VALUES (?,?,?,?)",
                         [(m.id, m.concept_id, m.statement, m.contrast_quote) for m in bank.misconceptions])
        conn.executemany(
            "INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(q.id, q.concept_id, q.kind, q.round, q.stem,
              json.dumps([o.model_dump() for o in q.options], ensure_ascii=False), q.answer_key, q.rationale,
              q.evidence.page, q.evidence.quote, "active") for q in bank.questions])
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('bank', ?)", (ident,))
    return True
