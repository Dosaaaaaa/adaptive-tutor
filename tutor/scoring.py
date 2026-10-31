"""Scores: a plain number for each student, next to the concept picture the brain already gives.

Score = answers credited as right among the main questions (rounds 1 and 2: the same questions for every student).
Round 3 questions are follow-ups for weak concepts and are not part of the score. A right answer with a reason that
shows a misunderstanding is not credited (SPEC 8), so the score and the concept picture agree.
"""
from __future__ import annotations

import sqlite3

from . import service
from .db import rows
from .models import Bank


def score_for(conn: sqlite3.Connection, sid: str) -> dict:
    answers = service.answers_of(conn, sid)
    main = [a for a in answers if a["round"] in (1, 2)]
    credited = sum(1 for a in main if a["credited"])
    return {"credited": credited, "asked": len(main), "percent": round(100 * credited / len(main)) if main else None,
            "follow_ups": sum(1 for a in answers if a["round"] == 3)}


def exam_scores(conn: sqlite3.Connection, bank: Bank, code: str, include: str = "all", only_done: bool = True) -> dict:
    """Every student's score for one exam, best first, and the class average."""
    sql, args = "SELECT * FROM students WHERE exam_code=?", [code]
    if include in ("real", "simulated"):
        sql += " AND is_simulated=?"
        args.append(int(include == "simulated"))
    if only_done:
        sql += " AND status='done'"
    table = []
    for s in rows(conn, sql + " ORDER BY created_at", tuple(args)):
        sc = score_for(conn, s["id"])
        table.append({"nickname": s["nickname"], "simulated": bool(s["is_simulated"]), "finished": s["status"] == "done",
                      "credited": sc["credited"], "asked": sc["asked"], "percent": sc["percent"],
                      "states": {cid: v["state"] for cid, v in service.mastery_snapshot(conn, bank, s["id"]).items()}})
    table.sort(key=lambda r: (-(r["percent"] if r["percent"] is not None else -1), r["nickname"].lower()))
    done = [r["percent"] for r in table if r["finished"] and r["percent"] is not None]
    return {"students": table, "average": round(sum(done) / len(done)) if done else None,
            "best": max(done) if done else None, "lowest": min(done) if done else None}
