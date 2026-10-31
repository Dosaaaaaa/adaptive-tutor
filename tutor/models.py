"""Data shapes: the quiz bank (SPEC 5.4) and what the AI is asked to return."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .config import ROUND_OF_KIND

Kind = Literal["recall", "apply", "tiebreak", "simple"]
CORRECT = "correct"
OTHER = "other"


class Page(BaseModel):
    n: int
    text: str


class Concept(BaseModel):
    id: str
    name: str
    summary: str = ""
    page: int
    quote: str


class Edge(BaseModel):
    parent: str  # comes before child
    child: str
    why: str = ""


class Misconception(BaseModel):
    id: str
    concept_id: str
    statement: str
    contrast_quote: str


class Option(BaseModel):
    key: str
    text: str
    tag: str  # "correct", a misconception id, or "other"


class Evidence(BaseModel):
    page: int
    quote: str


class Question(BaseModel):
    id: str
    concept_id: str
    kind: Kind
    round: int
    stem: str
    options: list[Option]
    answer_key: str
    rationale: str = ""
    evidence: Evidence
    checks: dict[str, Any] = Field(default_factory=dict)

    def option(self, key: str) -> Option:
        return next(o for o in self.options if o.key == key)

    @property
    def correct(self) -> Option:
        return self.option(self.answer_key)


# ---- what the AI returns (SPEC 5.1). The code adds ids, keys, rounds and pages. ----

class ConceptsOut(BaseModel):
    concepts: list[Concept]
    edges: list[Edge] = Field(default_factory=list)


class GenMisconception(BaseModel):
    statement: str
    contrast_quote: str


class MisconceptionsOut(BaseModel):
    misconceptions: list[GenMisconception]


class GenOption(BaseModel):
    text: str
    tag: str = OTHER


class GenQuestion(BaseModel):
    kind: Kind
    stem: str
    correct: str
    distractors: list[GenOption]
    rationale: str = ""
    evidence_quote: str


class QuestionsOut(BaseModel):
    questions: list[GenQuestion]


def round_of(kind: str) -> int:
    return ROUND_OF_KIND[kind]


class Bank:
    """A loaded quiz bank with lookups. Build one with load_bank() or Bank(...)."""

    def __init__(self, manifest: dict, pages: list[Page], concepts: list[Concept], edges: list[Edge],
                 misconceptions: list[Misconception], questions: list[Question]):
        self.manifest, self.pages = manifest, pages
        self.concepts, self.edges = concepts, edges
        self.misconceptions, self.questions = misconceptions, questions
        self._c = {c.id: c for c in concepts}
        self._q = {q.id: q for q in questions}
        self._m = {m.id: m for m in misconceptions}

    @property
    def name(self) -> str:
        return self.manifest.get("name", "bank")

    def concept(self, cid: str) -> Concept:
        return self._c[cid]

    def question(self, qid: str) -> Question:
        return self._q[qid]

    def misconception(self, mid: str) -> Misconception | None:
        return self._m.get(mid)

    def misconceptions_of(self, cid: str) -> list[Misconception]:
        return [m for m in self.misconceptions if m.concept_id == cid]

    def questions_of(self, cid: str, kinds: tuple[str, ...] | None = None) -> list[Question]:
        return [q for q in self.questions if q.concept_id == cid and (kinds is None or q.kind in kinds)]

    def parents(self, cid: str) -> list[str]:
        return [e.parent for e in self.edges if e.child == cid]

    def children(self, cid: str) -> list[str]:
        return [e.child for e in self.edges if e.parent == cid]

    def page_text(self, n: int) -> str:
        return next((p.text for p in self.pages if p.n == n), "")

    def topo_order(self) -> list[str]:
        order, seen = [], set()

        def visit(cid: str) -> None:
            if cid in seen:
                return
            seen.add(cid)
            for p in self.parents(cid):
                visit(p)
            order.append(cid)

        for c in self.concepts:
            visit(c.id)
        return order


FILES = ("concepts.json", "misconceptions.json", "questions.json", "pages.json", "manifest.json")


def save_bank(bank: Bank, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)

    def dump(name: str, obj: Any) -> None:
        (folder / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    dump("concepts.json", {"concepts": [c.model_dump() for c in bank.concepts],
                           "edges": [e.model_dump() for e in bank.edges]})
    dump("misconceptions.json", [m.model_dump() for m in bank.misconceptions])
    dump("questions.json", [q.model_dump() for q in bank.questions])
    dump("pages.json", [p.model_dump() for p in bank.pages])
    dump("manifest.json", bank.manifest)


def load_bank(folder: Path | str) -> Bank:
    folder = Path(folder)
    read = lambda n: json.loads((folder / n).read_text(encoding="utf-8"))  # noqa: E731
    cj = read("concepts.json")
    manifest = read("manifest.json")
    manifest.setdefault("name", folder.name)
    return Bank(
        manifest=manifest,
        pages=[Page(**p) for p in read("pages.json")],
        concepts=[Concept(**c) for c in cj["concepts"]],
        edges=[Edge(**e) for e in cj["edges"]],
        misconceptions=[Misconception(**m) for m in read("misconceptions.json")],
        questions=[Question(**q) for q in read("questions.json")],
    )
