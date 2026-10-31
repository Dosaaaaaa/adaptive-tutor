"""Shapes what the brain returns into what the API sends. Student output never carries answer keys or tags."""
from __future__ import annotations

import json
import sqlite3

from tutor import config, exams, jobs, service
from tutor.models import FILES, Bank

PRIVATE_EXAM_FIELDS = {"pid", "log_path"}


def exam_out(conn: sqlite3.Connection, exam: dict) -> dict:
    """An exam for the teacher. A building exam is refreshed first, so progress and status are current."""
    e = jobs.refresh(conn, exam) if exam["status"] == "building" else dict(exam, **exams.counts(conn, exam["code"]))
    e.update(exams.counts(conn, exam["code"]))
    return {k: v for k, v in e.items() if k not in PRIVATE_EXAM_FIELDS}


def public_exam(conn: sqlite3.Connection, exam: dict) -> dict:
    """What anyone with the link may know: the title and whether the exam can be joined."""
    if exam["status"] == "building":
        exam = jobs.refresh(conn, exam)
    c = exams.counts(conn, exam["code"])
    full = c["joined"] >= exam["max_students"]
    can_join = exam["status"] == "ready" and not full
    reason = {"building": "This exam is not ready yet. Please try again in a few minutes.",
              "failed": "This exam could not be prepared. Please tell your teacher.",
              "closed": "This exam is closed. Please ask your teacher."}.get(exam["status"]) or (
        "This exam is full. Please ask your teacher." if full else None)
    return {"code": exam["code"], "title": exam["title"], "status": exam["status"], "can_join": can_join, "message": reason}


def play_state(conn: sqlite3.Connection, bank: Bank, exam: dict, sid: str) -> dict:
    """Where a student is now. The question carries only what a student may see."""
    p = service.progress(conn, bank, sid)
    state = {"exam": {"code": exam["code"], "title": exam["title"]},
             "nickname": service.student(conn, sid)["nickname"], "round": p.round, "index": p.index, "total": p.total,
             "phase": {"question": "question", "judge_pending": "judging", "done": "done"}[p.phase], "question": None}
    if p.phase == "question":
        v = service.current_question(conn, bank, sid)
        state["question"] = {"id": v["question_id"], "stem": v["stem"], "round": v["round"], "index": v["index"],
                             "total": v["total"], "options": v["options"]}
    return state


def list_banks() -> list[dict]:
    """Complete quiz banks on this computer."""
    out = []
    for manifest in sorted(config.BANK_DIR.glob("*/manifest.json")):
        folder = manifest.parent
        if not all((folder / f).exists() for f in FILES):
            continue
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
            questions = len(json.loads((folder / "questions.json").read_text(encoding="utf-8")))
            concepts = len(json.loads((folder / "concepts.json").read_text(encoding="utf-8"))["concepts"])
        except (OSError, ValueError, KeyError):
            continue
        out.append({"name": folder.name, "pdf": m.get("pdf"), "concepts": concepts, "questions": questions,
                    "ai_checked": bool(m.get("ai_checks")),
                    "label": f"{m.get('pdf', folder.name)}: {concepts} concepts, {questions} questions "
                             f"({'AI-built and checked' if m.get('ai_checks') else 'hand-made'})"})
    return out
