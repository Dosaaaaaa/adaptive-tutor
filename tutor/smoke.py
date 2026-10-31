"""Check API keys, JSON mode and model names (SPEC 3 and 4). Prints OK or FAIL and model names, never a key.

Run:  python -m tutor.smoke            (add --write to save suggested models to .env)
"""
from __future__ import annotations

import argparse
import os
import re

import requests

from . import config
from .llm import LLM, PROVIDERS, LLMError

_AVOID = re.compile(r"(preview|exp|embed|tts|audio|image|vision|guard|whisper|8b|1b|3b|lite|nano|thinking|live)", re.I)
_PREFER = {"gemini": re.compile(r"flash", re.I), "groq": re.compile(r"(llama|gpt-oss|qwen|kimi)", re.I),
           "openrouter": re.compile(r":free$", re.I)}


def list_models(provider, key: str, session=requests) -> list[str]:
    r = session.get(provider.base_url.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    if r.status_code in (401, 403):
        raise LLMError(f"{provider.name} rejected the API key (HTTP {r.status_code})")
    r.raise_for_status()
    return sorted({m.get("id", "").removeprefix("models/") for m in r.json().get("data", []) if m.get("id")})


def suggest(name: str, ids: list[str]) -> list[str]:
    """A short list of likely good models. A guess from the names only: check the JSON test below."""
    good = [i for i in ids if _PREFER[name].search(i) and not _AVOID.search(i)]
    return sorted(good, key=lambda i: (len(i), i))[:5] or ids[:3]


def check(name: str, session=requests) -> dict:
    provider = PROVIDERS[name]
    key = config.api_key(provider.key_env)
    if not key:
        note = " (a key in your shell environment is ignored on purpose: put it in .env)" if os.environ.get(provider.key_env) else ""
        return {"provider": name, "status": f"no key ({provider.key_env} not set in .env){note}"}
    try:
        ids = list_models(provider, key, session)
    except Exception as exc:  # report, never crash
        return {"provider": name, "status": f"FAIL listing models: {type(exc).__name__}: {str(exc)[:120]}"}
    out = {"provider": name, "status": "OK (key accepted)", "models": len(ids), "suggested": suggest(name, ids)}
    configured = [os.environ.get(v) for v, p in (("GEN_MODEL", "GEN_PROVIDER"), ("VERIFY_MODEL", "VERIFY_PROVIDER"))
                  if os.environ.get(p, {"GEN_PROVIDER": "gemini", "VERIFY_PROVIDER": "groq"}[p]) == name]
    model = next((m for m in configured if m), None)
    if model:
        try:
            got = LLM(provider, model, key, cache=False).call_json("smoke", 'Return exactly this JSON: {"ok": true}',
                                                                     temperature=0.0, max_tokens=600)
            out["json_test"] = f"OK with {model}" if isinstance(got, dict) and got.get("ok") is True \
                else f"FAIL with {model}: unexpected answer"
        except Exception as exc:
            out["json_test"] = f"FAIL with {model}: {type(exc).__name__}: {str(exc)[:120]}"
    else:
        out["json_test"] = "skipped: set GEN_MODEL / VERIFY_MODEL in .env, then run again"
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Check keys, JSON mode and models.")
    ap.add_argument("--write", action="store_true", help="append suggested GEN_MODEL / VERIFY_MODEL to .env if unset")
    args = ap.parse_args()
    config.load_env()
    results = [check(n) for n in PROVIDERS]
    for r in results:
        print(f"{r['provider']:<11} {r['status']}")
        if "models" in r:
            print(f"            {r['models']} models. Suggested: {', '.join(r['suggested'])}")
            print(f"            JSON test: {r['json_test']}")
    if not config.ENV_FILE.exists():
        print("\nNo .env file yet. Copy .env.example to .env and add your keys.")
    if args.write:
        by = {r["provider"]: r for r in results if r.get("suggested")}
        lines = []
        for var, prov in (("GEN_MODEL", os.environ.get("GEN_PROVIDER", "gemini")),
                          ("VERIFY_MODEL", os.environ.get("VERIFY_PROVIDER", "groq"))):
            if not os.environ.get(var) and prov in by:
                lines.append(f"{var}={by[prov]['suggested'][0]}")
        if lines:
            with open(config.ENV_FILE, "a", encoding="utf-8") as f:
                f.write("\n" + "\n".join(lines) + "\n")
            print("\nAppended to .env:", ", ".join(l.split("=")[0] for l in lines), "(check the JSON test, then re-run)")


if __name__ == "__main__":
    main()
