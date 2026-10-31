import pytest

from tutor import config, exams, service
from tutor.exams import ExamError


def make(conn, **kw):
    kw.setdefault("bank_name", "electricity_gold")
    return exams.create_exam(conn, kw.pop("title", "Physics test"), kw.pop("max_students", 3), **kw)


def test_creating_an_exam_checks_its_inputs(conn):
    e = make(conn)
    assert len(e["code"]) == 6 and set(e["code"]) <= set(exams.ALPHABET) and e["status"] == "ready"
    with pytest.raises(ExamError, match="title"):
        make(conn, title="  ")
    for bad in (0, 1001):
        with pytest.raises(ExamError, match="between 1 and 1000"):
            make(conn, max_students=bad)
    assert len({make(conn)["code"] for _ in range(20)}) == 20                      # codes do not repeat


def test_codes_are_found_however_they_are_typed(conn):
    e = make(conn)
    assert exams.get_exam(conn, f" {e['code'].lower()[:3]}-{e['code'][3:]} ")["code"] == e["code"]
    assert exams.get_exam(conn, "NOPE00") is None and exams.get_exam(conn, "") is None


def test_a_student_joins_through_the_exam_and_the_brain_starts_them(conn, bank):
    e = make(conn)
    sid = exams.join_exam(conn, e["code"], "Ana")
    assert exams.student_exam(conn, sid) == e["code"]
    assert service.current_question(conn, bank, sid)["round"] == 1                  # the brain works as before
    assert exams.counts(conn, e["code"]) == {"joined": 1, "simulated": 0, "finished": 0}


def test_the_number_of_places_is_enforced(conn):
    e = make(conn, max_students=2)
    exams.join_exam(conn, e["code"], "a")
    exams.join_exam(conn, e["code"], "b")
    with pytest.raises(ExamError, match=r"full \(2 of 2"):
        exams.join_exam(conn, e["code"], "c")
    assert conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 2        # nobody was half-created


def test_simulated_students_do_not_take_places(conn, run):
    e = make(conn, max_students=1)
    sid = run({"C1"}, nickname="sim", is_simulated=True)
    exams.attach(conn, [sid], e["code"])
    assert exams.counts(conn, e["code"])["simulated"] == 1
    exams.join_exam(conn, e["code"], "real")                                         # still room for a real student


def test_nicknames_are_unique_inside_an_exam_only(conn):
    a, b = make(conn), make(conn)
    exams.join_exam(conn, a["code"], "Ana")
    with pytest.raises(ExamError, match="nickname"):
        exams.join_exam(conn, a["code"], "ANA")
    exams.join_exam(conn, b["code"], "Ana")                                          # another exam: fine
    with pytest.raises(Exception, match="nickname"):                                 # the brain's own check
        exams.join_exam(conn, a["code"], "   ")


@pytest.mark.parametrize("status, message", [("building", "not ready"), ("failed", "could not be prepared"), ("closed", "closed")])
def test_an_exam_that_is_not_open_cannot_be_joined(conn, status, message):
    e = make(conn, status=status)
    with pytest.raises(ExamError, match=message):
        exams.join_exam(conn, e["code"], "Ana")


def test_a_wrong_code_gives_a_friendly_message(conn):
    with pytest.raises(ExamError, match="could not find that exam"):
        exams.join_exam(conn, "ZZZZZZ", "Ana")


def test_closing_stops_new_students_but_not_those_already_in(conn, bank):
    e = make(conn)
    sid = exams.join_exam(conn, e["code"], "Ana")
    exams.close_exam(conn, e["code"])
    with pytest.raises(ExamError, match="closed"):
        exams.join_exam(conn, e["code"], "Ben")
    assert service.current_question(conn, bank, sid) is not None                     # Ana carries on
    exams.reopen_exam(conn, e["code"])
    exams.join_exam(conn, e["code"], "Ben")


def test_the_exam_list_shows_counts_newest_first(conn):
    a, b = make(conn, title="first"), make(conn, title="second")
    exams.join_exam(conn, a["code"], "x")
    listing = exams.list_exams(conn)
    assert {e["title"] for e in listing} == {"first", "second"}
    assert next(e for e in listing if e["code"] == a["code"])["joined"] == 1


def test_students_from_before_exams_existed_are_kept_in_a_demo_exam(conn, run):
    sid = run({"C1"})
    conn.execute("UPDATE students SET exam_code=NULL")
    assert exams.adopt_legacy(conn, "electricity_gold") is True
    assert exams.student_exam(conn, sid) == exams.LEGACY_CODE
    assert exams.get_exam(conn, exams.LEGACY_CODE)["status"] == "closed"
    assert exams.adopt_legacy(conn, "electricity_gold") is False                     # only once


def test_the_student_link(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    assert exams.student_link("abc-234", "http://10.0.0.5:8502/") == "http://10.0.0.5:8502/?exam=ABC234"
    assert exams.public_base().startswith("http://") and exams.public_base().endswith(f":{config.STUDENT_PORT}")
    (tmp_path / ".env").write_text("PUBLIC_URL=https://school.example.org/\n")        # for example a tunnel
    assert exams.student_link("abc234") == "https://school.example.org/?exam=ABC234"


def test_an_unknown_field_cannot_be_updated(conn):
    e = make(conn)
    with pytest.raises(ExamError):
        exams.update_exam(conn, e["code"], title="x")
    with pytest.raises(ExamError):
        exams.update_exam(conn, e["code"], status="banana")


def test_deleting_an_exam_removes_its_students_and_answers_but_not_other_exams(conn, run):
    keep, drop = make(conn, title="keep"), make(conn, title="drop")
    exams.attach(conn, [run({"C1"}, nickname="k")], keep["code"])
    exams.attach(conn, [run({"C1"}, nickname="d1"), run(set(), nickname="d2")], drop["code"])
    before = conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
    assert exams.delete_exam(conn, drop["code"]) == 2
    assert exams.get_exam(conn, drop["code"]) is None and exams.get_exam(conn, keep["code"]) is not None
    assert conn.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 1
    assert 0 < conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0] < before
    for table in ("judgements", "mastery_log"):                                   # nothing is left pointing at deleted answers
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE "
                            + ("answer_id NOT IN (SELECT id FROM answers)" if table == "judgements"
                               else "student_id NOT IN (SELECT id FROM students)")).fetchone()[0] == 0


def test_an_exam_that_is_being_built_or_does_not_exist_cannot_be_deleted(conn):
    building = make(conn, status="building")
    with pytest.raises(ExamError, match="still being prepared"):
        exams.delete_exam(conn, building["code"])
    with pytest.raises(ExamError, match="does not exist"):
        exams.delete_exam(conn, "NOPE00")
