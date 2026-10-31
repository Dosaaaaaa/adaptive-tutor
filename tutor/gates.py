"""Automatic checks that need no AI (SPEC 5.2). They replace the teacher's review."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import CORRECT, OTHER, Concept, Edge, Misconception, Page, Question
from .quotes import find_page, norm, quote_in

BANNED = ("all of the above", "none of the above", "both a and b", "(recommended)", "all the above")
BLOCK, WARN = "block", "warn"


@dataclass
class Issue:
    severity: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def blocking(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == BLOCK]


# ---- graph ----

def _reaches(edges: list[Edge], start: str, goal: str) -> bool:
    seen, stack = set(), [start]
    while stack:
        n = stack.pop()
        if n == goal:
            return True
        if n in seen:
            continue
        seen.add(n)
        stack += [e.child for e in edges if e.parent == n]
    return False


def check_graph(concepts: list[Concept], edges: list[Edge], max_concepts: int) -> tuple[list[Edge], list[str], list[str]]:
    """Returns (clean edges, repairs made, errors). Errors cannot be repaired by code and need a new AI answer."""
    errors, repairs = [], []
    ids = [c.id for c in concepts]
    if not ids:
        return [], [], ["no concepts"]
    if len(set(ids)) != len(ids):
        errors.append("duplicate concept ids")
    if len(ids) > max_concepts:
        errors.append(f"{len(ids)} concepts, the limit is {max_concepts}")
    valid, clean = set(ids), []
    for e in edges:
        if e.parent not in valid or e.child not in valid or e.parent == e.child:
            repairs.append(f"dropped invalid edge {e.parent}->{e.child}")
        elif any(x.parent == e.parent and x.child == e.child for x in clean):
            continue
        elif _reaches(clean, e.child, e.parent):
            repairs.append(f"dropped edge {e.parent}->{e.child}: it would make a cycle")
        else:
            clean.append(e)
    # connect separate islands by page order, so every concept belongs to one map
    page = {c.id: (c.page, i) for i, c in enumerate(concepts)}
    while True:
        comp = {i: i for i in ids}

        def find(x):
            while comp[x] != x:
                comp[x] = comp[comp[x]]
                x = comp[x]
            return x

        for e in clean:
            comp[find(e.parent)] = find(e.child)
        groups: dict[str, list[str]] = {}
        for i in ids:
            groups.setdefault(find(i), []).append(i)
        if len(groups) <= 1:
            break
        main = groups[find(min(ids, key=lambda i: page[i]))]
        other = min((g for r, g in groups.items() if g is not main), key=lambda g: min(page[i] for i in g))
        child = min(other, key=lambda i: page[i])
        before = [i for i in main if page[i] <= page[child]]
        if before:
            parent = max(before, key=lambda i: page[i])
            clean.append(Edge(parent=parent, child=child, why="attached by page order (no link found in the text)"))
        else:
            parent, child = child, min(main, key=lambda i: page[i])
            clean.append(Edge(parent=parent, child=child, why="attached by page order (no link found in the text)"))
        repairs.append(f"connected {parent}->{child} by page order")
    return clean, repairs, errors


def check_concepts(concepts: list[Concept], pages: list[Page]) -> list[Issue]:
    out = []
    for c in concepts:
        if not re.fullmatch(r"C\d+", c.id):
            out.append(Issue(BLOCK, "concept_id", f"{c.id!r} is not C<number>"))
        if find_page(c.quote, pages) is None:
            out.append(Issue(BLOCK, "concept_quote", f"{c.id}: quote not found in the PDF: {c.quote[:60]!r}"))
    return out


def check_misconception(m: Misconception, pages: list[Page]) -> list[Issue]:
    out = []
    if len(m.statement.split()) < 4:
        out.append(Issue(BLOCK, "misconception_short", f"{m.id}: statement is too short"))
    if find_page(m.contrast_quote, pages) is None:
        out.append(Issue(BLOCK, "contrast_quote", f"{m.id}: contrast quote not found in the PDF: {m.contrast_quote[:60]!r}"))
    return out


# ---- questions ----

def check_question(q: Question, valid_mids: set[str], pages: list[Page]) -> list[Issue]:
    out: list[Issue] = []
    texts = [o.text for o in q.options]
    if len(q.options) != 4:
        out.append(Issue(BLOCK, "options", f"{q.id}: needs exactly 4 options, has {len(q.options)}"))
    if len({norm(t) for t in texts}) != len(texts):
        out.append(Issue(BLOCK, "options_unique", f"{q.id}: two options are the same"))
    if any(not t.strip() for t in texts):
        out.append(Issue(BLOCK, "options_empty", f"{q.id}: an option is empty"))
    correct = [o for o in q.options if o.tag == CORRECT]
    if len(correct) != 1 or correct[0].key != q.answer_key:
        out.append(Issue(BLOCK, "answer_key", f"{q.id}: exactly one option must be tagged 'correct' and match answer_key"))
    bad = [o.tag for o in q.options if o.tag not in (CORRECT, OTHER) and o.tag not in valid_mids]
    if bad:
        out.append(Issue(BLOCK, "tags", f"{q.id}: unknown tags {bad}"))
    if any(b in norm(t) for t in texts for b in BANNED) or any(b in norm(q.stem) for b in BANNED):
        out.append(Issue(BLOCK, "banned_phrase", f"{q.id}: uses a banned phrase (all/none of the above, Recommended)"))
    if not quote_in(q.evidence.quote, " ".join(p.text for p in pages)):
        out.append(Issue(BLOCK, "evidence", f"{q.id}: evidence quote not found in the PDF"))
    elif find_page(q.evidence.quote, pages) != q.evidence.page:
        out.append(Issue(BLOCK, "evidence_page", f"{q.id}: evidence page does not match the quote"))
    if len(correct) == 1:
        longest_wrong = max((len(o.text) for o in q.options if o.tag != CORRECT), default=0)
        if len(correct[0].text) > 12 and len(correct[0].text) > longest_wrong * 1.15:
            out.append(Issue(BLOCK, "longest_correct", f"{q.id}: the correct option is clearly the longest (a hint)"))
        if norm(correct[0].text) in norm(q.stem) and len(correct[0].text) > 6:
            out.append(Issue(WARN, "answer_in_stem", f"{q.id}: the correct option text appears in the question"))
    lens = [len(t) for t in texts]
    if lens and min(lens) >= 12 and max(lens) > 3 * min(lens):
        out.append(Issue(WARN, "uneven_lengths", f"{q.id}: option lengths differ a lot"))
    if not any(o.tag not in (CORRECT, OTHER) for o in q.options):
        out.append(Issue(WARN, "no_misconception_tag", f"{q.id}: no distractor is tagged with a misconception"))
    if len(q.stem.strip()) < 15:
        out.append(Issue(WARN, "short_stem", f"{q.id}: the question is very short"))
    return out
