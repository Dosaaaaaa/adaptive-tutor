from tutor import service, stats

ALL = {"C1", "C2", "C3", "C4", "C5"}
FIRST3 = {"C1", "C2", "C3"}


def concept(rep, cid):
    return next(c for c in rep["concepts"] if c["id"] == cid)


def test_question_difficulty_is_measured_from_answers(conn, bank, run):
    for i in range(6):
        run(ALL, nickname=f"k{i}")
    for i in range(4):
        run(set(), nickname=f"n{i}")
    qs = {s["question_id"]: s for s in stats.question_stats(conn, bank)}
    q = qs["C1-recall-1"]
    assert (q["n"], q["k"]) == (10, 6) and round(q["p"], 3) == round(7 / 12, 3) and q["label"] == "Medium"
    assert sum(o["picked"] for o in q["options"]) == 10
    r3 = qs["C1-simple-1"]                                    # only the 4 who struggled ever saw round 3
    assert (r3["n"], r3["k"]) == (4, 0) and r3["label"] == "Hard" and r3["flags"] == []   # n too small to flag
    assert stats.question_stats(conn, bank)[0]["p"] <= stats.question_stats(conn, bank)[-1]["p"]   # hardest first


def test_flags_for_questions_that_look_broken(conn, bank, run):
    for i in range(10):
        run(set(), nickname=f"n{i}")
    flagged = {s["question_id"]: s["flags"] for s in stats.question_stats(conn, bank)}
    assert "check_question" in flagged["C1-recall-1"]         # everybody wrong: below chance, check the key
    for i in range(10):
        run(ALL, nickname=f"k{i}")
    easy = {s["question_id"]: s["flags"] for s in stats.question_stats(conn, bank, include="all")}
    assert "check_question" not in easy["C1-recall-1"]


def test_root_gap_separates_the_cause_from_the_fallout(conn, bank, run):
    for i in range(6):
        run(FIRST3, nickname=f"s{i}", fav={"C4": "M4.1"})     # know pages 1 to 3, not Ohm's law or series
    rep = stats.class_report(conn, bank)
    c4, c5 = concept(rep, "C4"), concept(rep, "C5")
    assert (c4["root_count"], c4["start_here"]) == (6, True)  # parents C2 and C3 are fine: C4 is the real gap
    assert (c5["root_count"], c5["start_here"]) == (0, False) # C5 is weak only because C4 is
    assert [c["id"] for c in rep["cards"]] == ["C4", "C5"]
    assert c4["status"] == "red" and concept(rep, "C1")["status"] == "green"
    assert concept(rep, "C4")["holds_back"] == ["Series circuits"] and c4["headline"] == "6 of 6 students have not understood this yet"
    assert c4["top_mistake"]["id"].startswith("M4") and c4["top_mistake"]["students"] >= 1
    assert "START HERE" in stats.format_report(rep) and rep["graph"]["edges"] and len(rep["graph"]["nodes"]) == 5


def test_a_class_that_knows_everything_needs_no_cards(conn, bank, run):
    for i in range(5):
        run(ALL, nickname=f"k{i}")
    rep = stats.class_report(conn, bank)
    assert rep["cards"] == [] and all(c["status"] == "green" for c in rep["concepts"])
    assert "No concept needs re-teaching" in stats.format_report(rep)


def test_real_and_simulated_students_are_never_mixed(conn, bank, run):
    for i in range(3):
        run(ALL, nickname=f"real{i}", is_simulated=False)
    for i in range(2):
        run(set(), nickname=f"sim{i}", is_simulated=True)
    assert stats.class_report(conn, bank)["students"] | {} == stats.class_report(conn, bank, "all")["students"] | {}
    real, sim = stats.class_report(conn, bank, "real"), stats.class_report(conn, bank, "simulated")
    assert real["students"]["counted"] == 3 and real["students"]["simulated"] == 0
    assert sim["students"]["counted"] == 2 and sim["students"]["real"] == 0
    assert all(c["status"] == "green" for c in real["concepts"]) and all(c["status"] == "red" for c in sim["concepts"])


def test_students_still_in_progress_are_counted_separately(conn, bank, run):
    run(ALL)
    service.join(conn, "slow")
    rep = stats.class_report(conn, bank)
    assert rep["students"]["counted"] == 1 and rep["students"]["in_progress"] == 1
    assert stats.class_report(conn, bank, only_done=False)["students"]["counted"] == 2


def test_empty_class_does_not_crash(conn, bank):
    rep = stats.class_report(conn, bank)
    assert rep["cards"] == [] and rep["students"]["counted"] == 0
    assert concept(rep, "C1")["headline"] == "No data yet"
    assert stats.table_counts(conn)["questions"] == 30


def test_a_simulated_class_is_reproducible(bank):
    """Same seed, same class: the report must not change from run to run (it used to, through random student ids)."""
    from tutor.db import connect, load_bank_into_db
    from tutor.simulate import simulate_class

    def report():
        c = connect(":memory:")
        load_bank_into_db(c, bank)
        simulate_class(c, bank, 14, 7)
        r = stats.class_report(c, bank)
        return ([(x["id"], x["understood"], x["root_count"], x["start_here"]) for x in r["concepts"]],
                [m["id"] for m in r["mistakes"]], r["grid"])

    assert report() == report() == report()


def test_reports_and_exports_can_be_limited_to_one_exam(conn, bank, run):
    from tutor import exams
    a, b = (exams.create_exam(conn, t, 30, bank_name="electricity_gold") for t in ("a", "b"))
    exams.attach(conn, [run(ALL, nickname="x1"), run(ALL, nickname="x2")], a["code"])
    exams.attach(conn, [run(set(), nickname="y1")], b["code"])
    ra, rb = stats.class_report(conn, bank, exam=a["code"]), stats.class_report(conn, bank, exam=b["code"])
    assert ra["students"]["counted"] == 2 and rb["students"]["counted"] == 1
    assert all(c["status"] == "green" for c in ra["concepts"]) and all(c["status"] == "red" for c in rb["concepts"])
    assert stats.class_report(conn, bank)["students"]["counted"] == 3                   # no filter: the old behaviour
    assert stats.question_stats(conn, bank, exam=b["code"])[0]["n"] == 1
    rows_a = stats.export_rows(conn, bank, exam=a["code"])
    assert {r["nickname"] for r in rows_a} == {"x1", "x2"} and all(r["concept_id"] and r["kind"] for r in rows_a)
    assert len(stats.export_rows(conn)) == len(rows_a) + len(stats.export_rows(conn, exam=b["code"]))
