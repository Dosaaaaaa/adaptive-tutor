"""Student routes. Anyone with an exam link can use these, and nothing else: no dashboard, no other student's data."""
from __future__ import annotations

import secrets
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from tutor import exams, scoring, service
from tutor.service import TutorError

from ..deps import bank_for, db, judge_for
from ..presenters import play_state, public_exam
from ..schemas import AnswerIn, JoinIn
from ..security import limit

router = APIRouter()


def _exam_or_404(conn: sqlite3.Connection, code: str) -> dict:
    exam = exams.get_exam(conn, code) if len(code) <= 12 else None
    if exam is None:
        raise HTTPException(404, "We could not find that exam. Check the link or the code with your teacher.")
    return exam


def _session(conn: sqlite3.Connection, token: str):
    """The student a token belongs to, with their exam and quiz. The token is long and random, so it acts as the key."""
    code = exams.student_exam(conn, token) if len(token) <= 64 else None
    exam = exams.get_exam(conn, code) if code else None
    if exam is None or not exam["bank_name"]:
        raise HTTPException(404, "We could not find this exam session.")
    return exam, bank_for(exam["bank_name"])


@router.get("/health")
def health(request: Request) -> dict:
    return {"ok": True, "mode": request.app.state.settings.mode}


@router.get("/exams/{code}/public")
def exam_public(code: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    return public_exam(conn, _exam_or_404(conn, code))


@router.post("/exams/{code}/join")
def join(code: str, body: JoinIn, request: Request, conn: sqlite3.Connection = Depends(db)) -> dict:
    limit(request, "join", 20, 60)
    exam = _exam_or_404(conn, code)
    try:
        token = exams.join_exam(conn, exam["code"], body.nickname, student_id=secrets.token_urlsafe(16))
    except exams.ExamError as exc:
        raise HTTPException(409, str(exc))
    except TutorError as exc:
        raise HTTPException(400, str(exc))
    bank = bank_for(exam["bank_name"])
    return {"token": token, "state": play_state(conn, bank, exam, token)}


@router.get("/play/{token}")
def state(token: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    exam, bank = _session(conn, token)
    return play_state(conn, bank, exam, token)


@router.post("/play/{token}/answer")
def answer(token: str, body: AnswerIn, request: Request, conn: sqlite3.Connection = Depends(db)) -> dict:
    limit(request, "answer", 120, 60, who=token)
    exam, bank = _session(conn, token)
    try:
        service.submit_answer(conn, bank, token, body.question_id, body.choice, body.reason, body.is_guess, body.seconds)
    except TutorError as exc:
        raise HTTPException(400, str(exc))
    return play_state(conn, bank, exam, token)


@router.post("/play/{token}/finish")
async def finish_round(token: str, request: Request) -> dict:
    """Run the reason judge for the round that just ended. It can take a few seconds when an AI is used."""
    limit(request, "finish", 30, 60, who=token)

    def work() -> dict:
        from tutor.db import connect
        conn = connect()
        try:
            exam, bank = _session(conn, token)
            judge, _ = judge_for(exam["bank_name"])
            service.finish_round(conn, bank, token, judge)
            return play_state(conn, bank, exam, token)
        finally:
            conn.close()

    return await run_in_threadpool(work)


@router.get("/play/{token}/results")
def results(token: str, conn: sqlite3.Connection = Depends(db)) -> dict:
    exam, bank = _session(conn, token)
    if service.progress(conn, bank, token).phase != "done":
        raise HTTPException(409, "The exam is not finished yet.")
    res = service.results(conn, bank, token)
    return {"nickname": res["student"]["nickname"], "exam": {"code": exam["code"], "title": exam["title"]},
            "score": scoring.score_for(conn, token), "concepts": res["concepts"], "review": res["review"]}
