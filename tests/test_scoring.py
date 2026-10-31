from tutor import exams, scoring, service

ALL = {"C1", "C2", "C3", "C4", "C5"}


def test_a_perfect_student_scores_full_marks_on_the_main_questions(conn, run):
    sid = run(ALL)
    assert scoring.score_for(conn, sid) == {"credited": 20, "asked": 20, "percent": 100, "follow_ups": 0}


def test_wrong_answers_score_zero_and_follow_ups_are_not_part_of_the_score(conn, run):
    sid = run(set())
    s = scoring.score_for(conn, sid)
    assert (s["credited"], s["asked"], s["percent"], s["follow_ups"]) == (0, 20, 0, 10)


def test_a_partly_known_subject_gives_a_partly_right_score(conn, run):
    sid = run({"C1", "C2", "C3"})                         # 3 concepts x 4 main questions right, 2 concepts wrong
    assert scoring.score_for(conn, sid)["credited"] == 12 and scoring.score_for(conn, sid)["percent"] == 60


def test_a_right_answer_with_a_flawed_reason_is_not_in_the_score(conn, bank, lexical):
    sid = service.join(conn, "ben")
    flawed = "I think current is the amount of charge stored in the wire, not a rate of flow."
    while (p := service.progress(conn, bank, sid)).phase == "question":
        q = bank.question(p.question_id)
        service.submit_answer(conn, bank, sid, q.id, q.answer_key,
                              flawed if q.id == "C1-recall-1" else "I remember that this is what the notes say about it")
    service.finish_round(conn, bank, sid, lexical)
    assert scoring.score_for(conn, sid)["credited"] == 9                                # 10 right, one not credited


def test_an_unstarted_student_has_no_score(conn):
    assert scoring.score_for(conn, service.join(conn, "new")) == {"credited": 0, "asked": 0, "percent": None, "follow_ups": 0}


def test_the_class_table_is_best_first_with_an_average(conn, bank, run):
    e = exams.create_exam(conn, "t", 30, bank_name="electricity_gold")
    other = exams.create_exam(conn, "other", 30, bank_name="electricity_gold")
    for name, known in (("low", set()), ("high", ALL), ("mid", {"C1", "C2", "C3"})):
        exams.attach(conn, [run(known, nickname=name)], e["code"])
    exams.attach(conn, [run(ALL, nickname="elsewhere")], other["code"])
    exams.attach(conn, [service.join(conn, "slow")], e["code"])                         # started, not finished
    t = scoring.exam_scores(conn, bank, e["code"])
    assert [r["nickname"] for r in t["students"]] == ["high", "mid", "low"]            # the unfinished one is left out
    assert [r["percent"] for r in t["students"]] == [100, 60, 0] and t["average"] == 53
    assert (t["best"], t["lowest"]) == (100, 0)
    assert t["students"][0]["states"]["C3"] == "understood" and t["students"][2]["states"]["C3"] == "missing"
    assert len(scoring.exam_scores(conn, bank, e["code"], only_done=False)["students"]) == 4
    assert scoring.exam_scores(conn, bank, "NONE00")["average"] is None


def test_real_and_simulated_students_are_separated(conn, bank, run):
    e = exams.create_exam(conn, "t", 30, bank_name="electricity_gold")
    exams.attach(conn, [run(ALL, nickname="real", is_simulated=False)], e["code"])
    exams.attach(conn, [run(set(), nickname="sim", is_simulated=True)], e["code"])
    assert [r["nickname"] for r in scoring.exam_scores(conn, bank, e["code"], "real")["students"]] == ["real"]
    assert [r["nickname"] for r in scoring.exam_scores(conn, bank, e["code"], "simulated")["students"]] == ["sim"]
