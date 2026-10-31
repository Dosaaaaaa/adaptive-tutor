import shutil
import sys
import time

import pymupdf
import pytest

from tutor import config, exams, jobs
from tutor.extract import pdf_sha256

DEMO = config.ROOT / "demo" / "Electricity_Basics.pdf"


def pdf_with(text="", pages=1, **save):
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(50, 50, 500, 700), text)
    return doc.tobytes(**save)


def test_the_demo_pdf_is_accepted():
    info = jobs.validate_pdf(DEMO.read_bytes())
    assert info["pages"] == 5 and info["sha256"] == pdf_sha256(DEMO)


@pytest.mark.parametrize("data, message", [
    (b"", "empty"),
    (b"This is not a pdf at all, just a text file." * 10, "does not look like a PDF"),
    (b"%PDF-1.4 garbage that cannot be read as a document", "could not be read"),
    (pdf_with(), "No readable text"),                                                    # a blank page: like a scan
    (pdf_with("secret " * 100, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="a", owner_pw="b"), "password"),
])
def test_bad_files_get_a_clear_message(data, message):
    with pytest.raises(jobs.UploadError, match=message):
        jobs.validate_pdf(data)


def test_size_and_page_limits(monkeypatch):
    text = "Electric current is the flow of charge. " * 30
    monkeypatch.setattr(config, "MAX_PDF_PAGES", 2)
    with pytest.raises(jobs.UploadError, match="3 pages"):
        jobs.validate_pdf(pdf_with(text, pages=3))
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    with pytest.raises(jobs.UploadError, match="larger than"):
        jobs.validate_pdf(pdf_with(text))


def test_a_bank_built_from_the_same_file_is_reused():
    sha = pdf_sha256(DEMO)
    assert jobs.reusable_bank(sha, 5) in ("electricity_llm", "electricity_gold")
    assert jobs.reusable_bank(sha, 7) is None                                             # other settings: build again
    assert jobs.reusable_bank("0" * 64, 5) is None


def test_the_ai_built_bank_is_preferred_for_reuse(tmp_path, monkeypatch):
    for name, ai in (("hand_made", False), ("ai_made", True)):
        shutil.copytree(config.BANK_DIR / "electricity_gold", tmp_path / name)
        m = (tmp_path / name / "manifest.json")
        import json
        d = json.loads(m.read_text())
        d["ai_checks"] = ai
        m.write_text(json.dumps(d))
    monkeypatch.setattr(config, "BANK_DIR", tmp_path)
    assert jobs.reusable_bank(pdf_sha256(DEMO), 5) == "ai_made"


def test_progress_is_read_from_the_build_log():
    log = lambda *lines: "\n".join(lines)  # noqa: E731
    assert jobs.parse_progress("")[0] < 0.05
    assert jobs.parse_progress(log("[0] extracted 5 pages"))[0] == 0.05
    f, msg = jobs.parse_progress(log("[0] extracted 5 pages", "[1] 5 concepts, 5 prerequisite edges", "[2-3] C1 a: 3 misconceptions, 6 questions"))
    assert 0.2 < f < 0.4 and "concept 2 of 5" in msg
    f, msg = jobs.parse_progress(log("[1] 5 concepts, 5 prerequisite edges", *["[2-3] C: x"] * 5))
    assert f == 0.65 and "second AI" in msg
    assert jobs.parse_progress(log("[4] 28 questions passed the AI checks"))[0] == 0.97
    assert jobs.parse_progress(log("wrote /x/bank/y"))[0] == 1.0


# ---- the real background process, with a stand-in for the AI build ----

FAKE_BUILD = """
import shutil, sys, time
print("[0] extracted 5 pages", flush=True); time.sleep(0.2)
print("[1] 5 concepts, 5 prerequisite edges", flush=True); time.sleep(0.2)
shutil.copytree({src!r}, {dst!r})
print("wrote " + {dst!r}, flush=True)
"""


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BANK_DIR", tmp_path / "bank")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "BUILD_DIR", tmp_path / "builds")
    (tmp_path / "bank").mkdir()
    return tmp_path


def wait_for(conn, code, want, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        e = jobs.refresh(conn, exams.get_exam(conn, code))
        if e["status"] != "building":
            return e
        time.sleep(0.1)
    raise AssertionError("the build did not finish")


def test_an_upload_builds_in_the_background_and_the_exam_becomes_ready(conn, sandbox):
    e = exams.create_exam(conn, "New topic", 20, pdf_name="x.pdf", status="building")
    dst = str(sandbox / "bank" / "exam_x")
    cmd = [sys.executable, "-c", FAKE_BUILD.format(src=str(config.ROOT / "bank" / "electricity_gold"), dst=dst)]
    pid = jobs.start_build(conn, e["code"], b"%PDF-fake", bank_name="exam_x", max_concepts=5, command=cmd)
    assert pid > 0 and (sandbox / "uploads" / f"{e['code']}.pdf").read_bytes() == b"%PDF-fake"
    assert oct((sandbox / "uploads" / f"{e['code']}.pdf").stat().st_mode & 0o777) == "0o600"   # private
    assert jobs.building_now(conn)["code"] == e["code"]                                  # only one build at a time
    done = wait_for(conn, e["code"], "ready")
    assert done["status"] == "ready" and done["progress"] == 1.0
    assert exams.get_exam(conn, e["code"])["status"] == "ready"
    assert jobs.building_now(conn) is None
    exams.join_exam(conn, e["code"], "Ana")                                              # students can now join


def test_a_build_that_crashes_marks_the_exam_failed_with_the_reason(conn, sandbox):
    e = exams.create_exam(conn, "Bad", 20, status="building")
    cmd = [sys.executable, "-c", "print('[0] extracted 5 pages'); print('Build stopped: GEMINI_API_KEY is not set in .env'); raise SystemExit(1)"]
    jobs.start_build(conn, e["code"], b"%PDF-fake", bank_name="exam_bad", max_concepts=5, command=cmd)
    done = wait_for(conn, e["code"], "failed")
    assert done["status"] == "failed" and "GEMINI_API_KEY" in done["error"]
    assert jobs.building_now(conn) is None


def test_a_build_that_was_killed_says_so_and_how_to_continue(conn, sandbox):
    e = exams.create_exam(conn, "Killed", 20, status="building")
    cmd = [sys.executable, "-c", "import os, signal; print('[0] extracted 1 pages', flush=True); os.kill(os.getpid(), signal.SIGKILL)"]
    jobs.start_build(conn, e["code"], b"%PDF-fake", bank_name="exam_k", max_concepts=5, command=cmd)
    done = wait_for(conn, e["code"], "failed")
    assert done["status"] == "failed" and "Press Try again" in done["error"] and "extracted" not in done["error"]


def test_the_ai_settings_check_names_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    assert "GEN_MODEL" in jobs.ai_config_problem()
    (tmp_path / ".env").write_text("GEN_MODEL=gemini-x\nVERIFY_MODEL=openai/gpt-oss-120b\nGEMINI_API_KEY=k1\nGROQ_API_KEY=k2\n")
    assert jobs.ai_config_problem() is None
    (tmp_path / ".env").write_text("GEN_MODEL=gemini-x\nVERIFY_MODEL=gemini-y\nGEMINI_API_KEY=k1\nVERIFY_PROVIDER=gemini\n")
    assert "both 'google'" in jobs.ai_config_problem()


# ---- the upload button, end to end (everything except the AI itself) ----

def test_uploading_the_same_pdf_again_is_ready_at_once_with_no_build(conn, sandbox, monkeypatch):
    for name in ("electricity_gold",):                                   # a bank for this exact file already exists
        shutil.copytree(config.ROOT / "bank" / name, sandbox / "bank" / name)
    monkeypatch.setattr(jobs, "start_build", lambda *a, **k: pytest.fail("must not build again"))
    exam = jobs.create_exam_from_pdf(conn, "Electricity", DEMO.read_bytes(), "notes.pdf", 25, 5)
    assert exam["reused"] is True and exam["status"] == "ready" and exam["bank_name"] == "electricity_gold"
    assert exam["max_students"] == 25
    exams.join_exam(conn, exam["code"], "Ana")


def test_a_new_pdf_starts_a_build_and_a_second_one_has_to_wait(conn, sandbox, monkeypatch):
    monkeypatch.setattr(jobs, "ai_config_problem", lambda: None)
    new_pdf = pdf_with("Photosynthesis is how plants make food from light. " * 40, pages=2)
    sleeper = [sys.executable, "-c", "import time; print('[0] extracted 2 pages', flush=True); time.sleep(30)"]
    first = jobs.create_exam_from_pdf(conn, "Biology", new_pdf, "bio.pdf", 10, 4, command=sleeper)
    try:
        assert first["reused"] is False and first["status"] == "building" and first["max_concepts"] == 4
        assert (sandbox / "uploads" / f"{first['code']}.pdf").exists()
        with pytest.raises(jobs.UploadError, match="still being built"):
            jobs.create_exam_from_pdf(conn, "Chemistry", pdf_with("Atoms bond to make molecules. " * 40), "c.pdf", 10, 4, command=sleeper)
        end = time.time() + 10
        while time.time() < end and not jobs.refresh(conn, first)["message"].startswith("Reading the PDF"):
            time.sleep(0.1)                                              # the child needs a moment to print its first line
        assert jobs.refresh(conn, first)["message"].startswith("Reading the PDF")
    finally:
        import os, signal
        os.kill(first["pid"] or exams.get_exam(conn, first["code"])["pid"], signal.SIGTERM)


def test_building_needs_working_ai_settings_and_says_what_is_missing(conn, sandbox, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "no.env")
    with pytest.raises(jobs.UploadError, match="cannot be built yet.*GEN_MODEL"):
        jobs.create_exam_from_pdf(conn, "x", pdf_with("Some readable text about a topic. " * 30), "x.pdf", 10, 4)
    assert exams.list_exams(conn) == []                                  # nothing half-created


def test_a_bad_file_creates_no_exam(conn, sandbox):
    with pytest.raises(jobs.UploadError, match="does not look like a PDF"):
        jobs.create_exam_from_pdf(conn, "x", b"not a pdf" * 20, "x.pdf", 10, 4)
    assert exams.list_exams(conn) == []


def test_a_failed_build_can_be_retried_from_the_saved_pdf(conn, sandbox):
    e = exams.create_exam(conn, "Retry", 10, status="building")
    jobs.start_build(conn, e["code"], b"%PDF-fake", bank_name="exam_r", max_concepts=5,
                     command=[sys.executable, "-c", "raise SystemExit('Build stopped: quota')"])
    assert wait_for(conn, e["code"], "failed")["status"] == "failed"
    dst = str(sandbox / "bank" / "exam_r")
    jobs.retry_build(conn, exams.get_exam(conn, e["code"]),
                     command=[sys.executable, "-c", FAKE_BUILD.format(src=str(config.ROOT / "bank" / "electricity_gold"), dst=dst)])
    assert wait_for(conn, e["code"], "ready")["status"] == "ready"
    missing = exams.create_exam(conn, "Gone", 10, status="failed")
    with pytest.raises(jobs.UploadError, match="no longer on this computer"):
        jobs.retry_build(conn, missing)


# ---- stopping a build ----

SLEEPER = [sys.executable, "-c", "import time; print('[0] extracted 5 pages', flush=True); time.sleep(60)"]


def test_a_build_can_be_stopped_and_the_exam_is_free_for_another(conn, sandbox):
    e = exams.create_exam(conn, "Slow", 20, status="building")
    pid = jobs.start_build(conn, e["code"], b"%PDF-fake", bank_name="exam_s", max_concepts=5, command=SLEEPER)
    assert jobs.building_now(conn)["code"] == e["code"]
    jobs.cancel_build(conn, exams.get_exam(conn, e["code"]))
    end = time.time() + 5
    while time.time() < end and jobs._alive(pid):
        time.sleep(0.05)
    assert not jobs._alive(pid)                                                         # the process is really gone
    row = exams.get_exam(conn, e["code"])
    assert row["status"] == "failed" and "You stopped this build" in row["error"]
    assert jobs.building_now(conn) is None                                              # nothing blocks a new upload any more


def test_a_stopped_build_can_be_resumed_with_try_again(conn, sandbox):
    e = exams.create_exam(conn, "Resume", 20, status="building")
    jobs.start_build(conn, e["code"], b"%PDF-fake", bank_name="exam_r2", max_concepts=5, command=SLEEPER)
    jobs.cancel_build(conn, exams.get_exam(conn, e["code"]))
    dst = str(sandbox / "bank" / "exam_r2")
    jobs.retry_build(conn, exams.get_exam(conn, e["code"]),
                     command=[sys.executable, "-c", FAKE_BUILD.format(src=str(config.ROOT / "bank" / "electricity_gold"), dst=dst)])
    assert wait_for(conn, e["code"], "ready")["status"] == "ready"


def test_stopping_never_signals_a_process_that_is_not_our_build(conn, sandbox):
    """The stored pid can be reused by an unrelated process. Here it is pointing at the test runner itself."""
    import os
    e = exams.create_exam(conn, "Foreign pid", 20, status="building")
    exams.update_exam(conn, e["code"], pid=os.getpid())                                 # no marker: it cannot be proven ours
    jobs.cancel_build(conn, exams.get_exam(conn, e["code"]))                            # would raise or kill us if unsafe
    assert exams.get_exam(conn, e["code"])["status"] == "failed" and jobs._alive(os.getpid())


def test_a_reused_pid_is_not_mistaken_for_the_build(conn, sandbox):
    e = exams.create_exam(conn, "Reuse", 20, status="building")
    jobs.start_build(conn, e["code"], b"%PDF-fake", bank_name="exam_u", max_concepts=5, command=SLEEPER)
    exam = exams.get_exam(conn, e["code"])
    assert jobs._is_the_build(exam)
    (sandbox / "builds" / f"{e['code']}.proc").write_text("1")                          # as if another process now owns this pid
    assert not jobs._is_the_build(exam) and not jobs._safe_to_kill(exam)
    jobs.cancel_build(conn, exam)                                                       # marks it failed without killing anything
    import os, signal
    os.killpg(exam["pid"], signal.SIGTERM)                                              # clean up our own sleeper


def test_only_a_building_exam_can_be_stopped(conn):
    e = exams.create_exam(conn, "Done", 5)
    with pytest.raises(jobs.UploadError, match="not being built"):
        jobs.cancel_build(conn, e)
