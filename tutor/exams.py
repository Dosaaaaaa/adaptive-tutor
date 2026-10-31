"""Exams: how a teacher turns a PDF (or an existing quiz bank) into one link for a class.

An exam picks a quiz bank, limits how many students may join, and has one code. The brain (service, mastery, rounds,
judge, stats) is not changed: an exam only decides WHICH bank a student is tested on and WHO the teacher's report counts.
"""
from __future__ import annotations

import secrets
import socket
import sqlite3
from datetime import datetime, timezone

from . import config, service
from .db import rows

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"      # no 0, O, 1, I: easy to read out loud
STATUSES = ("building", "ready", "closed", "failed")
LEGACY_CODE = "DEMO"


class ExamError(Exception):
    """A problem the person can fix. The message is safe to show on screen."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(code: str | None) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def new_code(conn: sqlite3.Connection) -> str:
    for _ in range(50):
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if not conn.execute("SELECT 1 FROM exams WHERE code=?", (code,)).fetchone():
            return code
    raise ExamError("Could not make a free exam code. Please try again.")


def create_exam(conn: sqlite3.Connection, title: str, max_students: int, *, bank_name: str | None = None,
                pdf_name: str | None = None, max_concepts: int | None = None, status: str = "ready",
                code: str | None = None) -> dict:
    title = (title or "").strip()
    if not title:
        raise ExamError("Please give the exam a title.")
    if not 1 <= int(max_students) <= 1000:
        raise ExamError("The number of students must be between 1 and 1000.")
    if status not in STATUSES:
        raise ExamError(f"Unknown status {status!r}.")
    code = normalize(code) or new_code(conn)
    with conn:
        conn.execute("INSERT INTO exams(code,title,bank_name,pdf_name,max_students,status,max_concepts,created_at) "
                     "VALUES (?,?,?,?,?,?,?,?)", (code, title[:120], bank_name, pdf_name, int(max_students), status,
                                                  max_concepts, _now()))
    return get_exam(conn, code)


def get_exam(conn: sqlite3.Connection, code: str | None) -> dict | None:
    found = rows(conn, "SELECT * FROM exams WHERE code=?", (normalize(code),))
    return found[0] if found else None


def counts(conn: sqlite3.Connection, code: str) -> dict:
    """Students of this exam. `joined` is people who used the link (simulated test students are never counted)."""
    r = rows(conn, """SELECT SUM(is_simulated=0) AS joined, SUM(is_simulated=1) AS simulated,
                             SUM(is_simulated=0 AND status='done') AS finished
                      FROM students WHERE exam_code=?""", (code,))[0]
    return {"joined": r["joined"] or 0, "simulated": r["simulated"] or 0, "finished": r["finished"] or 0}


def list_exams(conn: sqlite3.Connection) -> list[dict]:
    out = rows(conn, "SELECT * FROM exams ORDER BY created_at DESC, code")
    for e in out:
        e.update(counts(conn, e["code"]))
    return out


def update_exam(conn: sqlite3.Connection, code: str, **fields) -> None:
    allowed = {"status", "bank_name", "pid", "log_path", "error", "closed_at", "max_students"}
    bad = set(fields) - allowed
    if bad:
        raise ExamError(f"Cannot change {sorted(bad)}.")
    if "status" in fields and fields["status"] not in STATUSES:
        raise ExamError(f"Unknown status {fields['status']!r}.")
    if fields:
        with conn:
            conn.execute(f"UPDATE exams SET {', '.join(f'{k}=?' for k in fields)} WHERE code=?", (*fields.values(), code))


def close_exam(conn: sqlite3.Connection, code: str) -> None:
    """Stops new students joining. Students already taking the test can finish."""
    update_exam(conn, code, status="closed", closed_at=_now())


def reopen_exam(conn: sqlite3.Connection, code: str) -> None:
    update_exam(conn, code, status="ready", closed_at=None)


def join_exam(conn: sqlite3.Connection, code: str, nickname: str) -> str:
    """A student uses the link: check the exam, the free places and the nickname, then start them in the brain."""
    exam = get_exam(conn, code)
    if exam is None:
        raise ExamError("We could not find that exam. Check the link or the code with your teacher.")
    if exam["status"] == "building":
        raise ExamError("This exam is not ready yet. Please try again in a few minutes.")
    if exam["status"] == "failed":
        raise ExamError("This exam could not be prepared. Please tell your teacher.")
    if exam["status"] == "closed":
        raise ExamError("This exam is closed. Please ask your teacher.")
    nickname = (nickname or "").strip()
    if conn.execute("SELECT 1 FROM students WHERE exam_code=? AND lower(nickname)=lower(?)",
                    (exam["code"], nickname)).fetchone():
        raise ExamError("Someone in this exam already uses that nickname. Add your initial or a number.")
    used = counts(conn, exam["code"])["joined"]
    if used >= exam["max_students"]:
        raise ExamError(f"This exam is full ({used} of {exam['max_students']} places are taken). Please ask your teacher.")
    sid = service.join(conn, nickname, exam["code"])          # the brain starts the student; raises on an empty nickname
    with conn:
        conn.execute("UPDATE students SET exam_code=? WHERE id=?", (exam["code"], sid))
    if counts(conn, exam["code"])["joined"] > exam["max_students"]:   # two students took the last place at once
        with conn:
            conn.execute("DELETE FROM students WHERE id=?", (sid,))
        raise ExamError("This exam just became full. Please ask your teacher.")
    return sid


def delete_exam(conn: sqlite3.Connection, code: str) -> int:
    """Delete an exam and everything its students recorded. Returns how many students were removed."""
    exam = get_exam(conn, code)
    if exam is None:
        raise ExamError("That exam does not exist.")
    if exam["status"] == "building":
        raise ExamError("The quiz is still being prepared. Please wait until it is finished.")
    ids = [r[0] for r in conn.execute("SELECT id FROM students WHERE exam_code=?", (exam["code"],))]
    with conn:
        if ids:
            marks = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM judgements WHERE answer_id IN (SELECT id FROM answers WHERE student_id IN ({marks}))", ids)
            conn.execute(f"DELETE FROM mastery_log WHERE student_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM answers WHERE student_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM students WHERE id IN ({marks})", ids)
        conn.execute("DELETE FROM exams WHERE code=?", (exam["code"],))
    return len(ids)


def student_exam(conn: sqlite3.Connection, sid: str) -> str | None:
    r = conn.execute("SELECT exam_code FROM students WHERE id=?", (sid,)).fetchone()
    return r["exam_code"] if r else None


def attach(conn: sqlite3.Connection, sids: list[str], code: str) -> None:
    with conn:
        conn.executemany("UPDATE students SET exam_code=? WHERE id=?", [(code, s) for s in sids])


def adopt_legacy(conn: sqlite3.Connection, bank_name: str) -> bool:
    """Students made before exams existed (a trial run) are gathered into one closed demo exam, so nothing is lost."""
    orphans = conn.execute("SELECT COUNT(*) FROM students WHERE exam_code IS NULL").fetchone()[0]
    if not orphans or get_exam(conn, LEGACY_CODE):
        return False
    create_exam(conn, "Demo exam (earlier trial)", 1000, bank_name=bank_name, status="closed", code=LEGACY_CODE)
    with conn:
        conn.execute("UPDATE students SET exam_code=? WHERE exam_code IS NULL", (LEGACY_CODE,))
    return True


# ---- the link ----

def lan_ip() -> str:
    """This computer's address on the local network. No packet is sent."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def public_base(port: int = config.STUDENT_PORT) -> str:
    """Where students reach the student app: PUBLIC_URL from .env (for example a tunnel), else this computer's address."""
    custom = (config.read_env_file().get("PUBLIC_URL") or "").strip().rstrip("/")
    return custom or f"http://{lan_ip()}:{port}"


def student_link(code: str, base: str | None = None) -> str:
    return f"{(base or public_base()).rstrip('/')}/?exam={normalize(code)}"
