"""Shared helpers for both Streamlit apps.

The apps only call tutor.service, tutor.exams, tutor.scoring, tutor.stats and tutor.jobs. All the logic lives in tutor/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from tutor import config, llm  # noqa: E402
from tutor.db import connect  # noqa: E402
from tutor.judge import make_lexical_judge, make_llm_judge  # noqa: E402
from tutor.models import FILES, load_bank  # noqa: E402

STATE_ICON = {"understood": "🟢", "shaky": "🟠", "missing": "🔴"}
STATE_TEXT = {"understood": "Understood", "shaky": "Shaky", "missing": "Missing"}
STATUS_ICON = {"green": "🟢", "orange": "🟠", "red": "🔴"}
STATUS_COLOR = {"green": "#2e9e5b", "orange": "#d9822b", "red": "#d64545", "none": "#9ca3af"}
EXAM_STATUS = {"building": "⏳ Being prepared", "ready": "🟢 Open", "closed": "⚪ Closed", "failed": "🔴 Failed"}


def get_conn():
    """A fresh SQLite connection for this script run (cheap, and safe across Streamlit's threads)."""
    return connect()


@st.cache_resource
def get_bank(name: str):
    return load_bank(config.BANK_DIR / name)


@st.cache_resource(ttl=60)
def _judge(name: str):
    """The AI judge when a key is in .env, otherwise the built-in matcher. Re-checked every minute."""
    bank = get_bank(name)
    try:
        ai = llm.from_env("judge")
        return make_llm_judge(ai, bank), f"AI ({ai.provider.name}, {ai.model})"
    except llm.ConfigError:
        return make_lexical_judge(bank), "built-in matcher (no AI key in .env)"


def get_judge(name: str):
    return _judge(name)


def list_banks() -> list[tuple[str, str]]:
    """Complete quiz banks on this computer as (folder name, short description)."""
    out = []
    for manifest in sorted(config.BANK_DIR.glob("*/manifest.json")):
        folder = manifest.parent
        if not all((folder / f).exists() for f in FILES):
            continue
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
            n_q = len(json.loads((folder / "questions.json").read_text(encoding="utf-8")))
            n_c = len(json.loads((folder / "concepts.json").read_text(encoding="utf-8"))["concepts"])
        except (OSError, ValueError, KeyError):
            continue
        kind = "AI-built and checked" if m.get("ai_checks") else "hand-made"
        out.append((folder.name, f"{folder.name}: {m.get('pdf', '?')}, {n_c} concepts, {n_q} questions ({kind})"))
    return out
