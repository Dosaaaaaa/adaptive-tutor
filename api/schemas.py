"""Request bodies. Every field has a limit, so nothing oversized or malformed reaches the brain."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    password: str = Field(max_length=200)


class JoinIn(BaseModel):
    nickname: str = Field(min_length=1, max_length=30)


class AnswerIn(BaseModel):
    question_id: str = Field(min_length=1, max_length=40)
    choice: str = Field(pattern=r"^[A-H]$")
    reason: str = Field("", max_length=1500)
    is_guess: bool = False
    seconds: float | None = Field(None, ge=0, le=36000)


class ExamIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    seats: int = Field(30, ge=1, le=1000)
    bank: str = Field(min_length=1, max_length=120)


class SimulateIn(BaseModel):
    count: int = Field(14, ge=1, le=60)
    seed: int = Field(7, ge=0, le=9999)
