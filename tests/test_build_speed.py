"""The build's speed-ups: votes that stop once settled, concepts and checks run side by side, and nothing about the result changes."""
import itertools
import threading
import time

import pytest

from tests.fakes import GoldLLM
from tutor import config
from tutor.build_bank import BuildError, build_bank
from tutor.models import Question
from tutor.parallel import run_all
from tutor.verify import blind_solve, decide

PDF = config.ROOT / "demo" / "Electricity_Basics.pdf"


class SlowGold:
    """GoldLLM that takes `latency` seconds per call, like a real AI, and is safe to call from several threads."""

    def __init__(self, gold, latency=0.0, **kw):
        self.inner, self.latency, self._lock = GoldLLM(gold, **kw), latency, threading.Lock()
        self.stats = self.inner.stats

    def call_json(self, task, prompt, schema=None, **kw):
        time.sleep(self.latency)
        with self._lock:
            return self.inner.call_json(task, prompt, schema, **kw)


def run(tmp_path, gold, workers, latency=0.0, name="t"):
    gen, ver = SlowGold(gold, latency), SlowGold(gold, latency)
    t0 = time.perf_counter()
    (built, report) = build_bank(PDF, name, gen, ver, out_dir=tmp_path / f"bank{workers}", say=lambda *_: None, workers=workers)
    return built, report, time.perf_counter() - t0


def shape(bank):
    return ([(c.id, c.name, c.page) for c in bank.concepts], [(e.parent, e.child) for e in bank.edges],
            [(m.id, m.statement) for m in bank.misconceptions],
            [(q.id, q.stem, [(o.key, o.text, o.tag) for o in q.options], q.answer_key) for q in bank.questions])


# ---- votes that stop once the outcome is settled ----

class Scripted:
    """Answers each blind-solve vote from a pattern: pattern[v] is True when vote v matches the key."""

    def __init__(self, question, pattern):
        self.q, self.pattern, self.calls = question, pattern, 0

    def call_json(self, task, prompt, schema=None, salt="", temperature=0.0, **kw):
        self.calls += 1
        v = int(salt.removeprefix("vote"))
        right = self.q.answer_key
        wrong = next(o.key for o in self.q.options if o.key != right)
        return {"answers": [{"id": self.q.id, "choice": right if self.pattern[v] else wrong}]}


@pytest.mark.parametrize("votes", [1, 2, 3, 4, 5])
def test_stopping_votes_early_never_changes_the_verdict(bank, votes):
    q: Question = bank.questions[0]
    for pattern in itertools.product([True, False], repeat=votes):
        script = Scripted(q, pattern)
        collected = blind_solve(script, bank.pages, [q], votes)[q.id]
        full = [q.answer_key if ok else "Z" for ok in pattern]
        assert bool(decide(q, collected, {q.answer_key})) == bool(decide(q, full, {q.answer_key})), (votes, pattern, collected)
        assert script.calls <= votes


def test_a_unanimous_question_costs_two_votes_not_three(bank):
    q = bank.questions[0]
    for pattern in ([True] * 3, [False] * 3):
        script = Scripted(q, pattern)
        assert len(blind_solve(script, bank.pages, [q], 3)[q.id]) == 2 and script.calls == 2
    split = Scripted(q, [True, False, True])
    assert len(blind_solve(split, bank.pages, [q], 3)[q.id]) == 3         # only a split needs the third vote


def test_the_third_vote_is_asked_only_about_the_questions_that_need_it(bank):
    import json

    qs = bank.questions[:3]
    asked = {}

    class Mixed:
        def call_json(self, task, prompt, schema=None, salt="", temperature=0.0, **kw):
            v = int(salt.removeprefix("vote"))
            payload = json.JSONDecoder().raw_decode(prompt[prompt.rfind("\n[") + 1:])[0]      # the questions this call really carries
            asked.setdefault(v, []).extend(it["id"] for it in payload)
            rows = []
            for it in payload:
                q = next(x for x in qs if x.id == it["id"])
                ok = q.id != qs[1].id or v != 1                                                 # the middle question splits on vote 1
                rows.append({"id": q.id, "choice": q.answer_key if ok else next(o.key for o in q.options if o.key != q.answer_key)})
            return {"answers": rows}

    out = blind_solve(Mixed(), bank.pages, qs, 3)
    assert asked[0] == asked[1] == [q.id for q in qs] and asked[2] == [qs[1].id]
    assert [len(out[q.id]) for q in qs] == [2, 3, 2]


# ---- side by side, same result ----

def test_running_calls_side_by_side_gives_exactly_the_same_bank(tmp_path, bank):
    one, rep1, _ = run(tmp_path, bank, workers=1)
    many, rep4, _ = run(tmp_path, bank, workers=4)
    assert shape(one) == shape(many)
    assert rep1.counts == rep4.counts and rep1.warnings == rep4.warnings and rep1.rejected == rep4.rejected


def test_side_by_side_is_much_faster_when_each_call_takes_time(tmp_path, bank):
    _, _, slow = run(tmp_path, bank, workers=1, latency=0.05)
    _, _, fast = run(tmp_path, bank, workers=5, latency=0.05)
    assert fast < slow * 0.6, (slow, fast)


def test_repairs_run_side_by_side_and_still_end_the_same(tmp_path, bank):
    def with_wrong(workers):
        gen, ver = SlowGold(bank, 0.0), SlowGold(bank, 0.0, wrong_votes={"C2-apply-1": 1, "C4-recall-1": 1, "C5-simple-1": 1})
        built, report = build_bank(PDF, "t", gen, ver, out_dir=tmp_path / f"r{workers}", say=lambda *_: None, workers=workers)
        return shape(built), sorted(report.rejected)
    assert with_wrong(1) == with_wrong(4)


def test_an_error_inside_a_worker_stops_the_build_without_hanging(tmp_path, bank):
    class FailsOnQuestions(SlowGold):
        def call_json(self, task, prompt, schema=None, **kw):
            if task == "misconceptions" and "CONCEPT_ID: C3" in prompt:
                raise RuntimeError("the provider went away")
            return super().call_json(task, prompt, schema, **kw)

    t0 = time.perf_counter()
    with pytest.raises(RuntimeError, match="went away"):
        build_bank(PDF, "t", FailsOnQuestions(bank, 0.01), SlowGold(bank), out_dir=tmp_path / "x", say=lambda *_: None, workers=4)
    assert time.perf_counter() - t0 < 5


def test_the_report_says_where_the_time_and_tokens_went(tmp_path, bank):
    _, report, _ = run(tmp_path, bank, workers=2)
    assert set(report.stages) == {"concepts", "questions", "checks"}
    text = report.markdown()
    assert "concepts " in text and "checks " in text


def test_run_all_keeps_the_order_and_raises_the_first_error():
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(3) as pool:
        assert run_all(pool, [lambda i=i: (time.sleep(0.02 * (3 - i)), i)[1] for i in range(3)]) == [0, 1, 2]
        with pytest.raises(ValueError, match="bad"):
            run_all(pool, [lambda: 1, lambda: (_ for _ in ()).throw(ValueError("bad"))])
    assert run_all(None, [lambda: "a", lambda: "b"]) == ["a", "b"]


def test_the_checks_use_one_call_per_batch_so_the_pdf_is_not_re_sent_for_every_dozen_questions(bank):
    from tutor.verify import CHUNK, support_check

    assert CHUNK >= len(bank.questions)                           # the 30 demo questions go in a single call
    calls = []

    class Counting:
        def call_json(self, task, prompt, schema=None, **kw):
            calls.append(task)
            return {"items": []}

    support_check(Counting(), bank.pages, bank.questions)
    assert calls == ["support"]
