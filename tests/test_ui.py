"""Drives the real Streamlit apps headlessly (streamlit.testing): a teacher creating exams, students taking them."""
import pytest
from streamlit.testing.v1 import AppTest

from tutor import config, exams, jobs, service
from tutor.db import connect
from tutor.simulate import simulate_class

UI = config.ROOT / "ui"
PASSWORD = "s3cret-pass"
REASON = "I remember that this is what the notes say about it"
DEMO_PDF = config.ROOT / "demo" / "Electricity_Basics.pdf"


@pytest.fixture()
def db(tmp_path, monkeypatch):
    path = tmp_path / "t.db"
    monkeypatch.setenv("TUTOR_DB", str(path))
    monkeypatch.setenv("BANK_NAME", "electricity_gold")
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")          # no AI keys: the built-in matcher judges
    (tmp_path / ".env").write_text(f"TEACHER_PASSWORD={PASSWORD}\n")
    return path


def button(at, label):
    return next(b for b in at.button if b.label == label)


def has(at, text):
    parts = [m.value for m in at.markdown] + [e.value for e in at.error] + [s.value for s in at.success] \
        + [i.value for i in at.info] + [w.value for w in at.warning] + [t.value for t in at.title] + [c.value for c in at.caption]
    return any(text in p for p in parts)


def new_exam(db, **kw):
    conn = connect(db)
    return exams.create_exam(conn, kw.pop("title", "Physics: Electricity"), kw.pop("seats", 30),
                             bank_name=kw.pop("bank", "electricity_gold"), **kw)


# ======================= students =======================

def student(code=None):
    at = AppTest.from_file(str(UI / "student_app.py"), default_timeout=60)
    if code:
        at.session_state["exam_code"] = code
    return at


def join(at, nick="ana"):
    at.run()
    at.text_input[0].set_value(nick)
    button(at, "Start the exam").click().run()
    return at


def stem_of(at, bank):
    return next(q for q in bank.questions if q.stem == at.subheader[0].value)


def answer_all(at, bank, right=True, reason=REASON):
    while at.radio:
        q = stem_of(at, bank)
        key = q.answer_key if right else next(o.key for o in q.options if o.key != q.answer_key)
        at.radio[0].set_value(key)
        at.text_area[0].set_value(reason)
        button(at, "Submit answer").click().run()
        assert not at.exception, at.exception
    return at


def test_without_a_link_the_student_is_asked_for_the_exam_code(db):
    e = new_exam(db, title="Physics: Electricity")
    at = student().run()
    assert not at.exception and at.text_input[0].label == "Exam code"
    at.text_input[0].set_value(e["code"].lower())                          # typed in lower case: still found
    button(at, "Continue").click().run()
    assert has(at, "Physics: Electricity") and at.text_input[0].label.startswith("Your nickname")


def test_a_wrong_code_says_so(db):
    at = student("ZZZZZZ").run()
    assert has(at, "could not find that exam") and at.text_input[0].label == "Exam code"


def test_the_link_opens_the_exam_and_the_student_takes_it(db, bank):
    e = new_exam(db, title="Physics: Electricity")
    at = student(e["code"]).run()
    assert has(at, "Physics: Electricity") and at.text_input[0].label.startswith("Your nickname")
    at = join(student(e["code"]), "ana")
    assert not at.exception and at.progress[0].proto.text == "Question 1 of 10"
    seen = []
    while at.radio:                                                       # nothing is revealed while the test runs
        seen.append(" ".join(m.value.lower() for m in at.markdown))
        q = stem_of(at, bank)
        at.radio[0].set_value(q.answer_key)
        at.text_area[0].set_value(REASON)
        button(at, "Submit answer").click().run()
    assert not any("right answer" in t or "your score" in t for t in seen)
    assert has(at, "Your score: 20 out of 20 (100%)")                     # ... then the score
    conn = connect(db)
    sid = at.session_state["sid"]
    assert exams.student_exam(conn, sid) == e["code"] and service.student(conn, sid)["status"] == "done"
    assert conn.execute("SELECT COUNT(*) FROM answers WHERE student_id=?", (sid,)).fetchone()[0] == 20


def test_a_struggling_student_gets_a_low_score_and_is_told_what_to_reread(db, bank):
    e = new_exam(db)
    at = answer_all(join(student(e["code"]), "ben"), bank, right=False,
                    reason="I think this one looks right to me because it seems logical")
    assert has(at, "Your score: 0 out of 20 (0%)") and has(at, "read page 3 again")
    assert connect(db).execute("SELECT COUNT(*) FROM answers").fetchone()[0] == 30     # 20 main + 10 follow-up
    assert len(at.expander) >= 10


def test_the_places_limit_stops_extra_students(db):
    e = new_exam(db, seats=1)
    exams.join_exam(connect(db), e["code"], "first")
    at = join(student(e["code"]), "second")
    assert has(at, "This exam is full (1 of 1") and not at.radio


def test_a_build_that_finished_while_nobody_was_looking_opens_the_exam_for_students(db, tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(config, "BANK_DIR", tmp_path / "bank")
    shutil.copytree(config.ROOT / "bank" / "electricity_gold", tmp_path / "bank" / "exam_x")
    log = tmp_path / "x.log"
    log.write_text("[0] extracted 5 pages\nwrote /somewhere/exam_x\n")
    conn = connect(db)
    e = exams.create_exam(conn, "Late", 5, status="building")
    exams.update_exam(conn, e["code"], bank_name="exam_x", log_path=str(log), pid=0)
    at = join(student(e["code"]), "ana")                                  # the build finished: the student is let in
    assert not at.exception and at.progress and exams.get_exam(connect(db), e["code"])["status"] == "ready"


def test_a_nickname_cannot_be_used_twice(db):
    e = new_exam(db)
    exams.join_exam(connect(db), e["code"], "Ana")
    assert has(join(student(e["code"]), "ana"), "already uses that nickname")


@pytest.mark.parametrize("status, text", [("building", "not ready"), ("closed", "closed"), ("failed", "could not be prepared")])
def test_an_exam_that_is_not_open_cannot_be_joined(db, status, text):
    import os
    e = new_exam(db, status=status)
    if status == "building":                                    # a genuine build: its process is alive
        exams.update_exam(connect(db), e["code"], pid=os.getpid())
    at = student(e["code"]).run()
    at.text_input[0].set_value("ana")
    button(at, "Start the exam").click().run()
    assert has(at, text)


def test_an_exam_whose_build_process_died_is_shown_as_failed_not_as_waiting_for_ever(db):
    e = new_exam(db, status="building")                         # no process behind it
    at = student(e["code"]).run()
    at.text_input[0].set_value("ana")
    button(at, "Start the exam").click().run()
    assert has(at, "could not be prepared") and exams.get_exam(connect(db), e["code"])["status"] == "failed"


def test_a_student_already_in_can_finish_after_the_teacher_closes_the_exam(db, bank):
    e = new_exam(db)
    at = join(student(e["code"]), "ana")
    exams.close_exam(connect(db), e["code"])
    at.run()
    assert at.radio and not has(at, "This exam is closed")


def test_a_reload_carries_on_where_the_student_was(db, bank):
    e = new_exam(db)
    at = join(student(e["code"]), "ana")
    for _ in range(3):
        q = stem_of(at, bank)
        at.radio[0].set_value(q.answer_key)
        at.text_area[0].set_value(REASON)
        button(at, "Submit answer").click().run()
    again = student(e["code"])
    again.session_state["sid"] = at.session_state["sid"]
    again.run()
    assert again.progress[0].proto.text == "Question 4 of 10"


def test_a_student_id_from_another_exam_is_not_accepted(db):
    a, b = new_exam(db, title="A"), new_exam(db, title="B")
    sid = exams.join_exam(connect(db), a["code"], "ana")
    at = student(b["code"])
    at.session_state["sid"] = sid
    at.run()
    assert at.text_input[0].label.startswith("Your nickname")             # shown the join form, not ana's progress


def test_input_messages(db, bank):
    e = new_exam(db)
    at = join(student(e["code"]))
    button(at, "Submit answer").click().run()
    assert has(at, "pick an answer")
    at.radio[0].set_value(stem_of(at, bank).options[0].key)
    at.text_area[0].set_value("too short")
    button(at, "Submit answer").click().run()
    assert has(at, "at least 6 words")
    at.checkbox[0].check()
    at.text_area[0].set_value("")
    button(at, "Submit answer").click().run()
    assert at.progress[0].proto.text == "Question 2 of 10"


def test_the_student_app_has_no_way_to_the_dashboard(db):
    import ast
    e = new_exam(db)
    at = join(student(e["code"]))
    assert not at.sidebar.markdown and not at.sidebar.button and not at.sidebar.radio      # no menu, nothing to click to
    tree = ast.parse((UI / "student_app.py").read_text())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "tutor" for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("tutor.")}
    assert imported == {"config", "exams", "jobs", "scoring", "service", "tutor.service"}  # no stats, no simulate, no teacher pages
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"class_report", "question_stats", "export_rows", "exam_scores", "simulate_class", "start_build",
                        "create_exam_from_pdf", "delete_exam", "close_exam"}


# ======================= teacher =======================

def teacher(logged_in=True):
    at = AppTest.from_file(str(UI / "teacher_app.py"), default_timeout=60)
    if logged_in:
        at.session_state["teacher_ok"] = True
    return at


def test_the_teacher_area_asks_for_the_password_and_shows_nothing_before_it(db):
    at = teacher(logged_in=False).run()
    assert not at.exception and at.text_input[0].label == "Teacher password"
    assert not at.get("file_uploader") and not has(at, "Create a new exam")


def test_a_wrong_password_is_refused_and_too_many_lock_it(db, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    at = teacher(logged_in=False).run()
    for _ in range(4):
        at.text_input[0].set_value("nope")
        button(at, "Open").click().run()
        assert has(at, "not right") and not at.get("file_uploader")
    at.text_input[0].set_value("nope")
    button(at, "Open").click().run()
    at.text_input[0].set_value(PASSWORD)                                   # even the right one is refused now
    button(at, "Open").click().run()
    assert has(at, "Too many wrong passwords") or has(at, "not right")


def test_the_right_password_opens_the_teacher_area(db):
    at = teacher(logged_in=False).run()
    at.text_input[0].set_value(PASSWORD)
    button(at, "Open").click().run()
    assert not at.exception and at.title[0].value.endswith("Exams")


def test_spaces_around_the_password_do_not_matter_but_a_wrong_one_is_refused(db, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    at = teacher(logged_in=False).run()
    for wrong in (PASSWORD[:-1], PASSWORD + "x", PASSWORD.upper(), ""):                   # 4 tries: a 5th would lock the form
        at.text_input[0].set_value(wrong)
        button(at, "Open").click().run()
        assert has(at, "not right") and not at.get("file_uploader"), repr(wrong)
    at.text_input[0].set_value(f"  {PASSWORD}\n ")                     # pasted with spaces around it
    button(at, "Open").click().run()
    assert not at.exception and at.title[0].value.endswith("Exams")


def test_no_password_in_env_blocks_the_area(db, tmp_path):
    (tmp_path / ".env").write_text("")
    at = teacher(logged_in=False).run()
    assert has(at, "No teacher password is set") and not at.get("file_uploader")


def test_the_teacher_creates_an_exam_from_an_existing_bank_and_gets_the_link(db):
    at = teacher().run()
    assert not at.exception and has(at, "No exams yet")
    at.radio[0].set_value("Use a quiz bank that already exists").run()
    at.text_input[0].set_value("Physics: Electricity")
    at.number_input[0].set_value(12)
    button(at, "Create exam").click().run()
    assert not at.exception and has(at, "created")
    exam = exams.list_exams(connect(db))[0]
    assert exam["max_students"] == 12 and exam["status"] == "ready" and exam["bank_name"] in ("electricity_gold", "electricity_llm")
    assert any(f"/?exam={exam['code']}" in c.value for c in at.code)         # the link to send to students
    assert any(f":{config.STUDENT_PORT}" in c.value for c in at.code)


def test_creating_an_exam_needs_a_title_and_a_valid_number(db):
    at = teacher().run()
    at.radio[0].set_value("Use a quiz bank that already exists").run()
    button(at, "Create exam").click().run()
    assert has(at, "give the exam a title") and exams.list_exams(connect(db)) == []


def test_uploading_a_pdf_that_was_built_before_makes_the_exam_ready_at_once(db):
    at = teacher().run()
    at.text_input[0].set_value("Electricity again")
    at.file_uploader[0].set_value(("notes.pdf", DEMO_PDF.read_bytes(), "application/pdf"))
    at.number_input[0].set_value(20)
    button(at, "Create exam").click().run()
    assert not at.exception and has(at, "already existed")
    exam = exams.list_exams(connect(db))[0]
    assert exam["status"] == "ready" and exam["pdf_name"] == "notes.pdf" and exam["max_students"] == 20


def test_uploading_a_new_pdf_starts_a_build_and_shows_progress(db, monkeypatch):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 550, 800), "Photosynthesis is how plants make food from light. " * 40)
    started = {}
    monkeypatch.setattr(jobs, "ai_config_problem", lambda: None)

    def fake_start(conn, code, data, *, bank_name, max_concepts, command=None):
        import os
        started.update(code=code, bank=bank_name, concepts=max_concepts, size=len(data))
        exams.update_exam(conn, code, bank_name=bank_name, status="building", pid=os.getpid())   # "a live build"
        return os.getpid()

    monkeypatch.setattr(jobs, "start_build", fake_start)
    at = teacher().run()
    at.text_input[0].set_value("Biology")
    at.file_uploader[0].set_value(("bio.pdf", doc.tobytes(), "application/pdf"))
    at.slider[0].set_value(4)
    button(at, "Create exam").click().run()
    assert not at.exception and started["concepts"] == 4 and started["bank"].startswith("exam_")
    exam = exams.list_exams(connect(db))[0]
    assert exam["status"] == "building" and exam["title"] == "Biology"
    assert has(at, "being prepared") and at.progress                       # a progress bar, no student link yet
    assert not any("?exam=" in c.value for c in at.code)


@pytest.mark.parametrize("name, data, message", [
    ("renamed.pdf", b"just some text that was renamed to .pdf" * 20, "does not look like a PDF"),
    ("empty.pdf", b"", "empty"),
])
def test_a_bad_upload_is_explained_and_creates_nothing(db, name, data, message):
    at = teacher().run()
    at.text_input[0].set_value("Bad")
    at.file_uploader[0].set_value((name, data, "application/pdf"))
    button(at, "Create exam").click().run()
    assert has(at, message) and exams.list_exams(connect(db)) == []


def test_creating_with_no_file_asks_for_one(db):
    at = teacher().run()
    at.text_input[0].set_value("No file")
    button(at, "Create exam").click().run()
    assert has(at, "choose a PDF file")


def test_the_teacher_can_close_and_reopen_an_exam(db):
    e = new_exam(db)
    at = teacher().run()
    button(at, "Close exam").click().run()
    assert exams.get_exam(connect(db), e["code"])["status"] == "closed"
    button(at, "Reopen exam").click().run()
    assert exams.get_exam(connect(db), e["code"])["status"] == "ready"


def test_the_teacher_can_delete_an_exam_only_after_confirming(db, bank):
    conn = connect(db)
    e = new_exam(db, title="Throwaway")
    exams.attach(conn, simulate_class(conn, bank, 3, 1), e["code"])
    at = teacher().run()
    assert button(at, "Delete exam").disabled                                  # not until the box is ticked
    at.checkbox[0].check().run()
    button(at, "Delete exam").click().run()
    assert exams.get_exam(connect(db), e["code"]) is None and has(at, "Deleted")
    assert connect(db).execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0


def test_a_slow_build_can_be_stopped_from_the_exams_page(db):
    import os
    e = new_exam(db, title="Slow one", status="building", bank=None)
    exams.update_exam(connect(db), e["code"], pid=os.getpid())               # shown as a live build; stopping must not harm us
    at = teacher().run()
    assert has(at, "Being prepared") and button(at, "Stop building")
    button(at, "Stop building").click().run()
    assert not at.exception and exams.get_exam(connect(db), e["code"])["status"] == "failed"
    assert has(at, "You stopped this build") and button(at, "Try again")


def test_a_failed_build_shows_the_reason_and_a_retry_button(db):
    e = new_exam(db, status="failed", bank=None)
    exams.update_exam(connect(db), e["code"], error="Build stopped: GEMINI_API_KEY is not set")
    at = teacher().run()
    assert has(at, "could not be prepared") and has(at, "GEMINI_API_KEY") and button(at, "Try again")


def test_students_from_an_earlier_trial_are_kept_in_a_demo_exam(db):
    from tutor.models import load_bank
    conn = connect(db)
    sid = service.join(conn, "panda", "2222")
    at = teacher().run()
    assert not at.exception and has(at, "Demo exam (earlier trial)")
    assert exams.student_exam(connect(db), sid) == exams.LEGACY_CODE


def test_the_class_report_shows_scores_for_the_chosen_exam(db, bank):
    conn = connect(db)
    e, other = new_exam(db, title="Mine"), new_exam(db, title="Someone else's")
    exams.attach(conn, simulate_class(conn, bank, 14, 7), e["code"])
    exams.attach(conn, simulate_class(conn, bank, 3, 9), other["code"])
    at = teacher().run()
    at.session_state["exam_code"] = e["code"]
    at.switch_page("teacher/dashboard.py").run()
    assert not at.exception and at.title[0].value.endswith("Class report")
    assert at.selectbox[0].value == e["code"]
    text = " ".join(m.value for m in at.markdown)
    assert "START HERE" in text and "Most common mistake" in text
    assert len(at.get("graphviz_chart")) == 1 and len(at.tabs) == 4
    assert [t.label for t in at.tabs][0] == "Scores" and any(m.label == "Class average" for m in at.metric)
    assert any("14 students shown" in c.value for c in at.caption)         # only this exam's students, not the other's 3
    assert any("simulated" in i.value for i in at.info)


def test_the_dashboard_tells_the_teacher_when_nobody_has_finished_yet(db):
    e = new_exam(db)
    at = teacher().run()
    at.session_state["exam_code"] = e["code"]
    at.switch_page("teacher/dashboard.py").run()
    assert has(at, "No finished students yet") or any("No finished students yet" in w.value for w in at.warning)


def test_the_teacher_can_add_and_remove_test_students(db):
    e = new_exam(db)
    at = teacher().run()
    at.session_state["exam_code"] = e["code"]
    at.switch_page("teacher/dashboard.py").run()
    button(at, "Add simulated students").click().run()
    assert not at.exception and len(at.get("graphviz_chart")) == 1
    assert exams.counts(connect(db), e["code"])["simulated"] == 14
    at.sidebar.checkbox[2].check().run()                                    # the "I understand" box
    button(at, "Remove simulated students").click().run()
    assert exams.counts(connect(db), e["code"])["simulated"] == 0


def test_the_system_page_explains_the_ai_setup(db):
    at = teacher().run()
    at.switch_page("teacher/status.py").run()
    assert not at.exception and has(at, "API keys found") or any("API keys found" in m.value for m in at.markdown)
    assert any("cannot be turned into a quiz" in w.value for w in at.warning)   # no AI keys in this test setup
