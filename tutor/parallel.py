"""Run independent AI calls side by side. Used by the quiz-bank build; nothing else in the brain depends on it."""
from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")


def run_all(pool, jobs: list[Callable[[], T]]) -> list[T]:
    """Run zero-argument jobs, on `pool` when there is one, and return their results in the order given.
    Without a pool they simply run one after another. An error in any job is raised here, and the jobs not yet started are dropped."""
    if pool is None:
        return [job() for job in jobs]
    futures = [pool.submit(job) for job in jobs]
    try:
        return [f.result() for f in futures]
    except BaseException:
        for f in futures:
            f.cancel()
        raise
