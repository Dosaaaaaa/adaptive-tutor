"""Shared building blocks for the routes: database, quiz bank and judge caches, and the teacher check."""
from __future__ import annotations

import sqlite3
import threading
import time
from typing import Iterator

from fastapi import HTTPException, Request

from tutor import config, llm
from tutor.db import connect
from tutor.judge import make_lexical_judge, make_llm_judge
from tutor.models import Bank, load_bank

from .security import COOKIE, valid_session

_banks: dict[str, Bank] = {}
_judges: dict[str, tuple[float, object, str]] = {}
_lock = threading.Lock()


def db() -> Iterator[sqlite3.Connection]:
    """One short-lived SQLite connection per request (WAL mode makes this cheap and safe)."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def bank_for(name: str | None) -> Bank:
    if not name:
        raise HTTPException(409, "This exam has no quiz yet.")
    with _lock:
        if name not in _banks:
            try:
                _banks[name] = load_bank(config.BANK_DIR / name)
            except (OSError, ValueError, KeyError):
                raise HTTPException(409, "The quiz for this exam is not available.")
        return _banks[name]


def judge_for(name: str):
    """The AI judge when a key is in .env, otherwise the built-in matcher. Re-checked every minute."""
    now = time.monotonic()
    with _lock:
        hit = _judges.get(name)
        if hit and now - hit[0] < 60:
            return hit[1], hit[2]
    bank = bank_for(name)
    try:
        ai = llm.from_env("judge")
        judge, label = make_llm_judge(ai, bank), f"AI ({ai.provider.name}, {ai.model})"
    except llm.ConfigError:
        judge, label = make_lexical_judge(bank), "built-in matcher (no AI key in .env)"
    with _lock:
        _judges[name] = (now, judge, label)
    return judge, label


def forget_caches() -> None:
    """For tests and for after a new bank is built."""
    with _lock:
        _banks.clear()
        _judges.clear()


def require_teacher(request: Request) -> None:
    if not valid_session(request.app.state.settings.session_secret, request.cookies.get(COOKIE)):
        raise HTTPException(401, "Please sign in.")
