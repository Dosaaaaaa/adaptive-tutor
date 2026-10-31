"""Runtime settings for the web API, read once at start-up.

Environment variables win over `.env`. Nothing secret is ever printed or returned by the API.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from tutor import config

MODES = ("all", "teacher", "student")


@dataclass(frozen=True)
class Settings:
    mode: str = "all"                       # all: both | teacher: private instance | student: public exam link only
    teacher_password: str | None = None
    public_url: str | None = None           # for example a tunnel or the school's address
    cookie_secure: bool = False             # set to true behind HTTPS
    allowed_origins: tuple[str, ...] = ()   # extra origins allowed to send state-changing requests
    session_secret: bytes = b""
    session_hours: int = 12
    trust_proxy: bool = False               # read the client address from X-Forwarded-For (only behind your own proxy)
    web_dist: Path = config.ROOT / "web" / "dist"


def _session_secret(env: dict[str, str]) -> bytes:
    """A secret that survives restarts, so teachers stay logged in. Generated once and kept private."""
    given = os.environ.get("SESSION_SECRET") or env.get("SESSION_SECRET")
    if given:
        return given.encode()
    path = config.DATA_DIR / "session.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        os.chmod(path, 0o600)
    return path.read_text().strip().encode()


def load_settings(**overrides) -> Settings:
    env = config.read_env_file()
    get = lambda name, default=None: os.environ.get(name) or env.get(name) or default  # noqa: E731
    flag = lambda name: str(get(name, "")).lower() in ("1", "true", "yes", "on")  # noqa: E731
    mode = get("TUTOR_MODE", "all")
    if mode not in MODES:
        raise ValueError(f"TUTOR_MODE must be one of {MODES}, not {mode!r}")
    base = Settings(
        mode=mode,
        teacher_password=get("TEACHER_PASSWORD"),
        public_url=(get("PUBLIC_URL") or "").rstrip("/") or None,
        cookie_secure=flag("COOKIE_SECURE"),
        allowed_origins=tuple(o.strip().rstrip("/") for o in str(get("ALLOWED_ORIGINS", "")).split(",") if o.strip()),
        session_secret=b"",
        trust_proxy=flag("TRUST_PROXY"),
        web_dist=Path(get("WEB_DIST", str(config.ROOT / "web" / "dist"))),
    )
    values = {**base.__dict__, **overrides}
    if not values["session_secret"]:
        values["session_secret"] = _session_secret(env)
    return Settings(**values)
