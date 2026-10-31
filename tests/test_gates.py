import copy

from tutor.gates import blocking, check_concepts, check_graph, check_misconception, check_question
from tutor.models import Edge


def codes(issues):
    return {i.code for i in blocking(issues)}


def test_the_gold_bank_passes_every_blocking_check(bank):
    assert not blocking(check_concepts(bank.concepts, bank.pages))
    for m in bank.misconceptions:
        assert not blocking(check_misconception(m, bank.pages)), m.id
    for q in bank.questions:
        mids = {m.id for m in bank.misconceptions_of(q.concept_id)}
        assert not blocking(check_question(q, mids, bank.pages)), q.id


def test_most_gold_questions_have_a_misconception_tagged_distractor(bank):
    tagged = sum(any(o.tag not in ("correct", "other") for o in q.options) for q in bank.questions)
    assert tagged / len(bank.questions) >= 0.7           # numeric and formula questions have no natural tag


def test_gold_graph_needs_no_repair(bank):
    clean, repairs, errors = check_graph(bank.concepts, bank.edges, 5)
    assert len(clean) == 5 and repairs == [] and errors == []


def test_graph_repairs_cycles_invalid_edges_and_islands(bank):
    cs = bank.concepts
    edges = [Edge(parent="C1", child="C2"), Edge(parent="C2", child="C1"),          # cycle
             Edge(parent="C1", child="C9"), Edge(parent="C3", child="C3"),          # invalid
             Edge(parent="C2", child="C4"), Edge(parent="C4", child="C5")]          # C3 is an island
    clean, repairs, errors = check_graph(cs, edges, 5)
    text = " | ".join(repairs)
    assert "cycle" in text and "invalid" in text and "connected" in text and errors == []
    assert ("C2", "C1") not in {(e.parent, e.child) for e in clean}
    seen = {e.child for e in clean} | {e.parent for e in clean}
    assert seen == {c.id for c in cs}                                              # one connected map


def test_graph_errors_that_code_cannot_fix(bank):
    _, _, errors = check_graph(bank.concepts, [], 3)
    assert any("limit" in e for e in errors)
    _, _, errors = check_graph([], [], 5)
    assert errors == ["no concepts"]


def broken(bank, qid, **change):
    q = copy.deepcopy(bank.question(qid))
    for k, v in change.items():
        setattr(q, k, v)
    return q, {m.id for m in bank.misconceptions_of(q.concept_id)}


def test_each_blocking_problem_is_caught(bank):
    q, mids = broken(bank, "C3-recall-1")
    q.options[1].text = q.options[0].text
    assert "options_unique" in codes(check_question(q, mids, bank.pages))
    q, mids = broken(bank, "C3-recall-1")
    q.options[0].tag = "M9.9"
    assert "tags" in codes(check_question(q, mids, bank.pages))
    q, mids = broken(bank, "C3-recall-1")
    q.options[0].text = "All of the above"
    assert "banned_phrase" in codes(check_question(q, mids, bank.pages))
    q, mids = broken(bank, "C3-recall-1")
    q.evidence.quote = "This sentence is not anywhere in the notes."
    assert "evidence" in codes(check_question(q, mids, bank.pages))
    q, mids = broken(bank, "C3-recall-1")
    q.answer_key = next(o.key for o in q.options if o.tag != "correct")
    assert "answer_key" in codes(check_question(q, mids, bank.pages))
    q, mids = broken(bank, "C5-recall-2")
    next(o for o in q.options if o.tag == "correct").text = "Add all of the individual resistances together as one sum"
    assert "longest_correct" in codes(check_question(q, mids, bank.pages))
    q, mids = broken(bank, "C3-recall-1")
    q.options = q.options[:3]
    assert "options" in codes(check_question(q, mids, bank.pages))


def test_untagged_questions_only_warn(bank):
    q, mids = broken(bank, "C1-recall-1")
    for o in q.options:
        if o.tag not in ("correct",):
            o.tag = "other"
    issues = check_question(q, mids, bank.pages)
    assert not blocking(issues) and any(i.code == "no_misconception_tag" for i in issues)


def test_misconception_checks(bank):
    m = copy.deepcopy(bank.misconceptions[0])
    m.contrast_quote = "Not in the notes at all, sorry."
    assert codes(check_misconception(m, bank.pages)) == {"contrast_quote"}
    m = copy.deepcopy(bank.misconceptions[0])
    m.statement = "Too short."
    assert "misconception_short" in codes(check_misconception(m, bank.pages))
