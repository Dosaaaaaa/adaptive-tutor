"""Reason judge: finds the misconception in a student's one-liner (SPEC 8, function 4).

The AI is not trusted. It may only pick from the concept's misconception list (or OTHER), it must quote the
student's own words, and the code checks the quote. Without a working AI the lexical judge keeps things going.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import config
from .models import Bank
from .quotes import norm, quote_in

log = logging.getLogger(__name__)
PROMPTS = Path(__file__).parent / "prompts"
VERDICTS = {"sound", "misconception", "guess", "unclear"}


@dataclass
class JudgeItem:
    answer_id: int
    concept_id: str
    stem: str
    chosen_text: str
    chosen_tag: str
    correct_text: str
    is_correct: bool
    reason: str
    is_guess: bool = False
    rationale: str = ""


@dataclass
class JudgementOut:
    answer_id: int
    verdict: str                      # sound | misconception | guess | unclear
    misconception_id: str | None = None   # a bank id, "OTHER", or None
    other_text: str | None = None
    evidence_quote: str | None = None
    confidence: float = 0.0
    source: str = "llm"               # llm | lexical | rule | none | error


JudgeFn = Callable[[list[JudgeItem]], list[JudgementOut]]


def credit_of(is_correct: bool, verdict: str) -> bool:
    """A right answer with a flawed reason is counted wrong. Everything else follows the choice."""
    return bool(is_correct) and verdict != "misconception"


def _rule_guess(item: JudgeItem) -> JudgementOut | None:
    if item.is_guess or not item.reason.strip():
        return JudgementOut(item.answer_id, "guess", confidence=1.0, source="rule")
    return None


def validate(raw: dict, item: JudgeItem, valid_ids: set[str],
             min_conf: float = config.JUDGE_MIN_CONFIDENCE) -> JudgementOut:
    """Turn one AI answer into a checked judgement (SPEC 8, validation rules 1 and 2)."""
    verdict = str(raw.get("verdict", "unclear")).strip().lower()
    verdict = verdict if verdict in VERDICTS else "unclear"
    try:
        conf = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    quote = (raw.get("evidence_quote") or "").strip() or None
    mid = raw.get("misconception_id")
    other = (raw.get("other_text") or "").strip() or None

    if verdict == "misconception":
        if not quote or not quote_in(quote, item.reason) or conf < min_conf:
            return JudgementOut(item.answer_id, "unclear", confidence=conf, source="llm")
        if mid not in valid_ids:
            mid, other = "OTHER", other or quote
        return JudgementOut(item.answer_id, verdict, mid, other if mid == "OTHER" else None, quote, conf, "llm")
    if verdict in ("sound", "guess") and conf < min_conf:
        verdict = "unclear"
    return JudgementOut(item.answer_id, verdict, None, None, None, conf, "llm")


def _prompt(items: list[JudgeItem], bank: Bank) -> str:
    cids = sorted({i.concept_id for i in items})
    payload = {
        "concepts": [{"id": c, "name": bank.concept(c).name,
                      "page_text": bank.page_text(bank.concept(c).page),
                      "misconceptions": [{"id": m.id, "statement": m.statement} for m in bank.misconceptions_of(c)]}
                     for c in cids],
        "items": [{"answer_id": i.answer_id, "concept_id": i.concept_id, "question": i.stem,
                   "chosen_option": i.chosen_text, "chosen_option_is_correct": i.is_correct,
                   "correct_option": i.correct_text, "explanation": i.rationale,
                   "student_reason": i.reason} for i in items],
    }
    return (PROMPTS / "judge.txt").read_text(encoding="utf-8").replace(
        "{{INPUT}}", json.dumps(payload, ensure_ascii=False, indent=1))


def make_llm_judge(llm, bank: Bank) -> JudgeFn:
    """Judge backed by an LLM: one call per student per round. Falls back to the lexical judge on any failure."""
    fallback = make_lexical_judge(bank)

    def judge(items: list[JudgeItem]) -> list[JudgementOut]:
        out = {i.answer_id: _rule_guess(i) for i in items}
        todo = [i for i in items if out[i.answer_id] is None]
        if todo:
            try:
                raw = llm.call_json("judge", _prompt(todo, bank), temperature=0.0)
                rows = raw.get("judgements", []) if isinstance(raw, dict) else raw
                by_id = {int(r.get("answer_id", -1)): r for r in rows if isinstance(r, dict)}
                for i in todo:
                    valid = {m.id for m in bank.misconceptions_of(i.concept_id)}
                    out[i.answer_id] = validate(by_id[i.answer_id], i, valid) if i.answer_id in by_id else \
                        JudgementOut(i.answer_id, "unclear", source="llm")
            except Exception as exc:  # network, quota, bad JSON: keep the test going
                log.warning("Judge call failed (%s). Using the lexical judge for %d answers.", exc, len(todo))
                for j in fallback(todo):
                    out[j.answer_id] = j
        return [out[i.answer_id] for i in items]

    return judge


# ---- lexical judge: no AI, a weak but safe baseline, also used for simulated students ----

_STOP = set("""a an the of to in is are was were be been it its this that these those and or for with as at by on
from so than then because i me my we you they them their there not no do does did can could would should will have
has had if but also just think which what when how very more most""".split())


def _tokens(text: str) -> set[str]:
    return {t[:-1] if len(t) > 3 and t.endswith("s") else t
            for t in re.findall(r"[a-z0-9]+", norm(text)) if t not in _STOP}


def _best_sentence(reason: str, target: set[str]) -> str:
    parts = [s.strip() for s in re.split(r"(?<=[.!?;])\s+", reason.strip()) if s.strip()] or [reason.strip()]
    return max(parts, key=lambda s: len(_tokens(s) & target))[:160]


def _negated(text: str) -> bool:
    return bool(re.search(r"\b(not|never|no)\b|n't", norm(text)))


def _coverage(reason_tokens: set[str], target: set[str]) -> float:
    return len(reason_tokens & target) / len(target) if target else 0.0


def make_lexical_judge(bank: Bank, min_coverage: float = 0.5) -> JudgeFn:
    """No AI. Compares the reason with each misconception AND with the correct explanation, so a right
    reason that happens to share words with a misconception is not flagged. Weak, but safe and offline."""

    def judge(items: list[JudgeItem]) -> list[JudgementOut]:
        out = []
        for it in items:
            if (g := _rule_guess(it)) is not None:
                out.append(g)
                continue
            reason_tokens = _tokens(it.reason)
            negated = _negated(it.reason)
            right_cov = max(_coverage(reason_tokens, _tokens(it.rationale)),
                            _coverage(reason_tokens, _tokens(it.correct_text)))
            best_cov, best = 0.0, None
            for m in bank.misconceptions_of(it.concept_id):
                cov = _coverage(reason_tokens, _tokens(m.statement))
                if cov > best_cov:
                    best_cov, best = cov, m
            # a correct choice needs clearer evidence than a wrong one before its reason is called flawed
            needed = min_coverage + (0.15 if it.is_correct else 0.0)
            # "current is NOT used up" denies a misconception; but a statement that itself says "not" is not denied
            denies = it.is_correct and negated and best is not None and not _negated(best.statement)
            flawed = best is not None and best_cov >= needed and best_cov > right_cov and not denies
            if flawed:
                out.append(JudgementOut(it.answer_id, "misconception", best.id, None,
                                        _best_sentence(it.reason, _tokens(best.statement)),
                                        min(0.9, 0.5 + best_cov / 2), "lexical"))
            elif it.is_correct:  # "sound" needs some evidence: a reason with no link to the explanation is unclear
                out.append(JudgementOut(it.answer_id, "sound" if right_cov >= 0.25 else "unclear",
                                        confidence=0.6 if right_cov >= 0.25 else 0.4, source="lexical"))
            elif it.chosen_tag.startswith("M"):  # weak: the choice only, marked by its source
                out.append(JudgementOut(it.answer_id, "misconception", it.chosen_tag, None,
                                        it.reason.strip()[:160], 0.55, "lexical"))
            else:
                out.append(JudgementOut(it.answer_id, "unclear", "OTHER", it.reason.strip()[:160],
                                        None, 0.3, "lexical"))
        return out

    return judge
