from tutor import rounds


def test_round1_is_all_recall_questions_and_stable(bank):
    a = rounds.plan_round(bank, "s1", 1)
    assert len(a) == 10 and all(bank.question(q).kind == "recall" for q in a)
    assert a == rounds.plan_round(bank, "s1", 1)          # same student, same order
    assert a != rounds.plan_round(bank, "s2", 1)          # other students get another order


def test_same_concept_is_never_back_to_back(bank):
    for r in (1, 2):
        ids = rounds.plan_round(bank, "s1", r)
        assert all(bank.question(x).concept_id != bank.question(y).concept_id for x, y in zip(ids, ids[1:]))


def test_round3_needs_the_flagged_set(bank):
    assert rounds.plan_round(bank, "s1", 3) == []
    ids = rounds.plan_round(bank, "s1", 3, {"C3", "C5"})
    assert len(ids) == 4 and {bank.question(q).concept_id for q in ids} == {"C3", "C5"}
    assert {bank.question(q).kind for q in ids} == {"tiebreak", "simple"}


def test_clean_sweep_means_all_four_credited(bank):
    credited = {q.id: True for q in bank.questions if q.kind in ("recall", "apply")}
    assert rounds.flagged_concepts(bank, credited) == set()
    credited["C2-apply-1"] = False
    assert rounds.flagged_concepts(bank, credited) == {"C2"}
    del credited["C4-recall-1"]                           # unanswered counts as not credited
    assert rounds.flagged_concepts(bank, credited) == {"C2", "C4"}


def test_option_order_is_a_stable_permutation():
    keys = list("ABCD")
    o = rounds.option_order("s1", "C1-recall-1", keys)
    assert sorted(o) == keys and o == rounds.option_order("s1", "C1-recall-1", keys)
