"""Checks that need an AI of a different family than the writer (SPEC 5.2): blind solve, one right answer, leaks."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .extract import doc_text
from .models import Page, Question

PROMPTS = Path(__file__).parent / "prompts"
CHUNK = 12


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


def blind_solve(llm, pages: list[Page], questions: list[Question], votes: int) -> dict[str, list[str]]:
    """The checking AI sees the notes and the question but not the key. Several runs, one choice per run."""
    out: dict[str, list[str]] = {q.id: [] for q in questions}
    doc = doc_text(pages)
    for v in range(votes):
        for part in _chunks(questions):
            raw = llm.call_json("blind_solve", _prompt("blind_solve", DOC=doc, INPUT=_payload(part)),
                                temperature=0.0 if v == 0 else 0.7, salt=f"vote{v}")
            for a in _rows(raw, "answers"):
                if a.get("id") in out:
                    out[a["id"]].append(str(a.get("choice", "")).strip().upper()[:1])
    return out


def support_check(llm, pages: list[Page], questions: list[Question]) -> dict[str, set[str]]:
    """For each question: the option keys that the notes support. Exactly the answer key should be in it."""
    out: dict[str, set[str]] = {}
    doc = doc_text(pages)
    for part in _chunks(questions):
        raw = llm.call_json("support", _prompt("support", DOC=doc, INPUT=_payload(part)), temperature=0.0)
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
