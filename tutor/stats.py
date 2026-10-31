"""Numbers for the teacher: question difficulty (function 3) and the class report (function 6). SPEC 9 and 11."""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from . import config, mastery
from .db import rows
from .models import Bank
from .service import mastery_snapshot

STATUS_LABEL = {"green": "Class has it", "orange": "Shaky", "red": "Missing"}


def _students(conn: sqlite3.Connection, include: str = "all", only_done: bool = False, exam: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM students WHERE 1=1", []
    if exam is not None:
        sql += " AND exam_code=?"
        args.append(exam)
    if include in ("real", "simulated"):
        sql += " AND is_simulated=?"
        args.append(int(include == "simulated"))
    if only_done:
        sql += " AND status='done'"
    return rows(conn, sql + " ORDER BY created_at", tuple(args))


# ---- function 3: difficulty of each question, measured from the answers ----

def question_stats(conn: sqlite3.Connection, bank: Bank, include: str = "all", exam: str | None = None) -> list[dict]:
    """Per question: n students, k right, smoothed p, label, flags, and how often each option was chosen."""
    sids = {s["id"] for s in _students(conn, include, exam=exam)}
    picks: dict[str, list[dict]] = defaultdict(list)
    for a in rows(conn, "SELECT student_id, question_id, chosen_key, is_correct FROM answers"):
        if a["student_id"] in sids:
            picks[a["question_id"]].append(a)
    out = []
    for q in bank.questions:
        got = picks.get(q.id, [])
        n, k = len(got), sum(a["is_correct"] for a in got)
        p = (k + 1) / (n + 2)
        label = "No data" if n == 0 else "Easy" if p >= config.EASY_P else "Hard" if p < config.HARD_P else "Medium"
        flags = []
        if n >= config.CHECK_MIN_N and p < config.CHECK_BELOW_P:
            flags.append("check_question")  # below chance: wrong key, or a distractor that lures everyone
        if n >= config.TOO_EASY_MIN_N and p > config.TOO_EASY_P:
            flags.append("too_easy")
        out.append({
            "question_id": q.id, "concept_id": q.concept_id, "kind": q.kind, "round": q.round, "stem": q.stem,
            "n": n, "k": k, "p": p, "label": label, "flags": flags,
            "options": [{"key": o.key, "text": o.text, "tag": o.tag,
                         "picked": sum(a["chosen_key"] == o.key for a in got)} for o in q.options],
        })
    by_id = {s["question_id"]: s for s in out}
    for c in bank.concepts:  # a "simple" question should not be harder than the concept's other questions
        base = [by_id[q.id] for q in bank.questions_of(c.id, ("recall", "apply")) if by_id[q.id]["n"] >= config.CHECK_MIN_N]
        for q in bank.questions_of(c.id, ("simple",)):
            s = by_id[q.id]
            if base and s["n"] >= config.CHECK_MIN_N and s["p"] < sum(b["p"] for b in base) / len(base):
                s["flags"].append("order_broken")
    return sorted(out, key=lambda s: (s["p"], s["question_id"]))


# ---- function 6: the class report ----

def _mistakes(conn: sqlite3.Connection, bank: Bank, sids: set[str]) -> list[dict]:
    got = rows(conn, """SELECT a.student_id, a.question_id, j.misconception_id, j.evidence_quote, j.other_text,
                               j.confidence FROM judgements j JOIN answers a ON a.id=j.answer_id
                        WHERE j.verdict='misconception'""")
    return [dict(g, concept_id=bank.question(g["question_id"]).concept_id) for g in got if g["student_id"] in sids]


def class_report(conn: sqlite3.Connection, bank: Bank, include: str = "all", only_done: bool = True,
                 exam: str | None = None) -> dict:
    studs = _students(conn, include, only_done, exam)
    sids = {s["id"] for s in studs}
    n = len(studs)
    snaps = {s["id"]: mastery_snapshot(conn, bank, s["id"]) for s in studs}
    mist = _mistakes(conn, bank, sids)
    everyone = _students(conn, include, exam=exam)

    concepts = []
    for c in bank.concepts:
        states = [snaps[s["id"]][c.id]["state"] for s in studs]
        und = states.count(mastery.UNDERSTOOD)
        share = und / n if n else 0.0
        status = "green" if share >= config.CLASS_GREEN else "orange" if share >= config.CLASS_ORANGE else "red"
        parents = bank.parents(c.id)
        root = sum(1 for s in studs
                   if snaps[s["id"]][c.id]["state"] != mastery.UNDERSTOOD
                   and all(snaps[s["id"]][p]["state"] == mastery.UNDERSTOOD for p in parents))
        by_m: dict[str, set] = defaultdict(set)
        quotes: dict[str, list] = defaultdict(list)
        for m in (m for m in mist if m["concept_id"] == c.id and bank.misconception(m["misconception_id"])):
            by_m[m["misconception_id"]].add(m["student_id"])
            quotes[m["misconception_id"]].append((m["confidence"] or 0.0, m["evidence_quote"]))
        top = max(by_m, key=lambda k: (len(by_m[k]), k), default=None)
        concepts.append({
            "id": c.id, "name": c.name, "page": c.page, "parents": parents, "n": n,
            "understood": und, "shaky": states.count(mastery.SHAKY), "missing": states.count(mastery.MISSING),
            "not_understood": n - und, "share_understood": share, "status": status,
            "status_label": STATUS_LABEL[status], "root_count": root, "root_share": root / n if n else 0.0,
            "start_here": n > 0 and root / n >= config.START_HERE_ROOT_SHARE,
            "top_mistake": ({"id": top, "statement": bank.misconception(top).statement, "students": len(by_m[top]),
                             "quotes": [q for _, q in sorted(quotes[top], reverse=True)][:5]} if top else None),
        })
    by_id = {c["id"]: c for c in concepts}
    for c in concepts:
        c["holds_back"] = [by_id[k]["name"] for k in bank.children(c["id"]) if by_id[k]["status"] != "green"]
        c["headline"] = (f'{c["not_understood"]} of {n} student{"" if n == 1 else "s"} '
                          "have not understood this yet") if n else "No data yet"

    order = {cid: i for i, cid in enumerate(bank.topo_order())}
    due = [c for c in concepts if n and c["not_understood"] / n >= config.CARD_MIN_NOT_UNDERSTOOD]
    cards = sorted(due, key=lambda c: (-c["root_share"], -c["not_understood"], order[c["id"]]))[:config.MAX_CARDS]

    mistakes = []
    for mid in sorted({m["misconception_id"] for m in mist if bank.misconception(m["misconception_id"])}):
        who = {m["student_id"] for m in mist if m["misconception_id"] == mid}
        mm = bank.misconception(mid)
        mistakes.append({"id": mid, "concept_id": mm.concept_id, "concept": bank.concept(mm.concept_id).name,
                         "statement": mm.statement, "students": len(who),
                         "quotes": [m["evidence_quote"] for m in mist if m["misconception_id"] == mid][:5]})
    mistakes.sort(key=lambda m: (-m["students"], m["id"]))
    other = [{"concept_id": m["concept_id"], "text": m["other_text"] or m["evidence_quote"]}
             for m in mist if m["misconception_id"] == "OTHER"]

    return {
        "bank": bank.name,
        "students": {"counted": n, "finished": sum(s["status"] == "done" for s in everyone),
                     "in_progress": sum(s["status"] != "done" for s in everyone),
                     "real": sum(not s["is_simulated"] for s in studs),
                     "simulated": sum(bool(s["is_simulated"]) for s in studs)},
        "concepts": concepts, "cards": cards,
        "graph": {"nodes": [{"id": c["id"], "name": c["name"], "status": c["status"], "understood": c["understood"],
                             "n": n} for c in concepts],
                  "edges": [[e.parent, e.child] for e in bank.edges]},
        "mistakes": mistakes, "other_texts": other,
        "grid": [{"nickname": s["nickname"], "group": s["group_tag"], "simulated": bool(s["is_simulated"]),
                  "states": {cid: v["state"] for cid, v in snaps[s["id"]].items()}} for s in studs],
    }


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("students", "answers", "judgements", "mastery_log", "questions", "concepts")}


def export_rows(conn: sqlite3.Connection, bank: Bank | None = None, exam: str | None = None) -> list[dict]:
    """One row per answer, for the CSV download. Nicknames only: no real names are ever stored.
    Pass the exam's bank to add the concept and question type of every answer."""
    sql = """
        SELECT s.nickname, s.group_tag, s.exam_code, s.is_simulated, a.round, a.seq, a.question_id,
               a.chosen_key, a.chosen_tag, a.is_correct, COALESCE(j.credit, a.is_correct) AS credited,
               a.is_guess, a.reason_text, j.verdict, j.misconception_id, j.evidence_quote, j.confidence, j.source,
               a.seconds, a.created_at
        FROM answers a JOIN students s ON s.id=a.student_id LEFT JOIN judgements j ON j.answer_id=a.id"""
    args: tuple = ()
    if exam is not None:
        sql, args = sql + " WHERE s.exam_code=?", (exam,)
    out = rows(conn, sql + " ORDER BY s.created_at, a.seq", args)
    if bank is not None:
        by_id = {q.id: q for q in bank.questions}
        for r in out:
            q = by_id.get(r["question_id"])
            r["concept_id"], r["kind"] = (q.concept_id, q.kind) if q else (None, None)
    return out


def format_report(rep: dict) -> str:
    """Plain-text version of the dashboard, for the terminal and for checking the logic without a browser."""
    s = rep["students"]
    lines = [f'CLASS REPORT ({rep["bank"]}): {s["counted"]} students ({s["real"]} real, {s["simulated"]} simulated)', "",
             "Re-teach these first"]
    if not rep["cards"]:
        lines.append("  No concept needs re-teaching.")
    for i, c in enumerate(rep["cards"], 1):
        lines.append(f'  {i}. {c["name"]}  [{c["status_label"]}]  {c["headline"]}')
        if c["start_here"]:
            lines.append(f'     START HERE: the first gap for {c["root_count"]} students')
        if c["top_mistake"]:
            t = c["top_mistake"]
            lines.append(f'     Most common mistake: "{t["statement"]}" ({t["students"]} students)')
        if c["holds_back"]:
            lines.append(f'     Also holds back: {", ".join(c["holds_back"])}')
        lines.append(f'     Re-read: page {c["page"]}')
    lines += ["", "Concept map"]
    for c in rep["concepts"]:
        arrow = f'  after {", ".join(c["parents"])}' if c["parents"] else ""
        lines.append(f'  {c["id"]} {c["name"]:<32} {c["status_label"]:<13} {c["understood"]}/{c["n"]} understood{arrow}')
    return "\n".join(lines)
