"""Student-facing backend: the calls the Streamlit pages make (SPEC 6, 7, 8).

Flow: join -> (current_question -> submit_answer)* -> finish_round -> ... -> results.
There is no feedback during the test: submit_answer never says whether an answer was right.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from . import config, mastery, rounds
from .db import rows
from .judge import JudgeFn, JudgeItem, credit_of
from .models import Bank
from .quotes import words


class TutorError(Exception):
    """A problem the student can fix (for example a reason that is too short)."""


@dataclass
class Progress:
    phase: str                      # "question" | "judge_pending" | "done"
    round: int | None = None
    index: int = 0                  # questions already answered in this round
    total: int = 0
    question_id: str | None = None  # the next unanswered question


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def join(conn: sqlite3.Connection, nickname: str, class_code: str = "", *, is_simulated: bool = False,
         student_id: str | None = None) -> str:
    nickname = (nickname or "").strip()[:40]
    if not nickname:
        raise TutorError("Please enter a nickname.")
    code = (class_code or "").strip()
    group = config.GROUP_BY_CODE.get(code.upper(), code.lower() or "default")
    sid = student_id or uuid.uuid4().hex[:10]  # a fixed id makes a simulated class reproducible (it seeds the question order)
    with conn:
        conn.execute("INSERT INTO students(id,nickname,class_code,is_simulated,group_tag,created_at) VALUES (?,?,?,?,?,?)",
                     (sid, nickname, code, int(is_simulated), group, _now()))
    return sid


def student(conn: sqlite3.Connection, sid: str) -> dict:
    r = rows(conn, "SELECT * FROM students WHERE id=?", (sid,))
    if not r:
        raise TutorError("Unknown student.")
    return r[0]


def answers_of(conn: sqlite3.Connection, sid: str) -> list[dict]:
    """Answers in order, each with its judgement and the credited correctness."""
    out = rows(conn, """SELECT a.*, j.verdict, j.misconception_id, j.evidence_quote, j.other_text, j.confidence,
                               j.source, j.credit AS j_credit
                        FROM answers a LEFT JOIN judgements j ON j.answer_id=a.id
                        WHERE a.student_id=? ORDER BY a.seq""", (sid,))
    for a in out:
        a["credited"] = bool(a["is_correct"]) if a["j_credit"] is None else bool(a["j_credit"])
    return out


def _credited(answers: list[dict]) -> dict[str, bool]:
    return {a["question_id"]: a["credited"] for a in answers}


def _plan(conn: sqlite3.Connection, bank: Bank, st: dict, r: int, credited: dict[str, bool]) -> list[str]:
    if r != 3:
        return rounds.plan_round(bank, st["id"], r)
    if st["round3_plan"] is None:  # computed once, then frozen, so later re-judging cannot change the round
        plan = rounds.plan_round(bank, st["id"], 3, rounds.flagged_concepts(bank, credited))
        with conn:
            conn.execute("UPDATE students SET round3_plan=? WHERE id=?", (json.dumps(plan), st["id"]))
        return plan
    return json.loads(st["round3_plan"])


def progress(conn: sqlite3.Connection, bank: Bank, sid: str) -> Progress:
    st = student(conn, sid)
    ans = answers_of(conn, sid)
    answered, credited = {a["question_id"] for a in ans}, _credited(ans)
    for r in (1, 2, 3):  # round 3 is only reached, and planned, once rounds 1 and 2 are answered and judged
        qids = _plan(conn, bank, st, r, credited)
        if not qids:
            continue
        left = [q for q in qids if q not in answered]
        if left:
            return Progress("question", r, len(qids) - len(left), len(qids), left[0])
        if st["judged_round"] < r:
            return Progress("judge_pending", r, len(qids), len(qids))
    return Progress("done")


def current_question(conn: sqlite3.Connection, bank: Bank, sid: str) -> dict | None:
    """What to show now. Options come in this student's order. No tags, no answer key."""
    p = progress(conn, bank, sid)
    if p.phase != "question":
        return None
    q = bank.question(p.question_id)
    order = rounds.option_order(sid, q.id, [o.key for o in q.options])
    return {
        "question_id": q.id, "stem": q.stem, "round": p.round, "index": p.index + 1, "total": p.total,
        "options": [{"label": "ABCD"[i], "key": k, "text": q.option(k).text} for i, k in enumerate(order)],
    }


def submit_answer(conn: sqlite3.Connection, bank: Bank, sid: str, question_id: str, chosen_key: str,
                  reason: str = "", is_guess: bool = False, seconds: float | None = None) -> dict:
    p = progress(conn, bank, sid)
    if p.phase != "question":
        raise TutorError("No question is waiting for an answer.")
    ans = answers_of(conn, sid)
    answered = {a["question_id"] for a in ans}
    st = student(conn, sid)
    planned = _plan(conn, bank, st, p.round, _credited(ans))
    if question_id not in planned or question_id in answered:
        raise TutorError("That question is not part of the current round.")
    q = bank.question(question_id)
    if chosen_key not in {o.key for o in q.options}:
        raise TutorError("Please pick one of the options.")
    reason = (reason or "").strip()
    if not is_guess and words(reason) < config.MIN_REASON_WORDS:
        raise TutorError(f"Please explain your choice in at least {config.MIN_REASON_WORDS} words, "
                         "or tick 'I am guessing'.")
    opt = q.option(chosen_key)
    order = rounds.option_order(sid, question_id, [o.key for o in q.options])
    with conn:
        conn.execute(
            """INSERT INTO answers(student_id,question_id,round,seq,chosen_key,chosen_tag,is_correct,reason_text,
                                   is_guess,option_order,seconds,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, question_id, p.round, len(ans) + 1, chosen_key, opt.tag, int(chosen_key == q.answer_key),
             reason, int(is_guess), json.dumps(order), seconds, _now()))
    snap = recompute_mastery(conn, bank, sid)
    nxt = progress(conn, bank, sid)
    return {"mastery": snap, "round_complete": nxt.phase == "judge_pending", "next": nxt}


def recompute_mastery(conn: sqlite3.Connection, bank: Bank, sid: str, params: mastery.Params = mastery.DEFAULT) -> dict:
    """Replay the answer log into mastery per concept (SPEC 7) and refresh mastery_log."""
    by_concept: dict[str, list[tuple[int, mastery.Obs]]] = defaultdict(list)
    for a in answers_of(conn, sid):
        cid = bank.question(a["question_id"]).concept_id
        by_concept[cid].append((a["id"], mastery.Obs(a["id"], a["credited"], bool(a["is_guess"]))))
    log, snap = [], {}
    for c in bank.concepts:
        obs = [o for _, o in by_concept.get(c.id, [])]
        trail = mastery.trail(obs, params)
        log += [(sid, c.id, o.answer_id, p) for o, p in zip(obs, trail)]
        p = trail[-1] if trail else params.p0
        snap[c.id] = {"p": p, "state": mastery.state(p, params), "answers": len(obs)}
    with conn:
        conn.execute("DELETE FROM mastery_log WHERE student_id=?", (sid,))
        conn.executemany("INSERT INTO mastery_log VALUES (?,?,?,?)", log)
    return snap


def finish_round(conn: sqlite3.Connection, bank: Bank, sid: str, judge: JudgeFn | None = None) -> Progress:
    """Run the reason judge for the finished round, refresh mastery, and move on."""
    p = progress(conn, bank, sid)
    if p.phase != "judge_pending":
        return p
    items = []
    ans = [a for a in answers_of(conn, sid) if a["round"] == p.round]
    for a in ans:
        q = bank.question(a["question_id"])
        items.append(JudgeItem(a["id"], q.concept_id, q.stem, q.option(a["chosen_key"]).text, a["chosen_tag"],
                               q.correct.text, bool(a["is_correct"]), a["reason_text"] or "", bool(a["is_guess"]), q.rationale))
    outs = {}
    if judge and items:
        try:
            outs = {o.answer_id: o for o in judge(items)}
        except Exception:  # a failing judge must never stop a student
            outs = {}
    with conn:
        for a in ans:
            o = outs.get(a["id"])
            verdict, source = (o.verdict, o.source) if o else ("none", "none")
            conn.execute("INSERT OR REPLACE INTO judgements VALUES (?,?,?,?,?,?,?,?,?)",
                         (a["id"], verdict, o.misconception_id if o else None, o.other_text if o else None,
                          o.evidence_quote if o else None, o.confidence if o else 0.0,
                          int(credit_of(bool(a["is_correct"]), verdict)), source, _now()))
        conn.execute("UPDATE students SET judged_round=? WHERE id=?", (p.round, sid))
    recompute_mastery(conn, bank, sid)
    nxt = progress(conn, bank, sid)
    if nxt.phase == "done":
        with conn:
            conn.execute("UPDATE students SET status='done', finished_at=? WHERE id=?", (_now(), sid))
    return nxt


def mastery_snapshot(conn: sqlite3.Connection, bank: Bank, sid: str) -> dict:
    """Mastery per concept right now (for the learner-model panel). Does not write."""
    by_c: dict[str, list[mastery.Obs]] = defaultdict(list)
    for a in answers_of(conn, sid):
        by_c[bank.question(a["question_id"]).concept_id].append(mastery.Obs(a["id"], a["credited"], bool(a["is_guess"])))
    out = {}
    for c in bank.concepts:
        p = mastery.final(by_c.get(c.id, []))
        out[c.id] = {"p": p, "state": mastery.state(p), "answers": len(by_c.get(c.id, []))}
    return out


def results(conn: sqlite3.Connection, bank: Bank, sid: str) -> dict:
    """Feedback for the end of the test: where to read again, and what each missed answer showed."""
    snap = mastery_snapshot(conn, bank, sid)
    concepts = [{"id": c.id, "name": c.name, "page": c.page, **snap[c.id]} for c in bank.concepts]
    review = []
    for a in answers_of(conn, sid):
        if a["credited"]:
            continue
        q = bank.question(a["question_id"])
        m = bank.misconception(a["misconception_id"]) if a["verdict"] == "misconception" else None
        review.append({
            "concept": bank.concept(q.concept_id).name, "page": q.evidence.page, "question": q.stem,
            "your_answer": q.option(a["chosen_key"]).text, "correct_answer": q.correct.text,
            "was_right_choice": bool(a["is_correct"]), "your_reason": a["reason_text"],
            "misconception": m.statement if m else None, "explanation": q.rationale,
        })
    return {"student": student(conn, sid), "concepts": concepts, "review": review}
