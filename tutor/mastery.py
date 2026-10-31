"""Learner model: probability of mastery per concept (SPEC 7, function 2).

Bayesian Knowledge Tracing with learning rate 0 inside the test: no feedback is shown, so nothing is learned
between questions. The answer order therefore does not change the final number, but the trail after each
answer is kept for the live panel. Defaults are assumptions to tune on simulation.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log

UNDERSTOOD, SHAKY, MISSING = "understood", "shaky", "missing"


@dataclass(frozen=True)
class Params:
    p0: float = 0.30            # prior: chance a student knows a concept before the first answer
    guess: float = 0.25         # chance of a right answer without knowing (4 options)
    slip: float = 0.10          # chance of a wrong answer while knowing
    guess_weight: float = 0.5   # an answer ticked "I am guessing" counts half
    understood: float = 0.85
    shaky: float = 0.40


DEFAULT = Params()


@dataclass(frozen=True)
class Obs:
    """One answer as the model sees it. `credited` already includes the reason check."""
    answer_id: int
    credited: bool
    is_guess: bool = False


def _prob(logit: float) -> float:
    return 1.0 / (1.0 + exp(-logit))


def update(logit: float, credited: bool, is_guess: bool, params: Params = DEFAULT) -> float:
    step = log((1 - params.slip) / params.guess) if credited else log(params.slip / (1 - params.guess))
    return logit + (params.guess_weight if is_guess else 1.0) * step


def trail(observations: list[Obs], params: Params = DEFAULT) -> list[float]:
    """Mastery probability after each answer, in order."""
    logit = log(params.p0 / (1 - params.p0))
    out = []
    for o in observations:
        logit = update(logit, o.credited, o.is_guess, params)
        out.append(_prob(logit))
    return out


def final(observations: list[Obs], params: Params = DEFAULT) -> float:
    t = trail(observations, params)
    return t[-1] if t else params.p0


def state(p: float, params: Params = DEFAULT) -> str:
    if p >= params.understood:
        return UNDERSTOOD
    if p >= params.shaky:
        return SHAKY
    return MISSING
