"""One wrapper for every free AI provider (SPEC 4).

Gemini, Groq and OpenRouter all speak the same /chat/completions protocol, so a thin HTTP client is enough.
Provides: disk cache of validated answers, throttle, backoff that honours Retry-After, one JSON repair attempt,
and an optional fallback provider. Keys are read from the environment and are never logged or printed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, ValidationError

from . import config

log = logging.getLogger(__name__)


MAX_TOKENS_CAP = 16384   # reasoning models spend hidden "thinking" tokens from the same budget
REQUEST_TIMEOUT = 180    # slow thinking models can take over a minute
COOLDOWN_SECONDS = 180   # after a provider fails completely, go straight to the fallback for this long


class LLMError(Exception):
    """The provider failed (network, quota, server)."""


class LLMAuthError(LLMError):
    """The provider rejected the key."""


class LLMFormatError(LLMError):
    """The provider answered, but not with usable JSON."""


class ConfigError(Exception):
    """Something is missing in .env."""


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    key_env: str
    rpm: int  # conservative default; override with <NAME>_RPM in .env


PROVIDERS = {
    "gemini": Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", 10),
    "groq": Provider("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", 20),
    "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", 10),
}
_FAMILIES = (("gemini", "google"), ("gemma", "google"), ("llama", "meta"), ("gpt", "openai"), ("oss", "openai"),
             ("qwen", "alibaba"), ("mistral", "mistral"), ("mixtral", "mistral"), ("deepseek", "deepseek"),
             ("claude", "anthropic"))


def model_family(provider: str, model: str) -> str:
    m = model.lower()
    return next((fam for key, fam in _FAMILIES if key in m), provider)


def extract_json(text: str) -> Any:
    """Parse JSON from a model answer, tolerating code fences and chatter around it."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.I)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    spans = sorted((t.find(o), o, c) for o, c in (("{", "}"), ("[", "]")) if t.find(o) != -1)
    for i, _, close in spans:
        j = t.rfind(close)
        if j > i:
            try:
                return json.loads(t[i:j + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no valid JSON found in the answer")


def _json_validation_failed(text: str) -> bool:
    t = (text or "").lower()
    return "failed to validate json" in t or "json_validate_failed" in t


class LLM:
    def __init__(self, provider: Provider, model: str, api_key: str, *, role: str = "generator", cache: bool = True,
                 session: Any = None, fallback: "LLM | None" = None, sleep=time.sleep, clock=time.monotonic,
                 cache_dir: Path | None = None, max_retries: int = 5, rpm: int | None = None):
        self.provider, self.model, self.role = provider, model, role
        self._key, self.session = api_key, session or requests.Session()
        self.cache, self.cache_dir, self.fallback = cache, cache_dir or config.CACHE_DIR, fallback
        self._sleep, self._clock, self.max_retries = sleep, clock, max_retries
        self.rpm = rpm or int(os.environ.get(f"{provider.name.upper()}_RPM", provider.rpm))
        self._last, self._json_mode, self._down_until = float("-inf"), True, float("-inf")
        self.stats = {"calls": 0, "cache_hits": 0, "retries": 0, "repairs": 0, "fallbacks": 0,
                      "tokens_in": 0, "tokens_out": 0}

    @property
    def family(self) -> str:
        return model_family(self.provider.name, self.model)

    # ---- public ----
    def call_json(self, task: str, prompt: str, schema: type[BaseModel] | None = None, *, system: str | None = None,
                  temperature: float = 0.2, max_tokens: int = 8192, salt: str = "") -> Any:
        """Ask for JSON. Returns a dict/list, or a validated `schema` object. Never caches a bad answer."""
        if self.fallback is not None and self._clock() < self._down_until:   # known to be down: do not wait again
            self.stats["fallbacks"] += 1
            return self.fallback.call_json(task, prompt, schema, system=system, temperature=temperature,
                                           max_tokens=max_tokens, salt=salt)
        try:
            return self._call(task, prompt, schema, system, temperature, max_tokens, salt)
        except LLMFormatError:
            raise
        except LLMError as exc:
            if self.fallback is None:
                raise
            self._down_until = self._clock() + COOLDOWN_SECONDS
            self.stats["fallbacks"] += 1
            log.warning("%s failed for %s (%s). Trying the fallback provider.", self.provider.name, task, exc)
            return self.fallback.call_json(task, prompt, schema, system=system, temperature=temperature,
                                           max_tokens=max_tokens, salt=salt)

    # ---- internals ----
    def _key_for(self, prompt: str, system, temperature: float, salt: str, schema) -> Path:
        raw = json.dumps([self.provider.name, self.model, system, prompt, temperature, salt,
                          schema.__name__ if schema else None], ensure_ascii=False)
        return self.cache_dir / (hashlib.sha256(raw.encode()).hexdigest() + ".json")

    @staticmethod
    def _wrap(data: Any, schema):
        return schema.model_validate(data) if schema is not None else data

    def _call(self, task, prompt, schema, system, temperature, max_tokens, salt):
        path = self._key_for(prompt, system, temperature, salt, schema)
        if self.cache and path.exists():
            try:
                hit = self._wrap(json.loads(path.read_text(encoding="utf-8")), schema)
                self.stats["cache_hits"] += 1
                return hit
            except (ValueError, ValidationError):
                pass  # stale cache entry: ask again
        text, ask = None, prompt
        for attempt in (0, 1):
            text = self._complete(ask, system, temperature, max_tokens)
            try:
                data = extract_json(text)
                result = self._wrap(data, schema)
                if self.cache:
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return result
            except (ValueError, ValidationError) as exc:
                if attempt == 1:
                    raise LLMFormatError(f"{task}: the answer was not valid after a repair attempt ({str(exc)[:160]})")
                self.stats["repairs"] += 1
                ask = (prompt + "\n\nYour previous answer was not valid: " + str(exc)[:400].replace("\n", " ")
                       + "\nReturn ONLY the corrected JSON, with no other text.")

    def _throttle(self) -> None:
        wait = self._last + 60.0 / max(self.rpm, 1) - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()

    def _complete(self, prompt: str, system: str | None, temperature: float, max_tokens: int) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        body = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        url = self.provider.base_url.rstrip("/") + "/chat/completions"
        budget, json_failures = max_tokens, 0
        for attempt in range(self.max_retries):
            body["max_tokens"] = budget
            if self._json_mode:
                body["response_format"] = {"type": "json_object"}
            else:
                body.pop("response_format", None)
            self._throttle()
            try:
                r = self.session.post(url, headers={"Authorization": f"Bearer {self._key}"}, json=body, timeout=REQUEST_TIMEOUT)
            except requests.RequestException as exc:
                self._backoff(attempt, None, f"network error: {type(exc).__name__}")
                continue
            self.stats["calls"] += 1
            if r.status_code == 200:
                data = r.json()
                use = data.get("usage") or {}
                self.stats["tokens_in"] += use.get("prompt_tokens", 0) or 0
                self.stats["tokens_out"] += use.get("completion_tokens", 0) or 0
                try:
                    choice = data["choices"][0]
                    content = choice["message"]["content"]
                    truncated = choice.get("finish_reason") == "length"
                except (KeyError, IndexError, TypeError):
                    content, truncated = None, False
                if truncated and budget < MAX_TOKENS_CAP:  # cut off: a thinking model used the budget up
                    budget = min(budget * 2, MAX_TOKENS_CAP)
                    self.stats["retries"] += 1
                    log.info("%s: answer was cut off, retrying with %d tokens", self.provider.name, budget)
                    continue
                if not content:
                    raise LLMError(f"{self.provider.name}: empty answer" + (" (token limit reached)" if truncated else ""))
                return content
            if r.status_code in (401, 403):
                raise LLMAuthError(f"{self.provider.name} rejected the API key (HTTP {r.status_code})")
            if r.status_code == 400 and self._json_mode and "response_format" in r.text:
                self._json_mode = False  # this provider or model has no JSON mode: rely on the prompt
                continue
            if r.status_code == 400 and _json_validation_failed(r.text):
                # the provider could not validate the JSON it produced: usually cut off. Give it more room first,
                # then drop JSON mode and rely on the prompt.
                json_failures += 1
                self.stats["retries"] += 1
                if json_failures == 1 and budget < MAX_TOKENS_CAP:
                    budget = min(budget * 2, MAX_TOKENS_CAP)
                else:
                    self._json_mode = False
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                try:
                    retry_after = float(r.headers.get("Retry-After", ""))
                except (TypeError, ValueError):
                    retry_after = None
                self._backoff(attempt, retry_after, f"HTTP {r.status_code}")
                continue
            raise LLMError(f"{self.provider.name}: HTTP {r.status_code}: {r.text[:200]}")
        raise LLMError(f"{self.provider.name}: gave up after {self.max_retries} attempts")

    def _backoff(self, attempt: int, retry_after: float | None, why: str) -> None:
        self.stats["retries"] += 1
        wait = min(retry_after if retry_after is not None else 2 ** (attempt + 1), 60.0)
        log.info("%s: %s, waiting %.0fs", self.provider.name, why, wait)
        self._sleep(wait)


ROLES = {"generator": ("GEN_PROVIDER", "GEN_MODEL", "gemini"), "verifier": ("VERIFY_PROVIDER", "VERIFY_MODEL", "groq"),
         "judge": ("JUDGE_PROVIDER", "JUDGE_MODEL", None)}


def from_env(role: str, *, cache: bool = True) -> LLM:
    """Build the AI client for a role from .env. Raises ConfigError that names the missing variable, never a key."""
    config.load_env()
    prov_var, model_var, default = ROLES[role]
    name = os.environ.get(prov_var) or default or os.environ.get("VERIFY_PROVIDER") or "groq"
    model = os.environ.get(model_var) or (os.environ.get("VERIFY_MODEL") if role == "judge" else None)
    if name not in PROVIDERS:
        raise ConfigError(f"{prov_var}={name!r} is not one of {sorted(PROVIDERS)}")
    if not model:
        raise ConfigError(f"{model_var} is not set. Run: python -m tutor.smoke")
    provider = PROVIDERS[name]
    key = config.api_key(provider.key_env)
    if not key:
        raise ConfigError(f"{provider.key_env} is not set in .env (the shell environment is not used for keys)")
    fallback = None
    fb_name, fb_model = os.environ.get("FALLBACK_PROVIDER") or "openrouter", os.environ.get("FALLBACK_MODEL")
    if role != "judge" and fb_model and fb_name in PROVIDERS and fb_name != name and config.api_key(PROVIDERS[fb_name].key_env):
        # never used for the judge: student text only goes to the judge provider
        fallback = LLM(PROVIDERS[fb_name], fb_model, config.api_key(PROVIDERS[fb_name].key_env), role=role, cache=cache)
    return LLM(provider, model, key, role=role, cache=cache, fallback=fallback)


def assert_independent(generator: LLM, verifier: LLM) -> None:
    """The checker must not be the same model family as the writer (SPEC 4 rule 5)."""
    for name, writer in (("generator", generator), ("fallback", generator.fallback)):
        if writer is not None and writer.family == verifier.family:
            raise ConfigError(f"The {name} and the verifier are both '{writer.family}'. "
                              "Use a different family for the verifier (SPEC 4).")
