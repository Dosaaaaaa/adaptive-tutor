"""Teacher routes: sign in, create exams (upload a PDF), read the class report. Every route here needs the teacher's session."""
from __future__ import annotations

import csv
import hmac
import io
import sqlite3

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile

from tutor import config, exams, jobs, llm, scoring, stats
from tutor.llm import PROVIDERS
from tutor.simulate import simulate_class

from ..deps import bank_for, db, require_teacher
from ..presenters import exam_out, list_banks
from ..schemas import ExamIn, LoginIn, SimulateIn
from ..security import COOKIE, limit, make_session, valid_session

auth = APIRouter(prefix="/auth")
router = APIRouter(dependencies=[Depends(require_teacher)])


# ---- sign in ----

@auth.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    settings = request.app.state.settings
    if not settings.teacher_password:
        raise HTTPException(503, "No teacher password is set. Add TEACHER_PASSWORD to the .env file and restart.")
    limit(request, "login", 5, 60)
    if not hmac.compare_digest(body.password.strip().encode(), settings.teacher_password.encode()):
        raise HTTPException(401, "That password is not right.")
    response.set_cookie(COOKIE, make_session(settings.session_secret, settings.session_hours), httponly=True,
                        samesite="lax", secure=settings.cookie_secure, max_age=settings.session_hours * 3600, path="/")
    return {"authenticated": True}


@auth.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE, path="/")
    return {"authenticated": False}


@auth.get("/me")
def me(request: Request) -> dict:
    s = request.app.state.settings
    return {"authenticated": valid_session(s.session_secret, request.cookies.get(COOKIE)),
            "password_set": bool(s.teacher_password), "mode": s.mode}


# ---- helpers ----

def _exam_or_404(conn: sqlite3.Connection, code: str) -> dict:
    exam = exams.get_exam(conn, code)
    if exam is None:
        raise HTTPException(404, "That exam does not exist.")
    return exam


def _link_base(request: Request) -> str:
    s = request.app.state.settings
    if s.public_url:
        return s.public_url
    host, port = request.url.hostname, request.url.port
    port = s.student_port or port                                    # the student-only instance may listen on another port
    if host in ("localhost", "127.0.0.1", "::1"):                    # students cannot use "localhost": show this computer's address
        return f"{request.url.scheme}://{exams.lan_ip()}" + (f":{port}" if port else "")
    if s.student_port:
        return f"{request.url.scheme}://{host}:{port}"
    return str(request.base_url).rstrip("/")


# ---- system ----

@router.get("/system")
def system(request: Request, conn: sqlite3.Connection = Depends(db)) -> dict:
    problem = jobs.ai_config_problem()
    return {"mode": request.app.state.settings.mode, "link_base": _link_base(request),
            "keys": {p.name: bool(config.api_key(p.key_env)) for p in PROVIDERS.values()},
            "can_build": problem is None, "ai_problem": problem, "banks": list_banks(),
            "counts": stats.table_counts(conn), "max_upload_mb": config.MAX_UPLOAD_MB, "max_pages": config.MAX_PDF_PAGES,
            "default_concepts": config.MAX_CONCEPTS, "student_port_hint": config.STUDENT_PORT}


# ---- exams ----

@router.get("/exams")
def list_exams(conn: sqlite3.Connection = Depends(db)) -> list[dict]:
    return [exam_out(conn, e) for e in exams.list_exams(conn)]


@router.post("/exams", status_code=201)
def create_exam(body: ExamIn, conn: sqlite3.Connection = Depends(db)) -> dict:
    if body.bank not in {b["name"] for b in list_banks()}:
        raise HTTPException(422, "That quiz bank does not exist.")
    try:
        return exam_out(conn, exams.create_exam(conn, body.title, body.seats, bank_name=body.bank))
    except exams.ExamError as exc:
        raise HTTPException(422, str(exc))


@router.post("/exams/upload", status_code=201)
def upload(request: Request, title: str = Form(..., max_length=120), seats: int = Form(30, ge=1, le=1000),
           max_concepts: int = Form(config.MAX_CONCEPTS, ge=2, le=15), file: UploadFile = File(...),
           conn: sqlite3.Connection = Depends(db)) -> dict:
    limit(request, "upload", 10, 3600)
    data = file.file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    try:
        exam = jobs.create_exam_from_pdf(conn, title, data, (file.filename or "notes.pdf")[:120], seats, max_concepts)
    except (jobs.UploadError, exams.ExamError) as exc:
        raise HTTPException(422, str(exc))
    return {**exam_out(conn, exam), "reused": exam.get("reused", False)}


@router.get("/exams/{code}")
def get_exam(code: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    return exam_out(conn, _exam_or_404(conn, code))


def _exam_action(code: str, conn: sqlite3.Connection, run) -> dict:
    exam = _exam_or_404(conn, code)
    try:
        run(conn, exam)
    except (jobs.UploadError, exams.ExamError) as exc:
        raise HTTPException(409, str(exc))
    return exam_out(conn, exams.get_exam(conn, exam["code"]))


@router.post("/exams/{code}/close")
def close_exam(code: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    """Stops new students joining. Students already taking the test can finish."""
    return _exam_action(code, conn, lambda c, e: exams.close_exam(c, e["code"]))


@router.post("/exams/{code}/reopen")
def reopen_exam(code: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    return _exam_action(code, conn, lambda c, e: exams.reopen_exam(c, e["code"]))


@router.post("/exams/{code}/stop")
def stop_build(code: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    """Stop a quiz that is being built. Retry resumes it: finished steps are remembered."""
    return _exam_action(code, conn, jobs.cancel_build)


@router.post("/exams/{code}/retry")
def retry_build(code: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    return _exam_action(code, conn, jobs.retry_build)


@router.delete("/exams/{code}")
def delete_exam(code: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    exam = _exam_or_404(conn, code)
    try:
        removed = exams.delete_exam(conn, exam["code"])
    except exams.ExamError as exc:
        raise HTTPException(409, str(exc))
    jobs.forget_files(exam["code"])
    return {"deleted": exam["code"], "students_removed": removed}


# ---- the class report ----

@router.get("/exams/{code}/report")
def report(code: str, include: str = "all", only_done: bool = True, conn: sqlite3.Connection = Depends(db)) -> dict:
    if include not in ("all", "real", "simulated"):
        raise HTTPException(422, "include must be all, real or simulated.")
    exam = _exam_or_404(conn, code)
    if exam["status"] not in ("ready", "closed"):
        raise HTTPException(409, "The class report is available once the exam is open.")
    bank = bank_for(exam["bank_name"])
    questions = stats.question_stats(conn, bank, include=include, exam=exam["code"])
    for q in questions:
        for o in q["options"]:
            m = bank.misconception(o["tag"])
            o["label"] = "RIGHT ANSWER" if o["tag"] == "correct" else (m.statement if m else "other wrong answer")
    return {"exam": exam_out(conn, exam),
            "report": stats.class_report(conn, bank, include=include, only_done=only_done, exam=exam["code"]),
            "scores": scoring.exam_scores(conn, bank, exam["code"], include, only_done), "questions": questions,
            "build_report": _build_report(bank.name)}


def _build_report(bank_name: str) -> str | None:
    path = config.BANK_DIR / bank_name / "build_report.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


@router.get("/exams/{code}/export.csv")
def export_csv(code: str, conn: sqlite3.Connection = Depends(db)) -> Response:
    exam = _exam_or_404(conn, code)
    bank = bank_for(exam["bank_name"])
    rows = stats.export_rows(conn, bank, exam=exam["code"])
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["nickname"])
    writer.writeheader()
    writer.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="answers_{exam["code"]}.csv"'})


# ---- test data ----

@router.post("/exams/{code}/simulate", status_code=201)
def simulate(code: str, body: SimulateIn, conn: sqlite3.Connection = Depends(db)) -> dict:
    exam = _exam_or_404(conn, code)
    if exam["status"] not in ("ready", "closed"):
        raise HTTPException(409, "The exam must be open first.")
    ids = simulate_class(conn, bank_for(exam["bank_name"]), body.count, body.seed)
    exams.attach(conn, ids, exam["code"])
    return {"added": len(ids)}


@router.delete("/exams/{code}/simulated")
def remove_simulated(code: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    return {"removed": exams.clear_simulated_in(conn, _exam_or_404(conn, code)["code"])}
