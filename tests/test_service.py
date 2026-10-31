import json

import pytest

from tutor import service
from tutor.service import TutorError

ALL = {"C1", "C2", "C3", "C4", "C5"}


def answer_round(conn, bank, sid, choose):
    """Answer questions until the round ends. choose(question) -> (key, reason, is_guess)."""
    while True:
        p = service.progress(conn, bank, sid)
        if p.phase != "question":
            return p
        q = bank.question(p.question_id)
        key, reason, guess = choose(q)
        service.submit_answer(conn, bank, sid, q.id, key, reason, guess)


def right(q):
    return q.answer_key, "I remember that this is what the notes say about it.", False


def test_a_student_who_knows_everything_is_done_after_two_rounds(conn, bank, run):
    sid = run(ALL)
    assert service.student(conn, sid)["status"] == "done"
    assert conn.execute("SELECT COUNT(*) FROM answers WHERE student_id=?", (sid,)).fetchone()[0] == 20
    assert all(v["state"] == "understood" for v in service.mastery_snapshot(conn, bank, sid).values())


def test_only_the_weak_concept_goes_to_round_three(conn, bank, run):
    sid = run(ALL - {"C3"}, fav={"C3": "M3.1"})
    r3 = [a for a in service.answers_of(conn, sid) if a["round"] == 3]
    assert len(r3) == 2 and {bank.question(a["question_id"]).concept_id for a in r3} == {"C3"}
    snap = service.mastery_snapshot(conn, bank, sid)
    assert snap["C3"]["state"] == "missing"
    assert all(snap[c]["state"] == "understood" for c in ALL - {"C3"})


def test_no_feedback_during_the_test(conn, bank):
    sid = service.join(conn, "ana", "DEMO-ALL")
    view = service.current_question(conn, bank, sid)
    assert set(view) == {"question_id", "stem", "round", "index", "total", "options"}
    assert all(set(o) == {"label", "key", "text"} for o in view["options"])   # no tag, no answer key
    res = service.submit_answer(conn, bank, sid, view["question_id"], view["options"][0]["key"], "because I think that is the right one")
    assert not any("correct" in k for k in res) and set(res) == {"mastery", "round_complete", "next"}


def test_group_tag_comes_from_the_class_code(conn):
    assert service.student(conn, service.join(conn, "a", "demo-p13"))["group_tag"] == "read_p1_3"
    assert service.student(conn, service.join(conn, "b", "XYZ"))["group_tag"] == "xyz"


def test_input_checks(conn, bank):
    sid = service.join(conn, "ana")
    q = service.current_question(conn, bank, sid)
    key = q["options"][0]["key"]
    with pytest.raises(TutorError, match="at least 6 words"):
        service.submit_answer(conn, bank, sid, q["question_id"], key, "too short")
    with pytest.raises(TutorError, match="Please pick"):
        service.submit_answer(conn, bank, sid, q["question_id"], "Z", "a long enough explanation of my choice")
    other_round = next(x.id for x in bank.questions if x.kind == "apply")
    with pytest.raises(TutorError, match="not part of the current round"):
        service.submit_answer(conn, bank, sid, other_round, "A", "a long enough explanation of my choice")
    service.submit_answer(conn, bank, sid, q["question_id"], key, "", is_guess=True)       # a guess needs no reason
    with pytest.raises(TutorError, match="not part of the current round"):                # no second answer
        service.submit_answer(conn, bank, sid, q["question_id"], key, "", is_guess=True)
    with pytest.raises(TutorError):
        service.join(conn, "   ")


def test_a_right_answer_with_a_flawed_reason_is_not_credited(conn, bank, lexical):
    sid = service.join(conn, "ben")
    flawed = "I think current is the amount of charge stored in the wire, not a rate of flow."

    def choose(q):
        return (q.answer_key, flawed, False) if q.id == "C1-recall-1" else right(q)

    assert service.progress(conn, bank, sid).phase == "question"
    answer_round(conn, bank, sid, choose)
    assert service.progress(conn, bank, sid).phase == "judge_pending"
    service.finish_round(conn, bank, sid, lexical)
    a = next(x for x in service.answers_of(conn, sid) if x["question_id"] == "C1-recall-1")
    assert a["is_correct"] == 1 and a["verdict"] == "misconception" and a["misconception_id"] == "M1.1"
    assert a["credited"] is False and "stored in the wire" in a["evidence_quote"]
    answer_round(conn, bank, sid, right)
    service.finish_round(conn, bank, sid, lexical)
    r3 = [x for x in service.answers_of(conn, sid) if x["round"] == 3] or []
    plan = json.loads(service.student(conn, sid)["round3_plan"])
    assert {bank.question(q).concept_id for q in plan} == {"C1"}                   # C1 is no clean sweep
    assert r3 == []                                                               # not answered yet


def test_round_three_plan_is_frozen_once_made(conn, bank, run, lexical):
    sid = run(ALL - {"C2"})
    plan = service.student(conn, sid)["round3_plan"]
    conn.execute("UPDATE judgements SET credit=0")                                # pretend a later re-judge
    assert service.progress(conn, bank, sid).phase == "done"
    assert service.student(conn, sid)["round3_plan"] == plan


def test_a_judge_that_crashes_does_not_stop_the_student(conn, bank):
    sid = service.join(conn, "cy")
    answer_round(conn, bank, sid, right)

    def broken(items):
        raise RuntimeError("boom")

    nxt = service.finish_round(conn, bank, sid, broken)
    assert nxt.phase == "question" and nxt.round == 2
    assert conn.execute("SELECT COUNT(*) FROM judgements WHERE source='none'").fetchone()[0] == 10


def test_mastery_log_has_one_row_per_answer(conn, bank, run):
    sid = run(ALL - {"C5"})
    n = conn.execute("SELECT COUNT(*) FROM answers WHERE student_id=?", (sid,)).fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM mastery_log WHERE student_id=?", (sid,)).fetchone()[0] == n


def test_results_lists_what_to_read_again(conn, bank, run):
    sid = run(ALL - {"C4"}, fav={"C4": "M4.1"})
    res = service.results(conn, bank, sid)
    assert {c["id"]: c["state"] for c in res["concepts"]}["C4"] == "missing"
    assert res["review"] and all(r["page"] and r["correct_answer"] and r["explanation"] for r in res["review"])
    assert {r["concept"] for r in res["review"]} == {"Ohm's law"}
