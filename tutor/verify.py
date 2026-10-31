"""Checks that need an AI of a different family than the writer (SPEC 5.2): blind solve, one right answer, leaks."""
from __future__ import annotations

import json
from collections import Counter
from functools import partial
from pathlib import Path

from .extract import doc_text
from .models import Page, Question
from .parallel import run_all

PROMPTS = Path(__file__).parent / "prompts"
CHUNK = 30   # questions checked per call. Every call re-sends the whole PDF text, so bigger batches use far fewer tokens


def _prompt(name: str, **fields: str) -> str:
    text = (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")
    for key, value in fields.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _payload(questions: list[Question], with_answer: bool = False) -> str:
    items = []
    for q in questions:
        item = {"id": q.id, "question": q.stem, "options": {o.key: o.text for o in q.options}}
        if with_answer:
            item["correct"] = q.answer_key
        items.append(item)
    return json.dumps(items, ensure_ascii=False, indent=1)


def _chunks(items: list, size: int = CHUNK):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _rows(raw, key: str) -> list[dict]:
    rows = raw.get(key, []) if isinstance(raw, dict) else raw
    return [r for r in rows if isinstance(r, dict)]


def _vote(llm, doc: str, part: list[Question], v: int):
    return llm.call_json("blind_solve", _prompt("blind_solve", DOC=doc, INPUT=_payload(part)),
                         temperature=0.0 if v == 0 else 0.7, salt=f"vote{v}")


def _settled(collected: list[str], key: str, total: int, need: int) -> bool:
    """True once the remaining votes could not change whether the checker agrees with the key by majority."""
    right = collected.count(key)
    return right >= need or len(collected) - right > total - need


def blind_solve(llm, pages: list[Page], questions: list[Question], votes: int, pool=None) -> dict[str, list[str]]:
    """The checking AI sees the notes and the question but not the key. Several runs, one choice per run.

    The code (never the AI) knows the key, so it can stop asking a question once the majority is settled: two matching
    votes out of three, or two that do not match, already decide it. That gives the same verdict as running every vote while
    using fewer calls, which matters when the free allowance is counted in tokens. Votes 0 and 1 run together."""
    out: dict[str, list[str]] = {q.id: [] for q in questions}
    if votes < 1:
        return out
    doc, by_id, need = doc_text(pages), {q.id: q for q in questions}, votes // 2 + 1
    open_ids = [q.id for q in questions]
    for wave in [list(range(min(2, votes)))] + [[v] for v in range(2, votes)]:
        todo = [by_id[i] for i in open_ids]
        if not todo:
            break
        jobs = [(v, partial(_vote, llm, doc, part, v)) for v in wave for part in _chunks(todo)]
        for (v, _), raw in zip(jobs, run_all(pool, [job for _, job in jobs])):
            for a in _rows(raw, "answers"):
                if a.get("id") in out:
                    out[a["id"]].append(str(a.get("choice", "")).strip().upper()[:1])
        open_ids = [i for i in open_ids if not _settled(out[i], by_id[i].answer_key, votes, need)]
    return out


def support_check(llm, pages: list[Page], questions: list[Question], pool=None) -> dict[str, set[str]]:
    """For each question: the option keys that the notes support. Exactly the answer key should be in it."""
    out: dict[str, set[str]] = {}
    doc = doc_text(pages)
    parts = list(_chunks(questions))
    jobs = [partial(llm.call_json, "support", _prompt("support", DOC=doc, INPUT=_payload(part)), temperature=0.0) for part in parts]
    for raw in run_all(pool, jobs):
        for item in _rows(raw, "items"):
            sup = item.get("supported") or {}
            if item.get("id") and isinstance(sup, dict):
                out[item["id"]] = {k.upper() for k, v in sup.items() if v is True}
    return out


def leak_dup_check(llm, questions: list[Question]) -> dict[str, list[dict]]:
    raw = llm.call_json("leak", _prompt("leak", INPUT=_payload(questions, with_answer=True)), temperature=0.0)
    d = raw if isinstance(raw, dict) else {}
    return {"leaks": [x for x in d.get("leaks", []) if isinstance(x, dict)],
            "duplicates": [x for x in d.get("duplicates", []) if isinstance(x, dict)]}


def decide(q: Question, votes: list[str], supported: set[str] | None) -> list[str]:
    """Reasons a question fails the AI checks. Empty list means it passes."""
    reasons = []
    if not votes:
        reasons.append("blind_solve: no answers came back")
    elif Counter(votes)[q.answer_key] * 2 <= len(votes):
        reasons.append(f"blind_solve: the checker chose {votes} but the key is {q.answer_key}")
    if supported is not None and supported != {q.answer_key}:
        reasons.append(f"support: the notes support options {sorted(supported)}, expected only {q.answer_key}")
    return reasons
