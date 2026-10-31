"""PDF to checked quiz bank (SPEC 5). The teacher's only input is the PDF.

Stages: 0 extract text | 1 concepts and prerequisite edges | 2 misconceptions | 3 questions |
4 automatic checks with repair (a second AI family blind-solves and checks every question).
Run:  python -m tutor.build_bank demo/Electricity_Basics.pdf --name electricity_llm
"""
from __future__ import annotations

import argparse
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import config
from .extract import doc_text, extract_pages, pdf_sha256
from .gates import BLOCK, Issue, blocking, check_concepts, check_graph, check_misconception, check_question
from .models import (CORRECT, OTHER, Bank, Concept, ConceptsOut, Edge, Evidence, GenQuestion, Misconception,
                     MisconceptionsOut, Option, Page, Question, QuestionsOut, save_bank)
from .quotes import find_page, norm
from .verify import _prompt, blind_solve, decide, leak_dup_check, support_check


class BuildError(Exception):
    pass


@dataclass
class Report:
    name: str
    pdf: str
    pages: int
    models: dict = field(default_factory=dict)
    repairs: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    rejected: list = field(default_factory=list)     # (question id, what happened)
    low_confidence: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    ai_calls: dict = field(default_factory=dict)
    seconds: float = 0.0

    def markdown(self) -> str:
        c = self.counts
        made, kept = c.get("questions_generated", 0), c.get("questions_kept", 0)
        lines = [f"# Build report: {self.name}", "",
                 f"- PDF: `{self.pdf}` ({self.pages} pages)",
                 f"- Generator: `{self.models.get('generator', 'n/a')}`  Verifier: `{self.models.get('verifier', 'n/a')}`",
                 f"- Concepts: {c.get('concepts', 0)}, edges: {c.get('edges', 0)}, misconceptions: {c.get('misconceptions', 0)}",
                 f"- Questions generated: {made}, kept: {kept}" + (f" ({100 * kept // made}% passed)" if made else ""),
                 f"- AI calls (not from cache): {self.ai_calls}", f"- Time: {self.seconds:.0f} s", ""]
        for title, items in (("Repairs made by code", self.repairs), ("Low-confidence concepts", self.low_confidence),
                             ("Warnings", self.warnings)):
            if items:
                lines += [f"## {title}", *[f"- {i}" for i in items], ""]
        if self.rejected:
            lines += ["## Questions that failed a check", "", "| question | what happened |", "|---|---|"]
            lines += [f"| {q} | {why} |" for q, why in self.rejected]
        return "\n".join(lines) + "\n"


# ---- stage 1: concepts ----

def _remap(out: ConceptsOut, pages: list[Page]) -> tuple[list[Concept], list[Edge]]:
    """Give concepts clean ids C1..Cn in page order and take each page from where the quote really is."""
    order = sorted(enumerate(out.concepts), key=lambda p: (find_page(p[1].quote, pages) or p[1].page, p[0]))
    new, concepts = {}, []
    for i, (_, c) in enumerate(order, 1):
        new[c.id] = f"C{i}"
        concepts.append(c.model_copy(update={"id": f"C{i}", "page": find_page(c.quote, pages) or c.page}))
    edges = [Edge(parent=new[e.parent], child=new[e.child], why=e.why)
             for e in out.edges if e.parent in new and e.child in new]
    return concepts, edges


def stage_concepts(gen, pages, max_concepts, attempts):
    feedback, problems = "", []
    for n in range(attempts):
        prompt = _prompt("concepts", MAX=str(max_concepts), DOC=doc_text(pages), FEEDBACK=feedback)
        concepts, edges = _remap(gen.call_json("concepts", prompt, ConceptsOut, salt=f"try{n}"), pages)
        clean, repairs, errors = check_graph(concepts, edges, max_concepts)
        problems = [str(i) for i in blocking(check_concepts(concepts, pages))] + errors
        if not problems:
            return concepts, clean, repairs
        feedback = "\nYour previous answer had these problems. Fix them:\n- " + "\n- ".join(problems) + "\n"
    raise BuildError("Could not extract a valid concept map: " + "; ".join(problems))


# ---- context for later stages ----

def context_for(concept: Concept, concepts: list[Concept], edges: list[Edge], pages: list[Page]) -> str:
    full = doc_text(pages)
    if len(full) <= config.CONTEXT_CHARS:
        return full
    ids, frontier = {concept.id}, {concept.id}
    for _ in range(2):  # the concept and two levels of prerequisites
        frontier = {e.parent for e in edges if e.child in frontier}
        ids |= frontier
    near = doc_text(pages, {c.page for c in concepts if c.id in ids})
    return near if len(near) <= config.CONTEXT_CHARS else doc_text(pages, {concept.page})


# ---- stage 2: misconceptions ----

def stage_misconceptions(gen, pages, concept, context, attempts) -> list[Misconception]:
    n, good, feedback = int(concept.id[1:]), [], ""
    for t in range(attempts):
        prompt = _prompt("misconceptions", CID=concept.id, NAME=concept.name, SUMMARY=concept.summary,
                         DOC=context, FEEDBACK=feedback)
        out = gen.call_json("misconceptions", prompt, MisconceptionsOut, salt=f"try{t}")
        bad = []
        for g in out.misconceptions:
            m = Misconception(id=f"M{n}.{len(good) + 1}", concept_id=concept.id, statement=g.statement.strip(),
                              contrast_quote=g.contrast_quote.strip())
            issues = blocking(check_misconception(m, pages))
            dup = any(norm(m.statement) == norm(x.statement) for x in good)
            if issues or dup:
                bad += [str(i) for i in issues] or ["duplicate statement"]
            elif len(good) < 3:
                good.append(m)
        if len(good) >= 3:
            break
        feedback = ("\nYour previous answer had too few valid misconceptions. Problems:\n- " + "\n- ".join(bad or ["fewer than 3"])
                    + "\nWrite 3 valid ones.\n")
    return good


# ---- stage 3: questions ----

def _materialize(gq: GenQuestion, qid: str, concept: Concept, mids: set[str], pages: list[Page]) -> Question:
    opts = [(gq.correct.strip(), CORRECT)] + [(d.text.strip(), d.tag if d.tag in mids else OTHER)
                                              for d in gq.distractors[:3]]
    random.Random(f"build:{qid}").shuffle(opts)  # the code, not the AI, decides where the right answer goes
    options = [Option(key="ABCDEFGH"[i], text=t, tag=tag) for i, (t, tag) in enumerate(opts)]
    key = next((o.key for o in options if o.tag == CORRECT), "A")
    quote = gq.evidence_quote.strip()
    return Question(id=qid, concept_id=concept.id, kind=gq.kind, round=config.ROUND_OF_KIND[gq.kind], stem=gq.stem.strip(),
                    options=options, answer_key=key, rationale=gq.rationale.strip(),
                    evidence=Evidence(page=find_page(quote, pages) or 0, quote=quote))


def _questions_prompt(concept, mis, context, task, avoid, feedback="") -> str:
    listing = "\n".join(f"- {m.id}: {m.statement}" for m in mis) or "(none)"
    avoid_text = ("\nDo not repeat these existing questions or test their facts again:\n"
                  + "\n".join(f"- {s}" for s in avoid) + "\n") if avoid else ""
    return _prompt("questions", CID=concept.id, NAME=concept.name, SUMMARY=concept.summary, MISCONCEPTIONS=listing,
                   TASK=task, AVOID=avoid_text, FEEDBACK=feedback, DOC=context)


def regenerate(gen, concept, mis, context, kind, avoid, issues, salt) -> GenQuestion | None:
    task = f'Write exactly ONE question of kind "{kind}" about this concept.'
    fb = "\nA previous attempt failed these checks. Fix them:\n- " + "\n- ".join(str(i) for i in issues) + "\n"
    try:
        out = gen.call_json("regen", _questions_prompt(concept, mis, context, task, avoid, fb), QuestionsOut, salt=salt)
    except Exception:
        return None
    return next((q for q in out.questions if q.kind == kind), out.questions[0] if out.questions else None)


def stage_questions(gen, pages, concept, mis, context, attempts, report: Report) -> list[Question]:
    mids = {m.id for m in mis}
    per = ", ".join(f"{n} {k}" for k, n in config.PER_KIND.items())
    task = f"Write exactly {sum(config.PER_KIND.values())} questions about THIS concept: {per}."
    pool: dict[str, list[GenQuestion]] = defaultdict(list)
    try:
        for gq in gen.call_json("questions", _questions_prompt(concept, mis, context, task, []), QuestionsOut).questions:
            pool[gq.kind].append(gq)
    except Exception as exc:
        report.warnings.append(f"{concept.id}: the question call failed ({str(exc)[:100]}); regenerating one by one")
    kept: list[Question] = []
    for kind in config.KIND_ORDER:
        for k in range(1, config.PER_KIND[kind] + 1):
            qid, cand, issues = f"{concept.id}-{kind}-{k}", pool[kind].pop(0) if pool[kind] else None, []
            report.counts["questions_generated"] = report.counts.get("questions_generated", 0) + 1
            for attempt in range(attempts):
                if cand is not None:
                    q = _materialize(cand, qid, concept, mids, pages)
                    issues = check_question(q, mids, pages)
                    if not blocking(issues):
                        kept.append(q)
                        report.warnings += [str(i) for i in issues]
                        break
                else:
                    issues = [Issue(BLOCK, "missing", "no question came back")]
                if attempt < attempts - 1:
                    cand = regenerate(gen, concept, mis, context, kind, [x.stem for x in kept], blocking(issues),
                                      f"{qid}#{attempt + 1}")
            else:
                report.rejected.append((qid, "dropped by the code checks: " + "; ".join(str(i) for i in blocking(issues))))
    return kept


# ---- stage 4: AI checks with repair ----

def stage_verify(ver, gen, pages, concepts, edges, mis_by_c, questions, votes, attempts, report: Report) -> list[Question]:
    by_id = {q.id: q for q in questions}
    pending = list(questions)
    concept_of = {c.id: c for c in concepts}
    for rnd in range(attempts + 1):
        if not pending:
            break
        voted = blind_solve(ver, pages, pending, votes)
        sup = support_check(ver, pages, pending)
        failed = {}
        for q in pending:
            why = decide(q, voted.get(q.id, []), sup.get(q.id))
            if why:
                failed[q.id] = why
            else:
                q.checks.update({"grounded": True, "blind_votes": voted[q.id], "supported_options": sorted(sup.get(q.id, [])),
                                 "attempts": rnd + 1})
        if not failed:
            break
        if rnd == attempts:
            for qid, why in failed.items():
                report.rejected.append((qid, f"dropped after {attempts} repairs: " + "; ".join(why)))
                by_id.pop(qid, None)
            break
        pending = []
        for qid, why in failed.items():
            old, c = by_id[qid], concept_of[by_id[qid].concept_id]
            mis = mis_by_c[c.id]
            gq = regenerate(gen, c, mis, context_for(c, concepts, edges, pages), old.kind,
                            [q.stem for q in by_id.values() if q.id != qid and q.concept_id == c.id],
                            [Issue(BLOCK, "ai_check", w) for w in why], f"{qid}#v{rnd + 1}")
            new = _materialize(gq, qid, c, {m.id for m in mis}, pages) if gq else None
            if new is None or blocking(check_question(new, {m.id for m in mis}, pages)):
                report.rejected.append((qid, "could not be repaired: " + "; ".join(why)))
                by_id.pop(qid, None)
            else:
                report.rejected.append((qid, "repaired after: " + "; ".join(why)))
                by_id[qid] = new
                pending.append(new)
    kept = [by_id[q.id] for q in questions if q.id in by_id]
    if len(kept) > 1:  # leaks and duplicates, one call over the whole bank
        found = leak_dup_check(ver, kept)
        drop = {x.get("question") for x in found["leaks"]} | {x.get("b") for x in found["duplicates"]}
        for qid in sorted(d for d in drop if d in by_id):
            report.rejected.append((qid, "dropped: leaks another answer or duplicates a question"))
        kept = [q for q in kept if q.id not in drop]
    return kept


# ---- the whole build ----

def build_bank(pdf: str | Path, name: str, gen, ver=None, *, max_concepts: int = config.MAX_CONCEPTS,
               votes: int = config.VOTES, attempts: int = config.MAX_ATTEMPTS, out_dir: Path | None = None,
               say=print) -> tuple[Bank, Report]:
    t0 = time.time()
    pdf = Path(pdf)
    pages = extract_pages(pdf)
    report = Report(name=name, pdf=pdf.name, pages=len(pages))
    say(f"[0] extracted {len(pages)} pages")
    concepts, edges, repairs = stage_concepts(gen, pages, max_concepts, attempts)
    report.repairs += repairs
    say(f"[1] {len(concepts)} concepts, {len(edges)} prerequisite edges")
    misconceptions: list[Misconception] = []
    questions: list[Question] = []
    mis_by_c: dict[str, list[Misconception]] = {}
    for c in concepts:
        ctx = context_for(c, concepts, edges, pages)
        mis = stage_misconceptions(gen, pages, c, ctx, attempts)
        if len(mis) < 2:
            report.low_confidence.append(f"{c.id} {c.name}: only {len(mis)} valid misconceptions")
        mis_by_c[c.id] = mis
        misconceptions += mis
        questions += stage_questions(gen, pages, c, mis, ctx, attempts, report)
        say(f"[2-3] {c.id} {c.name}: {len(mis)} misconceptions, {sum(q.concept_id == c.id for q in questions)} questions")
    if ver is not None:
        questions = stage_verify(ver, gen, pages, concepts, edges, mis_by_c, questions, votes, attempts, report)
        say(f"[4] {len(questions)} questions passed the AI checks")
    else:
        report.warnings.append("The AI checks were skipped (no verifier): blind solve, one-right-answer and leak checks did NOT run.")
    for c in concepts:
        have = {q.kind for q in questions if q.concept_id == c.id}
        if not {"recall", "apply"} <= have:
            report.low_confidence.append(f"{c.id} {c.name}: missing a {' and '.join(sorted({'recall', 'apply'} - have))} question")
    report.counts.update(concepts=len(concepts), edges=len(edges), misconceptions=len(misconceptions),
                         questions_kept=len(questions))
    report.models = {"generator": f"{gen.provider.name}:{gen.model}" if hasattr(gen, "provider") else "scripted",
                     "verifier": (f"{ver.provider.name}:{ver.model}" if hasattr(ver, "provider") else "scripted") if ver else "none"}
    report.ai_calls = {"generator": getattr(gen, "stats", {}).get("calls", 0),
                       "verifier": getattr(ver, "stats", {}).get("calls", 0) if ver else 0}
    report.seconds = time.time() - t0
    manifest = {"name": name, "pdf": pdf.name, "pdf_sha256": pdf_sha256(pdf), "created": str(date.today()),
                "source": "llm pipeline", "models": report.models, "max_concepts": max_concepts, "votes": votes,
                "ai_checks": ver is not None, "counts": report.counts}
    bank = Bank(manifest, pages, concepts, edges, misconceptions, questions)
    out = out_dir or config.BANK_DIR / name
    save_bank(bank, out)
    (out / "build_report.md").write_text(report.markdown(), encoding="utf-8")
    say(f"wrote {out}")
    return bank, report


def main() -> None:
    from . import llm

    ap = argparse.ArgumentParser(description="Build a quiz bank from a PDF.")
    ap.add_argument("pdf")
    ap.add_argument("--name", default=None)
    ap.add_argument("--max-concepts", type=int, default=config.MAX_CONCEPTS)
    ap.add_argument("--no-verify", action="store_true", help="skip the AI checks (for debugging only)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    name = args.name or f"{Path(args.pdf).stem.lower()}_{pdf_sha256(args.pdf)[:8]}"
    try:
        gen = llm.from_env("generator", cache=not args.no_cache)
        ver = None if args.no_verify else llm.from_env("verifier", cache=not args.no_cache)
        if ver:
            llm.assert_independent(gen, ver)
        _, rep = build_bank(args.pdf, name, gen, ver, max_concepts=args.max_concepts)
    except (llm.ConfigError, llm.LLMError, BuildError) as exc:
        raise SystemExit(f"Build stopped: {exc}")
    print(rep.markdown())


if __name__ == "__main__":
    main()
