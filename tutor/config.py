"""Settings and thresholds. Everything tunable lives here (SPEC sections 1, 4, 7, 9, 11)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK_DIR = ROOT / "bank"
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache" / "llm"
ENV_FILE = ROOT / ".env"

# Build
MAX_CONCEPTS = 5            # demo scale. Use 12 to 15 for a 30 to 40 page PDF.
VOTES = 3                   # blind-solve runs per question
MAX_ATTEMPTS = 3            # regenerate a failing question this many times
CONTEXT_CHARS = 14000       # max document text sent in one build call
PER_KIND = {"recall": 2, "apply": 2, "tiebreak": 1, "simple": 1}
ROUND_OF_KIND = {"recall": 1, "apply": 2, "tiebreak": 3, "simple": 3}
KIND_ORDER = ("recall", "apply", "tiebreak", "simple")

# Where the apps listen. Students get the student port; the teacher app stays on this computer only.
TEACHER_PORT = 8501
STUDENT_PORT = 8502

# Uploads (teacher only)
UPLOAD_DIR = DATA_DIR / "uploads"
BUILD_DIR = DATA_DIR / "builds"
MAX_UPLOAD_MB = 20
MAX_PDF_PAGES = 80

# Students
MIN_REASON_WORDS = 6
GROUP_BY_CODE = {"DEMO-ALL": "read_all", "DEMO-P13": "read_p1_3", "DEMO-COLD": "cold"}

# Judge
JUDGE_MIN_CONFIDENCE = 0.6

# Class dashboard: shares are "students in state understood"
CLASS_GREEN = 0.75
CLASS_ORANGE = 0.50
START_HERE_ROOT_SHARE = 0.30
CARD_MIN_NOT_UNDERSTOOD = 0.25
MAX_CARDS = 3

# Question difficulty
EASY_P, HARD_P = 0.75, 0.45
CHECK_BELOW_P, CHECK_MIN_N = 0.25, 8
TOO_EASY_P, TOO_EASY_MIN_N = 0.95, 10


def db_path() -> Path:
    return Path(os.environ.get("TUTOR_DB") or DATA_DIR / "tutor.db")


def read_env_file(path: Path | None = None) -> dict[str, str]:
    """Parse .env (KEY=value lines). Blank values and comments are ignored."""
    path = path or ENV_FILE
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if key.strip() and value:
            out[key.strip()] = value
    return out


def load_env(path: Path | None = None) -> None:
    """Put .env settings (models, providers) into the environment. For names it defines, .env wins over the shell."""
    os.environ.update(read_env_file(path))


def api_key(var: str) -> str | None:
    """API keys are read ONLY from .env, never from the shell environment. A key that another tool left in
    ~/.bashrc is therefore never used by accident and never hides the key you put here."""
    return read_env_file().get(var) or None


def resolve_bank(name: str | None = None) -> Path:
    """Folder of the bank to use: argument, then BANK_NAME (environment or .env), then the newest bank."""
    name = name or os.environ.get("BANK_NAME") or read_env_file().get("BANK_NAME")
    if name:
        path = BANK_DIR / name
        if not (path / "manifest.json").exists():
            raise FileNotFoundError(f"No bank named {name!r} in {BANK_DIR}")
        return path
    banks = sorted((p for p in BANK_DIR.glob("*/manifest.json")), key=lambda p: p.stat().st_mtime)
    if not banks:
        raise FileNotFoundError(f"No bank found in {BANK_DIR}. Run: python -m tutor.build_bank <pdf>")
    return banks[-1].parent
