"""The web API, tested through HTTP with FastAPI's test client. Everything runs on a throwaway database."""
import sys
import time

import pytest
from fastapi.testclient import TestClient

from api import deps
from api.main import create_app
from api.security import COOKIE, make_session
from api.settings import Settings
from tutor import config, exams, jobs
from tutor.db import connect
from tutor.simulate import simulate_class

PASSWORD = "open-sesame"
SECRET = b"test-secret"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TUTOR_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")                 # no AI keys: the built-in matcher judges
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "data" / "uploads")
    monkeypatch.setattr(config, "BUILD_DIR", tmp_path / "data" / "builds")
    deps.forget_caches()
    return tmp_path


def client(env, mode="all", logged_in=False, **kw):
    settings = Settings(mode=mode, teacher_password=PASSWORD, session_secret=SECRET, web_dist=env / "no-dist", **kw)
    c = TestClient(create_app(settings))
    if logged_in:
        assert c.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    return c


def new_exam(env, seats=30, status="ready", bank="electricity_gold", title="Physics"):
    return exams.create_exam(connect(env / "t.db"), title, seats, bank_name=bank, status=status)


def play(c, token, bank, right=True):
    """Answer a whole exam through the API. Returns the final state."""
    for _ in range(80):
        s = c.get(f"/api/play/{token}").json()
        if s["phase"] == "done":
            return s
        if s["phase"] == "judging":
            s = c.post(f"/api/play/{token}/finish").json()
            continue
        q = bank.question(s["question"]["id"])
        key = q.answer_key if right else next(o.key for o in q.options if o.key != q.answer_key)
        r = c.post(f"/api/play/{token}/answer", json={"question_id": q.id, "choice": key, "reason": "I remember that this is what the notes say about it"})
        assert r.status_code == 200, r.text
    raise AssertionError("the exam did not finish")


# ======================= basics and security =======================

def test_health_and_security_headers(env):
    r = client(env).get("/api/health")
    assert r.status_code == 200 and r.json() == {"ok": True, "mode": "all"}
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"] and r.headers["cache-control"] == "no-store"


def test_the_teacher_routes_need_a_session(env):
    c = client(env)
    for path in ("/api/exams", "/api/system", "/api/exams/ABC123", "/api/exams/ABC123/report"):
        assert c.get(path).status_code == 401, path
    assert c.post("/api/exams", json={"title": "x", "seats": 5, "bank": "electricity_gold"}).status_code == 401
    assert c.delete("/api/exams/ABC123").status_code == 401


def test_login_logout_and_the_cookie(env):
    c = client(env)
    assert c.get("/api/auth/me").json() == {"authenticated": False, "password_set": True, "mode": "all"}
    assert c.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    r = c.post("/api/auth/login", json={"password": f"  {PASSWORD}\n"})            # spaces from copy and paste are fine
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and COOKIE in cookie
    assert c.get("/api/auth/me").json()["authenticated"] is True and c.get("/api/exams").status_code == 200
    c.post("/api/auth/logout")
    assert c.get("/api/exams").status_code == 401


def test_a_forged_or_expired_session_is_refused(env):
    c = client(env)
    c.cookies.set(COOKIE, "v1.99999999999.deadbeef")
    assert c.get("/api/exams").status_code == 401
    c.cookies.set(COOKIE, make_session(b"another-secret", 1))                      # signed with the wrong key
    assert c.get("/api/exams").status_code == 401
    c.cookies.set(COOKIE, make_session(SECRET, -1))                                # properly signed but expired
    assert c.get("/api/exams").status_code == 401
    c.cookies.set(COOKIE, make_session(SECRET, 1))
    assert c.get("/api/exams").status_code == 200


def test_too_many_wrong_passwords_are_throttled(env):
    c = client(env)
    codes = [c.post("/api/auth/login", json={"password": "nope"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
    assert c.post("/api/auth/login", json={"password": PASSWORD}).status_code == 429       # even the right one waits


def test_no_password_configured_blocks_login(env):
    c = TestClient(create_app(Settings(mode="all", teacher_password=None, session_secret=SECRET, web_dist=env / "x")))
    r = c.post("/api/auth/login", json={"password": "anything"})
    assert r.status_code == 503 and "TEACHER_PASSWORD" in r.json()["detail"]


def test_a_cross_site_post_is_blocked_but_the_same_site_works(env):
    c = client(env)
    r = c.post("/api/auth/login", json={"password": PASSWORD}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert c.post("/api/auth/login", json={"password": PASSWORD}, headers={"Origin": "http://testserver"}).status_code == 200
    d = client(env, allowed_origins=("https://school.example",))
    assert d.post("/api/auth/login", json={"password": PASSWORD}, headers={"Origin": "https://school.example"}).status_code == 200


def test_validation_errors_are_readable(env):
    e = new_exam(env)
    c = client(env)
    r = c.post(f"/api/exams/{e['code']}/join", json={"nickname": ""})
    assert r.status_code == 422 and "nickname" in r.json()["detail"] and isinstance(r.json()["detail"], str)
    assert c.post(f"/api/exams/{e['code']}/join", json={"nickname": "x" * 31}).status_code == 422


# ======================= students =======================

def test_a_student_takes_the_whole_exam_and_gets_a_score(env, bank):
    e = new_exam(env)
    c = client(env)
    pub = c.get(f"/api/exams/{e['code']}/public").json()
    assert pub == {"code": e["code"], "title": "Physics", "status": "ready", "can_join": True, "message": None}
    r = c.post(f"/api/exams/{e['code']}/join", json={"nickname": "Ana"})
    assert r.status_code == 200
    token, state = r.json()["token"], r.json()["state"]
    assert len(token) >= 20 and state["phase"] == "question" and state["total"] == 10 and state["nickname"] == "Ana"
    final = play(c, token, bank)
    assert final["phase"] == "done"
    res = c.get(f"/api/play/{token}/results").json()
    assert res["score"] == {"credited": 20, "asked": 20, "percent": 100, "follow_ups": 0}
    assert res["nickname"] == "Ana" and all(x["state"] == "understood" for x in res["concepts"]) and res["review"] == []


def test_a_struggling_student_gets_follow_up_questions_and_a_low_score(env, bank):
    e = new_exam(env)
    c = client(env)
    token = c.post(f"/api/exams/{e['code']}/join", json={"nickname": "Ben"}).json()["token"]
    play(c, token, bank, right=False)
    res = c.get(f"/api/play/{token}/results").json()
    assert res["score"]["percent"] == 0 and res["score"]["follow_ups"] == 10 and len(res["review"]) == 30


def test_the_student_never_receives_answer_keys_or_feedback(env, bank):
    e = new_exam(env)
    c = client(env)
    r = c.post(f"/api/exams/{e['code']}/join", json={"nickname": "Ana"}).json()
    q = r["state"]["question"]
    assert set(q) == {"id", "stem", "round", "index", "total", "options"}
    assert all(set(o) == {"label", "key", "text"} for o in q["options"])
    a = c.post(f"/api/play/{r['token']}/answer", json={"question_id": q["id"], "choice": q["options"][0]["key"],
                                                       "reason": "because that is what I believe it is"})
    assert "correct" not in str(a.json()).lower() and "answer_key" not in a.text and "tag" not in a.text
    assert c.get(f"/api/play/{r['token']}/results").status_code == 409                     # no results before the end


def test_answer_input_is_checked(env):
    e = new_exam(env)
    c = client(env)
    r = c.post(f"/api/exams/{e['code']}/join", json={"nickname": "Ana"}).json()
    q, tok = r["state"]["question"], r["token"]
    base = {"question_id": q["id"], "choice": q["options"][0]["key"]}
    assert c.post(f"/api/play/{tok}/answer", json={**base, "reason": "too short"}).status_code == 400      # needs 6 words
    assert "at least 6 words" in c.post(f"/api/play/{tok}/answer", json={**base, "reason": "too short"}).json()["detail"]
    assert c.post(f"/api/play/{tok}/answer", json={**base, "choice": "Z", "reason": "a long enough reason here"}).status_code == 422
    assert c.post(f"/api/play/{tok}/answer", json={**base, "reason": "x " * 800}).status_code == 422       # over the length limit
    assert c.post(f"/api/play/{tok}/answer", json={**base, "reason": "", "is_guess": True}).status_code == 200


def test_tokens_are_private(env):
    e, f = new_exam(env), new_exam(env, title="Other")
    c = client(env)
    t1 = c.post(f"/api/exams/{e['code']}/join", json={"nickname": "Ana"}).json()["token"]
    assert c.get(f"/api/play/{t1}").status_code == 200
    for bad in ("nope", "A" * 22, "x" * 200, t1[:-1], t1.upper()):
        assert c.get(f"/api/play/{bad}").status_code == 404, bad
    assert c.get(f"/api/exams/ZZZZZZ/public").status_code == 404 and c.post("/api/exams/ZZZZZZ/join", json={"nickname": "a"}).status_code == 404


def test_the_seat_limit_and_closed_exams(env):
    e = new_exam(env, seats=1)
    c = client(env)
    assert c.post(f"/api/exams/{e['code']}/join", json={"nickname": "a"}).status_code == 200
    r = c.post(f"/api/exams/{e['code']}/join", json={"nickname": "b"})
    assert r.status_code == 409 and "full" in r.json()["detail"]
    assert c.get(f"/api/exams/{e['code']}/public").json()["can_join"] is False
    closed = new_exam(env, status="closed")
    assert "closed" in c.post(f"/api/exams/{closed['code']}/join", json={"nickname": "a"}).json()["detail"]
    dup = new_exam(env)
    c.post(f"/api/exams/{dup['code']}/join", json={"nickname": "Ana"})
    assert "nickname" in c.post(f"/api/exams/{dup['code']}/join", json={"nickname": "ana"}).json()["detail"]


def test_joining_is_rate_limited(env):
    e = new_exam(env, seats=100)
    c = client(env)
    codes = [c.post(f"/api/exams/{e['code']}/join", json={"nickname": f"s{i}"}).status_code for i in range(23)]
    assert codes[:20] == [200] * 20 and set(codes[20:]) == {429}


# ======================= student-only instances =======================

def test_a_student_only_instance_has_no_teacher_routes_at_all(env, bank):
    e = new_exam(env)
    c = client(env, mode="student")
    assert c.get("/api/health").json()["mode"] == "student"
    for method, path in (("get", "/api/exams"), ("get", "/api/system"), ("post", "/api/auth/login"), ("get", f"/api/exams/{e['code']}/report"),
                         ("delete", f"/api/exams/{e['code']}"), ("get", "/api/auth/me")):
        assert getattr(c, method)(path).status_code in (404, 405), path
    token = c.post(f"/api/exams/{e['code']}/join", json={"nickname": "Ana"}).json()["token"]        # students still work
    assert play(c, token, bank)["phase"] == "done"


# ======================= teacher =======================

def _teacher_at(env, base_url, **kw):
    c = TestClient(create_app(Settings(mode="teacher", teacher_password=PASSWORD, session_secret=SECRET, web_dist=env / "no-dist", **kw)), base_url=base_url)
    assert c.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    return c


def test_a_private_teacher_instance_shows_links_that_point_at_the_student_port(env, monkeypatch):
    monkeypatch.setattr(exams, "lan_ip", lambda: "192.168.1.20")
    c = _teacher_at(env, "http://localhost:8081", student_port=8080)
    assert c.get("/api/system").json()["link_base"] == "http://192.168.1.20:8080"            # this computer's address, the student port
    assert _teacher_at(env, "http://localhost:8081").get("/api/system").json()["link_base"] == "http://192.168.1.20:8081"   # no student port: its own
    assert _teacher_at(env, "http://school-laptop:8081", student_port=8080).get("/api/system").json()["link_base"] == "http://school-laptop:8080"
    assert _teacher_at(env, "http://localhost:8081", student_port=8080, public_url="https://exams.example.org").get("/api/system").json()["link_base"] == "https://exams.example.org"


def test_the_student_port_setting_is_validated(monkeypatch, tmp_path):
    from api.settings import load_settings

    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("STUDENT_PORT", "8080")
    assert load_settings(session_secret=SECRET).student_port == 8080
    for bad in ("eighty", "0", "70000", "-1"):
        monkeypatch.setenv("STUDENT_PORT", bad)
        with pytest.raises(ValueError, match="STUDENT_PORT"):
            load_settings(session_secret=SECRET)
    monkeypatch.delenv("STUDENT_PORT")
    assert load_settings(session_secret=SECRET).student_port is None


def test_the_teacher_creates_an_exam_from_a_bank_and_sees_it_listed(env):
    c = client(env, logged_in=True)
    sys_ = c.get("/api/system").json()
    assert sys_["mode"] == "all" and {b["name"] for b in sys_["banks"]} >= {"electricity_gold"} and sys_["link_base"].startswith("http")
    assert set(sys_["keys"]) == {"gemini", "groq", "openrouter"}
    r = c.post("/api/exams", json={"title": "Electricity", "seats": 12, "bank": "electricity_gold"})
    assert r.status_code == 201 and r.json()["max_students"] == 12 and r.json()["status"] == "ready"
    assert "pid" not in r.json() and "log_path" not in r.json()                             # internals stay private
    assert [e["title"] for e in c.get("/api/exams").json()] == ["Electricity"]
    assert c.post("/api/exams", json={"title": "x", "seats": 5, "bank": "../../etc"}).status_code == 422
    assert c.post("/api/exams", json={"title": "x", "seats": 0, "bank": "electricity_gold"}).status_code == 422


def test_the_class_report_has_scores_questions_and_the_root_gap_cards(env, bank):
    e = new_exam(env)
    conn = connect(env / "t.db")
    exams.attach(conn, simulate_class(conn, bank, 14, 7), e["code"])
    c = client(env, logged_in=True)
    r = c.get(f"/api/exams/{e['code']}/report").json()
    assert r["report"]["students"]["counted"] == 14 and r["report"]["students"]["simulated"] == 14
    assert r["report"]["cards"] and any(card["start_here"] for card in r["report"]["cards"])
    assert r["scores"]["average"] is not None and len(r["scores"]["students"]) == 14
    assert len(r["questions"]) == 30 and any(o["label"] == "RIGHT ANSWER" for q in r["questions"] for o in q["options"])
    assert c.get(f"/api/exams/{e['code']}/report?include=real").json()["report"]["students"]["counted"] == 0
    assert c.get(f"/api/exams/{e['code']}/report?include=bogus").status_code == 422
    csv_ = c.get(f"/api/exams/{e['code']}/export.csv")
    assert csv_.headers["content-type"].startswith("text/csv") and csv_.text.splitlines()[0].startswith("nickname") and "concept_id" in csv_.text


def test_test_students_can_be_added_and_removed_per_exam(env):
    a, b = new_exam(env, title="A"), new_exam(env, title="B")
    c = client(env, logged_in=True)
    assert c.post(f"/api/exams/{a['code']}/simulate", json={"count": 5, "seed": 3}).json() == {"added": 5}
    assert c.post(f"/api/exams/{b['code']}/simulate", json={"count": 4, "seed": 3}).json() == {"added": 4}
    assert c.delete(f"/api/exams/{a['code']}/simulated").json() == {"removed": 5}
    assert exams.counts(connect(env / "t.db"), b["code"])["simulated"] == 4                   # the other exam is untouched
    assert c.post(f"/api/exams/{a['code']}/simulate", json={"count": 999, "seed": 1}).status_code == 422


def test_closing_reopening_and_deleting(env, bank):
    e = new_exam(env)
    c = client(env, logged_in=True)
    token = client(env).post(f"/api/exams/{e['code']}/join", json={"nickname": "Ana"}).json()["token"]
    assert c.post(f"/api/exams/{e['code']}/close").json()["status"] == "closed"
    assert client(env).post(f"/api/exams/{e['code']}/join", json={"nickname": "Ben"}).status_code == 409
    assert c.post(f"/api/exams/{e['code']}/reopen").json()["status"] == "ready"
    assert c.post(f"/api/exams/{e['code']}/explode").status_code == 404
    assert c.delete(f"/api/exams/{e['code']}").json() == {"deleted": e["code"], "students_removed": 1}
    assert c.get(f"/api/exams/{e['code']}").status_code == 404 and c.get(f"/api/play/{token}").status_code == 404


PDF_DEMO = config.ROOT / "demo" / "Electricity_Basics.pdf"


def test_uploading_a_pdf_that_was_built_before_is_ready_at_once(env):
    c = client(env, logged_in=True)
    r = c.post("/api/exams/upload", data={"title": "Again", "seats": "20", "max_concepts": "5"},
               files={"file": ("notes.pdf", PDF_DEMO.read_bytes(), "application/pdf")})
    assert r.status_code == 201 and r.json()["reused"] is True and r.json()["status"] == "ready" and r.json()["max_students"] == 20


@pytest.mark.parametrize("name, data, message", [("a.pdf", b"", "empty"), ("a.pdf", b"not a pdf at all " * 30, "does not look like a PDF")])
def test_a_bad_upload_is_explained_and_creates_nothing(env, name, data, message):
    c = client(env, logged_in=True)
    r = c.post("/api/exams/upload", data={"title": "Bad", "seats": "5"}, files={"file": (name, data, "application/pdf")})
    assert r.status_code == 422 and message in r.json()["detail"] and c.get("/api/exams").json() == []


def test_a_new_pdf_builds_in_the_background_and_can_be_stopped_and_retried(env, monkeypatch):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page().insert_textbox(pymupdf.Rect(40, 40, 550, 800), "Photosynthesis is how plants make food from light. " * 40)
    monkeypatch.setattr(jobs, "ai_config_problem", lambda: None)
    sleeper = [sys.executable, "-c", "import time; print('[0] extracted 1 pages', flush=True); time.sleep(60)"]
    real_start = jobs.start_build
    monkeypatch.setattr(jobs, "start_build", lambda *a, **k: real_start(*a, **{**k, "command": sleeper}))
    c = client(env, logged_in=True)
    r = c.post("/api/exams/upload", data={"title": "Biology", "seats": "10", "max_concepts": "4"},
               files={"file": ("bio.pdf", doc.tobytes(), "application/pdf")})
    assert r.status_code == 201 and r.json()["status"] == "building" and r.json()["max_concepts"] == 4
    code = r.json()["code"]
    end = time.time() + 10
    while time.time() < end and "Reading the PDF" not in c.get(f"/api/exams/{code}").json()["message"]:
        time.sleep(0.1)
    assert 0 < c.get(f"/api/exams/{code}").json()["progress"] < 1
    assert client(env).get(f"/api/exams/{code}/public").json()["can_join"] is False             # students wait
    assert c.get(f"/api/exams/{code}/report").status_code == 409
    second = c.post("/api/exams/upload", data={"title": "Chem", "seats": "10"}, files={"file": ("c.pdf", doc.tobytes(), "application/pdf")})
    assert second.status_code == 422 and "still being built" in second.json()["detail"]         # one build at a time
    stopped = c.post(f"/api/exams/{code}/stop").json()
    assert stopped["status"] == "failed" and "You stopped this build" in stopped["error"]
    assert c.delete(f"/api/exams/{code}").status_code == 200


# ======================= serving the front end =======================

def test_the_front_end_is_served_with_the_right_caching_and_cannot_read_other_files(env):
    dist = env / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>app</title>")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)")
    (dist / "robots.txt").write_text("User-agent: *")
    (env / "secret.txt").write_text("top secret")
    c = TestClient(create_app(Settings(mode="all", teacher_password=PASSWORD, session_secret=SECRET, web_dist=dist)))
    assert "<title>app</title>" in c.get("/").text
    page = c.get("/teacher/exams/ABC123")                                                       # a page of the app: client-side routing
    assert "<title>app</title>" in page.text and page.headers["cache-control"] == "no-cache"
    asset = c.get("/assets/app-abc123.js")
    assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
    assert c.get("/robots.txt").text == "User-agent: *"
    for sneaky in ("/..%2fsecret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        assert "top secret" not in c.get(sneaky).text, sneaky
    assert c.get("/api/does-not-exist").status_code == 404
    assert c.get("/", headers={"Accept-Encoding": "gzip"}).status_code == 200


def test_without_a_built_front_end_the_api_says_how_to_build_it(env):
    assert "npm run build" in client(env).get("/").json()["message"]
