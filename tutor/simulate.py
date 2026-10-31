"""Simulated students (SPEC 12). They go through the real service code, so they test it too.

Simulated rows are always stored with is_simulated=1 and are never mixed into "real" numbers.
Run:  python -m tutor.simulate --n 14 --seed 7 --report
"""
from __future__ import annotations

import argparse
import random

from . import config, service
from .db import connect, load_bank_into_db
from .judge import JudgeFn, make_lexical_judge
from .models import Bank, load_bank
from .quotes import words

GROUPS = ("read_all", "read_p1_3", "cold")
_WRONG_TEMPLATES = ("I think {s}.", "{S}, so I picked this one.", "Because {s}, as far as I remember.")
_SLIP_REASON = "I think this one looks right to me, but I am not completely sure."
_OTHER_REASON = "I am not sure, but this one seemed the most likely answer to me."


def class_latents(bank: Bank, group: str, rng: random.Random) -> set[str]:
    """Which concepts a simulated student really knows. A concept is much less likely if a parent is unknown."""
    known: set[str] = set()
    for cid in bank.topo_order():
        page = bank.concept(cid).page
        base = (0.85 if page <= 3 else 0.12) if group == "read_p1_3" else {"read_all": 0.88, "cold": 0.18}.get(group, 0.5)
        p = base * (1.0 if all(par in known for par in bank.parents(cid)) else 0.4)
        if rng.random() < p:
            known.add(cid)
    return known


def _lower_first(s: str) -> str:
    return s[0].lower() + s[1:] if s and not s[:2].isupper() else s


def _misconception_reason(statement: str, rng: random.Random) -> str:
    s = statement.rstrip(".")
    return rng.choice(_WRONG_TEMPLATES).format(s=_lower_first(s), S=s)


def _pad(text: str) -> str:
    return text if words(text) >= config.MIN_REASON_WORDS else text + " I remember this from the notes."


def simulate_student(conn, bank: Bank, *, nickname: str, group: str, known: set[str], rng: random.Random,
                     judge: JudgeFn | None, favourite: dict[str, str] | None = None,
                     guess: float = 0.25, slip: float = 0.10, flawed_right: float = 0.5,
                     is_simulated: bool = True, student_id: str | None = None) -> str:
    """Run one student through all rounds. `known` is the ground truth: concepts they really know.

    A student who does not know a concept answers right by luck with chance `guess`; a lucky answer comes with a
    flawed reason with chance `flawed_right`, otherwise with a guess tick. A student who knows it slips with `slip`.
    """
    code = {"read_all": "DEMO-ALL", "read_p1_3": "DEMO-P13", "cold": "DEMO-COLD"}.get(group, group)
    sid = service.join(conn, nickname, code, is_simulated=is_simulated, student_id=student_id)
    fav = favourite or {}
    while True:
        p = service.progress(conn, bank, sid)
        if p.phase == "done":
            return sid
        if p.phase == "judge_pending":
            service.finish_round(conn, bank, sid, judge)
            continue
        q = bank.question(p.question_id)
        wrongs = [o for o in q.options if o.key != q.answer_key]
        mastered = q.concept_id in known
        is_guess, reason = False, ""
        if mastered and rng.random() >= slip:
            key, reason = q.answer_key, _pad(q.rationale)
        elif mastered:  # a slip
            key, reason = rng.choice(wrongs).key, _SLIP_REASON
        elif rng.random() < guess:  # lucky
            key = q.answer_key
            fm = bank.misconception(fav.get(q.concept_id, ""))
            if fm is not None and rng.random() < flawed_right:
                reason = _misconception_reason(fm.statement, rng)
            else:
                is_guess = True
        else:
            tagged = [o for o in wrongs if o.tag == fav.get(q.concept_id)]
            opt = tagged[0] if tagged and rng.random() < 0.7 else rng.choice(wrongs)
            key = opt.key
            m = bank.misconception(opt.tag)
            reason = _misconception_reason(m.statement, rng) if m else _OTHER_REASON
        service.submit_answer(conn, bank, sid, q.id, key, reason, is_guess, seconds=round(rng.uniform(8, 40), 1))


def simulate_class(conn, bank: Bank, n: int = 14, seed: int = 7, judge: JudgeFn | None = None) -> list[str]:
    rng = random.Random(seed)
    judge = judge or make_lexical_judge(bank)
    sids = []
    taken = conn.execute("SELECT COUNT(*) FROM students WHERE is_simulated=1").fetchone()[0]
    for i in range(n):
        group = GROUPS[i % len(GROUPS)]
        known = class_latents(bank, group, rng)
        fav = {c.id: rng.choice(ms).id for c in bank.concepts if (ms := bank.misconceptions_of(c.id))}
        sids.append(simulate_student(conn, bank, nickname=f"sim-{taken + i + 1}", group=group, known=known, rng=rng,
                                     judge=judge, favourite=fav, student_id=f"sim{seed}-{taken + i + 1}"))
    return sids


def clear_simulated(conn) -> int:
    """Delete every simulated student and their rows. Real students are never touched."""
    ids = [r[0] for r in conn.execute("SELECT id FROM students WHERE is_simulated=1")]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    with conn:
        conn.execute(f"DELETE FROM judgements WHERE answer_id IN (SELECT id FROM answers WHERE student_id IN ({marks}))", ids)
        conn.execute(f"DELETE FROM mastery_log WHERE student_id IN ({marks})", ids)
        conn.execute(f"DELETE FROM answers WHERE student_id IN ({marks})", ids)
        conn.execute(f"DELETE FROM students WHERE id IN ({marks})", ids)
    return len(ids)


def main() -> None:
    from .stats import class_report, format_report

    ap = argparse.ArgumentParser(description="Create simulated students and optionally print the class report.")
    ap.add_argument("--n", type=int, default=14)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--bank", default=None, help="bank folder name under bank/ (default: newest)")
    ap.add_argument("--db", default=None, help="database file (default: data/tutor.db)")
    ap.add_argument("--report", action="store_true", help="print the class report as text")
    args = ap.parse_args()
    bank = load_bank(config.resolve_bank(args.bank))
    conn = connect(args.db)
    load_bank_into_db(conn, bank)
    sids = simulate_class(conn, bank, args.n, args.seed)
    print(f"created {len(sids)} simulated students (is_simulated=1) in {args.db or config.db_path()}")
    if args.report:
        print()
        print(format_report(class_report(conn, bank)))


if __name__ == "__main__":
    main()
