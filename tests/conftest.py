import os
import random

import pytest

from tutor import config, service
from tutor.db import connect, load_bank_into_db
from tutor.judge import make_lexical_judge
from tutor.models import load_bank
from tutor.simulate import simulate_student


@pytest.fixture(scope="session")
def bank():
    return load_bank(config.BANK_DIR / "electricity_gold")


@pytest.fixture()
def conn(bank):
    c = connect(":memory:")
    load_bank_into_db(c, bank)
    return c


@pytest.fixture()
def lexical(bank):
    return make_lexical_judge(bank)


@pytest.fixture()
def run(conn, bank, lexical):
    """run(known, fav=None) -> student id. Deterministic: knowers never slip, others never guess."""
    def _run(known, fav=None, nickname="t", group="read_all", **kw):
        return simulate_student(conn, bank, nickname=nickname, group=group, known=set(known), rng=random.Random(1),
                                judge=lexical, favourite=fav or {}, guess=kw.pop("guess", 0.0),
                                slip=kw.pop("slip", 0.0), **kw)
    return _run


@pytest.fixture(autouse=True)
def isolated_environ(monkeypatch):
    """Every test gets its own copy of the environment, so settings loaded from a .env cannot leak between tests."""
    monkeypatch.setattr(os, "environ", os.environ.copy())
