from pathlib import Path

import pytest

from tests.fakes import GoldLLM
from tutor import config
from tutor.build_bank import BuildError, build_bank
from tutor.gates import blocking, check_question
from tutor.models import load_bank

PDF = config.ROOT / "demo" / "Electricity_Basics.pdf"


def build(tmp_path, gold, gen=None, ver="same", **kw):
    gen = gen or GoldLLM(gold)
    ver = GoldLLM(gold) if ver == "same" else ver
    return build_bank(PDF, "t", gen, ver, out_dir=tmp_path / "bank", say=lambda *_: None, **kw), gen, ver


def test_the_pipeline_rebuilds_the_gold_bank_from_the_pdf(tmp_path, bank):
    (built, report), gen, ver = build(tmp_path, bank)
    assert [c.id for c in built.concepts] == [c.id for c in bank.concepts]
    assert [c.page for c in built.concepts] == [1, 2, 3, 4, 5]
    assert {(e.parent, e.child) for e in built.edges} == {(e.parent, e.child) for e in bank.edges}
    assert len(built.questions) == 30 and len(built.misconceptions) == 15 and report.rejected == []
    for q in built.questions:
        assert not blocking(check_question(q, {m.id for m in built.misconceptions_of(q.concept_id)}, built.pages))
        assert q.checks["blind_votes"] == [q.answer_key] * 2 and q.checks["supported_options"] == [q.answer_key]   # two agreeing votes settle it
        assert q.correct.text == bank.question(q.id).correct.text
    assert {q.answer_key for q in built.questions} == set("ABCD")           # the code spreads the right answers
    assert (tmp_path / "bank" / "build_report.md").exists() and load_bank(tmp_path / "bank").name == "t"
    assert built.manifest["ai_checks"] is True and report.counts["questions_kept"] == 30


def test_a_question_the_checker_disagrees_with_is_regenerated(tmp_path, bank):
    (built, report), _, _ = build(tmp_path, bank, ver=GoldLLM(bank, wrong_votes={"C2-apply-1": 1}))
    assert len(built.questions) == 30
    assert any(q == "C2-apply-1" and "repaired" in why for q, why in report.rejected)
    assert "C2-apply-1" in [q.id for q in built.questions]


def test_a_question_that_never_passes_is_dropped_and_reported(tmp_path, bank):
    (built, report), _, _ = build(tmp_path, bank, ver=GoldLLM(bank, wrong_votes={"C3-simple-1": 99}))
    assert "C3-simple-1" not in [q.id for q in built.questions] and len(built.questions) == 29
    assert any(q == "C3-simple-1" and "dropped" in why for q, why in report.rejected)
    assert "dropped" in report.markdown()


def test_a_question_that_leaks_another_answer_is_dropped(tmp_path, bank):
    leak = [{"question": "C1-simple-1", "reveals_answer_of": "C1-recall-2", "why": "names the instrument"}]
    (built, report), _, _ = build(tmp_path, bank, ver=GoldLLM(bank, leaks=leak))
    assert "C1-simple-1" not in [q.id for q in built.questions] and len(built.questions) == 29


def test_an_invented_quote_is_caught_by_the_code_and_regenerated(tmp_path, bank):
    gen = GoldLLM(bank, bad_quote_once={"C1-recall-1"})
    (built, report), _, _ = build(tmp_path, bank, gen=gen)
    assert "C1-recall-1" in [q.id for q in built.questions]
    assert "regen" in gen.tasks and report.rejected == []                    # fixed before it reached the checker


def test_without_a_verifier_the_report_says_the_ai_checks_did_not_run(tmp_path, bank):
    (built, report), _, _ = build(tmp_path, bank, ver=None)
    assert built.manifest["ai_checks"] is False and any("did NOT run" in w for w in report.warnings)
    assert "blind_solve" not in GoldLLM(bank).tasks


def test_a_broken_concept_extraction_stops_the_build_with_a_clear_message(tmp_path, bank):
    class NoQuotes(GoldLLM):
        def _concepts(self, prompt):
            d = super()._concepts(prompt)
            for c in d["concepts"]:
                c["quote"] = "invented sentence that is nowhere in the document"
            return d

    with pytest.raises(BuildError, match="valid concept map"):
        build(tmp_path, bank, gen=NoQuotes(bank))


def test_call_budget_is_in_the_expected_range(tmp_path, bank):
    (_, report), gen, ver = build(tmp_path, bank)
    assert gen.stats["calls"] == 1 + 5 + 5                                   # concepts + misconceptions + questions
    assert ver.stats["calls"] == 2 + 1 + 1                                   # the 2 votes that settle it + support + leak: one call each for all 30 questions
