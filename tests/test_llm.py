import json

import pytest
import requests
from pydantic import BaseModel

from tests.fakes import Boom
from tutor import llm
from tutor.llm import LLM, LLMAuthError, LLMError, LLMFormatError, PROVIDERS, extract_json, model_family

SECRET = "SECRETKEY123"


class Resp:
    def __init__(self, status=200, content=None, headers=None, text=""):
        self.status_code, self.headers, self.text = status, headers or {}, text or (content or "")
        self._json = {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    def json(self):
        return self._json


class Session:
    def __init__(self, *responses):
        self.responses, self.posts = list(responses), []

    def post(self, url, headers, json, timeout):
        self.posts.append((url, dict(json)))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class Clock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def now(self):
        return self.t


def make(tmp_path, *responses, **kw):
    c = Clock()
    kw.setdefault("rpm", 600)
    return LLM(PROVIDERS["groq"], "llama-x", SECRET, session=Session(*responses), sleep=c.sleep, clock=c.now,
               cache_dir=tmp_path, **kw), c


def test_extract_json_handles_fences_and_chatter():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": [1, 2]} hope that helps') == {"a": [1, 2]}
    assert extract_json('[{"a": 1}]') == [{"a": 1}]                    # a one-item list stays a list
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_answer_is_cached_so_the_second_call_costs_nothing(tmp_path):
    ai, _ = make(tmp_path, Resp(content='{"ok": true}'), Resp(content='{"ok": "second"}'))
    assert ai.call_json("t", "hello") == {"ok": True}
    assert ai.call_json("t", "hello") == {"ok": True}
    assert len(ai.session.posts) == 1 and ai.stats["cache_hits"] == 1 and ai.stats["calls"] == 1
    assert ai.call_json("t", "hello", salt="vote1") == {"ok": "second"}       # a new salt is a new question


def test_retry_after_is_honoured_on_429(tmp_path):
    ai, clock = make(tmp_path, Resp(429, headers={"Retry-After": "7"}), Resp(content='{"ok": 1}'))
    assert ai.call_json("t", "p") == {"ok": 1}
    assert clock.sleeps == [7.0] and ai.stats["retries"] == 1


def test_server_errors_back_off_then_give_up(tmp_path):
    ai, clock = make(tmp_path, *[Resp(503) for _ in range(5)])
    with pytest.raises(LLMError, match="gave up"):
        ai.call_json("t", "p")
    assert clock.sleeps[:3] == [2, 4, 8] and len(ai.session.posts) == 5


def test_a_rejected_key_fails_fast_and_never_leaks_the_key(tmp_path):
    ai, _ = make(tmp_path, Resp(401, text="bad key"))
    with pytest.raises(LLMAuthError) as exc:
        ai.call_json("t", "p")
    assert SECRET not in str(exc.value) and len(ai.session.posts) == 1


def test_network_errors_are_retried(tmp_path):
    ai, _ = make(tmp_path, requests.ConnectionError("boom"), Resp(content='{"ok": 1}'))
    assert ai.call_json("t", "p") == {"ok": 1}


def test_json_mode_is_dropped_when_the_provider_refuses_it(tmp_path):
    ai, _ = make(tmp_path, Resp(400, text="response_format is not supported"), Resp(content='{"ok": 1}'))
    assert ai.call_json("t", "p") == {"ok": 1}
    assert "response_format" in ai.session.posts[0][1] and "response_format" not in ai.session.posts[1][1]


def cut_off(content):
    r = Resp(content=content)
    r._json["choices"][0]["finish_reason"] = "length"
    return r


def test_a_cut_off_answer_is_retried_with_a_bigger_token_budget(tmp_path):
    ai, _ = make(tmp_path, cut_off(""), cut_off('{"ok'), Resp(content='{"ok": 1}'))      # a thinking model ran out of tokens
    assert ai.call_json("t", "p", max_tokens=100) == {"ok": 1}
    assert [p[1]["max_tokens"] for p in ai.session.posts] == [100, 200, 400]


def test_the_token_budget_has_a_ceiling(tmp_path):
    ai, _ = make(tmp_path, *[cut_off("") for _ in range(5)], max_retries=5)
    with pytest.raises(LLMError, match="empty answer"):
        ai.call_json("t", "p", max_tokens=10000)
    assert max(p[1]["max_tokens"] for p in ai.session.posts) == llm.MAX_TOKENS_CAP


def test_a_json_validation_error_gets_more_room_then_json_mode_is_dropped(tmp_path):
    bad = Resp(400, text='{"error":{"message":"Failed to validate JSON. Please adjust your prompt."}}')
    ai, _ = make(tmp_path, bad, bad, Resp(content='{"ok": 1}'))
    assert ai.call_json("t", "p", max_tokens=100) == {"ok": 1}
    first, second, third = (p[1] for p in ai.session.posts)
    assert second["max_tokens"] == 200 and "response_format" in second and "response_format" not in third


def test_one_repair_attempt_for_bad_json_then_a_clear_error(tmp_path):
    ai, _ = make(tmp_path, Resp(content="not json"), Resp(content='{"ok": 1}'))
    assert ai.call_json("t", "p") == {"ok": 1} and ai.stats["repairs"] == 1
    assert "not valid" in ai.session.posts[1][1]["messages"][-1]["content"]
    ai2, _ = make(tmp_path / "x", Resp(content="nope"), Resp(content="still nope"))
    with pytest.raises(LLMFormatError):
        ai2.call_json("t", "p")


class Shape(BaseModel):
    n: int


def test_schema_validation_triggers_a_repair_and_bad_answers_are_not_cached(tmp_path):
    ai, _ = make(tmp_path, Resp(content='{"n": "abc"}'), Resp(content='{"n": 3}'))
    assert ai.call_json("t", "p", Shape).n == 3
    assert len(list(tmp_path.glob("*.json"))) == 1                       # only the valid answer is stored


def test_the_fallback_provider_is_used_when_the_first_fails(tmp_path):
    fb, _ = make(tmp_path / "fb", Resp(content='{"from": "fallback"}'))
    ai, _ = make(tmp_path / "main", Resp(500), Resp(500), Resp(500), Resp(500), Resp(500), fallback=fb)
    assert ai.call_json("t", "p") == {"from": "fallback"} and ai.stats["fallbacks"] == 1


def test_after_a_total_failure_the_fallback_is_used_straight_away_until_the_cooldown_ends(tmp_path):
    fb, _ = make(tmp_path / "fb", Resp(content='{"n": 1}'), Resp(content='{"n": 2}'), Resp(content='{"n": 3}'))
    ai, clock = make(tmp_path / "main", *[Resp(503) for _ in range(5)], Resp(content='{"n": "primary again"}'), fallback=fb)
    assert ai.call_json("t", "a") == {"n": 1}                           # five 503s, then the fallback answers
    posts_after_outage = len(ai.session.posts)
    assert ai.call_json("t", "b") == {"n": 2}                           # no waiting: the primary is skipped
    assert len(ai.session.posts) == posts_after_outage
    clock.t += llm.COOLDOWN_SECONDS + 1                                 # cooldown over: try the primary again
    assert ai.call_json("t", "c") == {"n": "primary again"}


def test_calls_are_spaced_by_the_rate_limit(tmp_path):
    ai, clock = make(tmp_path, Resp(content='{"a": 1}'), Resp(content='{"b": 1}'), rpm=30)
    ai.call_json("t", "one")
    ai.call_json("t", "two")
    assert clock.sleeps == [2.0]                                         # 60 / 30 per minute


def test_model_families():
    assert model_family("groq", "llama-3.3-70b") == "meta" and model_family("gemini", "gemini-x-flash") == "google"
    assert model_family("groq", "openai/gpt-oss-120b") == "openai" and model_family("groq", "mystery") == "groq"


def test_generator_and_verifier_must_differ(tmp_path):
    a = LLM(PROVIDERS["gemini"], "gemini-x", "k", cache_dir=tmp_path)
    b = LLM(PROVIDERS["groq"], "llama-x", "k", cache_dir=tmp_path)
    llm.assert_independent(a, b)
    with pytest.raises(llm.ConfigError, match="both 'google'"):
        llm.assert_independent(a, LLM(PROVIDERS["openrouter"], "google/gemini-y", "k", cache_dir=tmp_path))
    a.fallback = LLM(PROVIDERS["groq"], "openai/gpt-oss-20b", "k", cache_dir=tmp_path)        # a fallback must differ too
    with pytest.raises(llm.ConfigError, match="fallback and the verifier are both 'openai'"):
        llm.assert_independent(a, LLM(PROVIDERS["groq"], "openai/gpt-oss-120b", "k", cache_dir=tmp_path))


def test_from_env_names_the_missing_variable_not_the_value(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    monkeypatch.setattr(llm.config, "ENV_FILE", env)
    for v in ("GEN_PROVIDER", "GEN_MODEL", "GEMINI_API_KEY", "VERIFY_PROVIDER", "VERIFY_MODEL", "JUDGE_PROVIDER", "JUDGE_MODEL"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(llm.ConfigError, match="GEN_MODEL is not set"):
        llm.from_env("generator")
    env.write_text("GEN_MODEL=gemini-x\n")
    with pytest.raises(llm.ConfigError, match="GEMINI_API_KEY is not set"):
        llm.from_env("generator")
    env.write_text(f"GEN_MODEL=gemini-x\nGEMINI_API_KEY={SECRET}\n")
    assert llm.from_env("generator").model == "gemini-x"
    env.write_text(f"GEN_PROVIDER=nope\nGEN_MODEL=gemini-x\nGEMINI_API_KEY={SECRET}\n")
    with pytest.raises(llm.ConfigError, match="not one of"):
        llm.from_env("generator")


def test_a_key_in_the_shell_environment_is_never_used(monkeypatch, tmp_path):
    monkeypatch.setattr(llm.config, "ENV_FILE", tmp_path / ".env")        # no .env at all
    monkeypatch.setenv("GEMINI_API_KEY", "left-in-bashrc-by-another-tool")
    monkeypatch.setenv("GEN_MODEL", "gemini-x")
    with pytest.raises(llm.ConfigError, match="GEMINI_API_KEY is not set in .env"):
        llm.from_env("generator")
