"""Scores that need no teacher (SPEC 12): the bank, the learner model, and the reason judge.

Run:  python -m tutor.eval [--bank NAME] [--n 100]
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from . import config, mastery, service
from .db import connect, load_bank_into_db
from .judge import JudgeFn, JudgeItem, make_lexical_judge
from .models import Bank, load_bank
from .simulate import GROUPS, class_latents, simulate_student


def eval_bank(bank: Bank, expected: dict) -> dict:
    """Compare concepts and edges with demo/expected.json. Concepts are matched by page."""
    exp_by_page = {c["page"]: c["id"] for c in expected["concepts"]}
    got_by_page = {c.page: c.id for c in bank.concepts}
    to_expected = {got_by_page[p]: exp_by_page[p] for p in exp_by_page if p in got_by_page}
    got_edges = {(to_expected.get(e.parent), to_expected.get(e.child)) for e in bank.edges}
    exp_edges = {tuple(e) for e in expected["edges_parent_before_child"]}
    tagged = sum(any(o.tag not in ("correct", "other") for o in q.options) for q in bank.questions)
    return {
        "concepts_found": f"{len(bank.concepts)} (expected {len(expected['concepts'])}), "
                          f"{len(set(exp_by_page) & set(got_by_page))} on the expected pages",
        "edges_matched": f"{len(got_edges & exp_edges)} of {len(exp_edges)}", "extra_edges": len(got_edges - exp_edges),
        "questions": len(bank.questions), "per_kind": dict(Counter(q.kind for q in bank.questions)),
        "questions_with_a_misconception_tag": f"{tagged} of {len(bank.questions)}",
        "answer_key_spread": dict(Counter(q.answer_key for q in bank.questions)),
    }


def eval_mastery(bank: Bank, n: int = 100, seed: int = 1) -> dict:
    """Does the learner model recover what simulated students really know? Compares 'understood' with the truth."""
    rng, judge = random.Random(seed), make_lexical_judge(bank)
    conn = connect(":memory:")
    load_bank_into_db(conn, bank)
    hit_all = hit_two = total = 0
    for i in range(n):
        group = GROUPS[i % len(GROUPS)]
        known = class_latents(bank, group, rng)
        fav = {c.id: rng.choice(ms).id for c in bank.concepts if (ms := bank.misconceptions_of(c.id))}
        sid = simulate_student(conn, bank, nickname=f"e{i}", group=group, known=known, rng=rng, judge=judge, favourite=fav,
                               student_id=f"eval{seed}-{i}")
        full = service.mastery_snapshot(conn, bank, sid)
        two: dict[str, list[mastery.Obs]] = {}
        for a in service.answers_of(conn, sid):
            if a["round"] < 3:
                two.setdefault(bank.question(a["question_id"]).concept_id, []).append(
                    mastery.Obs(a["id"], a["credited"], bool(a["is_guess"])))
        for c in bank.concepts:
            truth = c.id in known
            hit_all += (full[c.id]["state"] == mastery.UNDERSTOOD) == truth
            hit_two += (mastery.state(mastery.final(two.get(c.id, []))) == mastery.UNDERSTOOD) == truth
            total += 1
    return {"students": n, "decisions": total, "agreement_rounds_1_to_3": round(hit_all / total, 3),
            "agreement_rounds_1_and_2_only": round(hit_two / total, 3), "target": 0.85}


def eval_judge(writer, judge: JudgeFn, bank: Bank, per: int = 3, seed: int = 1) -> dict:
    """Can the judge recover a misconception from a student-voice reason? The writer AI invents the reasons.

    One writer call and one judge call per concept, so it stays inside free-tier limits.
    """
    items, truth, aid = [], {}, 0
    by_concept: dict[str, list[JudgeItem]] = {}
    for c in bank.concepts:
        mine = [m for m in bank.misconceptions_of(c.id)
                if any(o.tag == m.id for q in bank.questions_of(c.id) for o in q.options)]
        if mine:
            prompt = (f"Write {per} different one-sentence reasons for EACH wrong idea below, in the casual voice of a "
                      "school student (vary the length, allow small typos). The student FIRMLY BELIEVES the wrong idea "
                      "and argues FOR it. The reason must express the wrong idea itself. It must NOT state, hint at, or "
                      "agree with the correct fact given for each one (that is what the student gets wrong). Do not name "
                      "the wrong idea or say it is wrong. Return only JSON: "
                      '{"reasons": {"<id>": ["..."]}}\nWRONG IDEAS:\n'
                      + json.dumps([{"id": m.id, "wrong_idea": m.statement, "correct_fact_the_student_gets_wrong": m.contrast_quote}
                                    for m in mine], ensure_ascii=False))
            reasons = writer.call_json("synthetic_reason", prompt, temperature=0.9).get("reasons", {})
        else:
            reasons = {}
        chunk = by_concept.setdefault(c.id, [])
        for m in mine:
            q = next(x for x in bank.questions_of(c.id) if any(o.tag == m.id for o in x.options))
            wrong = next(o for o in q.options if o.tag == m.id)
            for text in list(reasons.get(m.id, []))[:per]:
                aid += 1
                chunk.append(JudgeItem(aid, c.id, q.stem, wrong.text, m.id, q.correct.text, False, str(text), False, q.rationale))
                truth[aid] = ("misconception", m.id)
        q = bank.questions_of(c.id)[0]  # a sound reason (the explanation itself) and a vague one
        aid += 1
        chunk.append(JudgeItem(aid, c.id, q.stem, q.correct.text, "correct", q.correct.text, True, q.rationale, False, q.rationale))
        truth[aid] = ("sound", None)
        aid += 1
        chunk.append(JudgeItem(aid, c.id, q.stem, q.correct.text, "correct", q.correct.text, True, "I just picked this one", False, q.rationale))
        truth[aid] = ("vague", None)
    got = {}
    for chunk in by_concept.values():
        got.update({o.answer_id: o for o in judge(chunk)})
    mis = [a for a, t in truth.items() if t[0] == "misconception"]
    sound = [a for a, t in truth.items() if t[0] == "sound"]
    vague = [a for a, t in truth.items() if t[0] == "vague"]
    share = lambda hits, base: round(len(hits) / len(base), 3) if base else None  # noqa: E731
    wrong_calls = [a for a in mis if got[a].verdict == "misconception" and got[a].misconception_id != truth[a][1]]
    return {
        "misconception_items": len(mis),
        "recovered_id": share([a for a in mis if got[a].misconception_id == truth[a][1]], mis), "target_recovered": 0.80,
        "named_a_different_misconception": len(wrong_calls),
        "sound_falsely_flagged": share([a for a in sound if got[a].verdict == "misconception"], sound), "target_false": 0.10,
        "vague_not_flagged": share([a for a in vague if got[a].verdict in ("guess", "unclear")], vague),
        "judged_by": sorted({o.source for o in got.values()}),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the bank, the learner model and (with keys) the judge.")
    ap.add_argument("--bank", default=None)
    ap.add_argument("--expected", default=str(config.ROOT / "demo" / "expected.json"))
    ap.add_argument("--n", type=int, default=100, help="simulated students for the learner-model score")
    ap.add_argument("--judge", action="store_true", help="also score the AI judge (needs keys)")
    args = ap.parse_args()
    bank = load_bank(config.resolve_bank(args.bank))
    print(f"BANK {bank.name}")
    for k, v in eval_bank(bank, json.loads(Path(args.expected).read_text(encoding="utf-8"))).items():
        print(f"  {k}: {v}")
    print("LEARNER MODEL (simulated students)")
    for k, v in eval_mastery(bank, args.n).items():
        print(f"  {k}: {v}")
    if args.judge:
        from . import llm
        from .judge import make_llm_judge
        print("JUDGE (AI)")
        for k, v in eval_judge(llm.from_env("generator"), make_llm_judge(llm.from_env("judge"), bank), bank).items():
            print(f"  {k}: {v}")
    else:
        print("JUDGE: skipped (add --judge once keys exist)")


if __name__ == "__main__":
    main()
