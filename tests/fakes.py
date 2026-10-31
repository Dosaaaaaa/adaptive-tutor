"""Stand-ins for the AI, so the tests never need a key or a network."""
from __future__ import annotations


class ScriptedLLM:
    """call_json(task, prompt, ...) answers come from fn(task, prompt). Records every call."""

    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def call_json(self, task, prompt, schema=None, **kw):
        self.calls.append((task, prompt))
        data = self.fn(task, prompt)
        return schema.model_validate(data) if schema is not None else data


class Boom:
    def call_json(self, *a, **kw):
        raise RuntimeError("network down")


# ---- a perfect AI for the electricity PDF, replaying the hand-authored gold bank ----

import json as _json
import re as _re


class GoldLLM:
    """Acts as both the writer and the checker. Hooks let a test make it misbehave.

    wrong_votes: question ids the checker answers wrongly (a number says for how many verification rounds).
    leaks: leak list returned by the leak check.  bad_quote_once: question ids whose first draft has an invented quote.
    """

    def __init__(self, gold, wrong_votes=None, leaks=None, bad_quote_once=()):
        self.gold, self.wrong, self.leaks, self.bad_quote_once = gold, dict(wrong_votes or {}), leaks or [], set(bad_quote_once)
        self.tasks, self.stats, self._rounds = [], {"calls": 0}, {}
        self.correct_text = {q.id: q.correct.text for q in gold.questions}

    def call_json(self, task, prompt, schema=None, **kw):
        self.tasks.append(task)
        self.stats["calls"] += 1
        data = getattr(self, "_" + task)(prompt)
        return schema.model_validate(data) if schema is not None else data

    def _cid(self, prompt):
        return _re.search(r"CONCEPT_ID: (C\d+)", prompt).group(1)

    def _items(self, prompt):
        return _json.JSONDecoder().raw_decode(prompt[prompt.rfind("\n[") + 1:])[0]

    def _concepts(self, prompt):
        g = self.gold
        return {"concepts": [{"id": c.id, "name": c.name, "summary": c.summary, "page": c.page, "quote": c.quote} for c in g.concepts],
                "edges": [e.model_dump() for e in g.edges]}

    def _misconceptions(self, prompt):
        return {"misconceptions": [{"statement": m.statement, "contrast_quote": m.contrast_quote}
                                   for m in self.gold.misconceptions_of(self._cid(prompt))]}

    def _gen(self, q):
        quote = "this sentence is not in the notes at all" if q.id in self.bad_quote_once else q.evidence.quote
        self.bad_quote_once.discard(q.id)
        return {"kind": q.kind, "stem": q.stem, "correct": q.correct.text, "rationale": q.rationale,
                "distractors": [{"text": o.text, "tag": o.tag} for o in q.options if o.tag != "correct"],
                "evidence_quote": quote}

    def _questions(self, prompt):
        return {"questions": [self._gen(q) for q in self.gold.questions_of(self._cid(prompt))]}

    def _regen(self, prompt):
        kind = _re.search(r'ONE question of kind "(\w+)"', prompt).group(1)
        return {"questions": [self._gen(next(q for q in self.gold.questions_of(self._cid(prompt)) if q.kind == kind))]}

    def _blind_solve(self, prompt):
        answers = []
        for it in self._items(prompt):
            right = next(k for k, t in it["options"].items() if t == self.correct_text[it["id"]])
            if self.wrong.get(it["id"], 0) > 0:
                right = next(k for k in it["options"] if k != right)
            answers.append({"id": it["id"], "choice": right})
        return {"answers": answers}

    def _support(self, prompt):
        for qid in list(self.wrong):  # a verification round has passed for these: count it down
            self.wrong[qid] -= 1
        return {"items": [{"id": it["id"], "supported": {k: t == self.correct_text[it["id"]] for k, t in it["options"].items()}}
                          for it in self._items(prompt)]}

    def _leak(self, prompt):
        return {"leaks": self.leaks, "duplicates": []}
