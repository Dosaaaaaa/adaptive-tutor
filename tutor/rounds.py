"""Round engine: which questions come when (SPEC 6). Pure functions, no database."""
from __future__ import annotations

import random

from .models import Bank

ROUND_KINDS = {1: ("recall",), 2: ("apply",), 3: ("tiebreak", "simple")}


def plan_round(bank: Bank, student_id: str, round_no: int, flagged: set[str] | None = None) -> list[str]:
    """Question ids for a round, shuffled per student, with the same concept never twice in a row if avoidable.

    Round 3 needs `flagged` (concepts that were not a clean sweep); without it the round is empty.
    """
    if round_no == 3 and flagged is None:
        return []
    kinds = ROUND_KINDS[round_no]
    pool = [q for q in bank.questions
            if q.kind in kinds and (round_no != 3 or q.concept_id in (flagged or set()))]
    rng = random.Random(f"{student_id}:{round_no}")
    rng.shuffle(pool)
    out: list = []
    while pool:
        i = next((k for k, q in enumerate(pool) if not out or q.concept_id != out[-1].concept_id), 0)
        out.append(pool.pop(i))
    return [q.id for q in out]


def flagged_concepts(bank: Bank, credited: dict[str, bool]) -> set[str]:
    """Concepts that are not a clean sweep: some round 1 or 2 answer was not credited as correct."""
    flagged = set()
    for c in bank.concepts:
        qids = [q.id for q in bank.questions_of(c.id, ("recall", "apply"))]
        if qids and not all(credited.get(q) is True for q in qids):
            flagged.add(c.id)
    return flagged


def option_order(student_id: str, question_id: str, keys: list[str]) -> list[str]:
    """Shuffled option keys, stable for one student and question."""
    keys = list(keys)
    random.Random(f"{student_id}:{question_id}").shuffle(keys)
    return keys
