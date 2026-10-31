import json

from tests.fakes import ScriptedLLM
from tutor import config, eval as ev, smoke
from tutor.judge import make_lexical_judge
from tutor.llm import PROVIDERS


def test_the_gold_bank_matches_the_expected_ground_truth(bank):
    exp = json.loads((config.ROOT / "demo" / "expected.json").read_text(encoding="utf-8"))
    r = ev.eval_bank(bank, exp)
    assert r["edges_matched"] == "5 of 5" and r["extra_edges"] == 0 and r["questions"] == 30
    assert r["per_kind"] == {"recall": 10, "apply": 10, "tiebreak": 5, "simple": 5}


def test_learner_model_recovers_what_simulated_students_know(bank):
    r = ev.eval_mastery(bank, n=45, seed=3)
    assert r["agreement_rounds_1_to_3"] >= 0.85                       # the SPEC target
    assert r["agreement_rounds_1_to_3"] >= r["agreement_rounds_1_and_2_only"] - 0.02   # round 3 should not hurt


def test_judge_score_with_a_scripted_writer(bank):
    def writer(task, prompt):
        ideas = json.loads(prompt.split("WRONG IDEAS:\n")[1])
        low = lambda t: t[0].lower() + t[1:].rstrip(".")  # noqa: E731
        return {"reasons": {i["id"]: [f"I think {low(i['wrong_idea'])}.", f"Because {low(i['wrong_idea'])}.", i["wrong_idea"]]
                            for i in ideas}}

    w = ScriptedLLM(writer)
    r = ev.eval_judge(w, make_lexical_judge(bank), bank, per=3)
    assert len(w.calls) == 5                                           # one writer call per concept, not per misconception
    assert r["misconception_items"] == 45                              # 15 misconceptions x 3 reasons each
    assert r["recovered_id"] >= 0.9 and r["named_a_different_misconception"] == 0
    assert r["sound_falsely_flagged"] <= 0.10 and r["vague_not_flagged"] == 1.0
    assert r["judged_by"] == ["lexical"]


class FakeResp:
    def __init__(self, status=200, data=None):
        self.status_code, self._d, self.text = status, data or {}, "x"

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttp:
    def __init__(self, status=200, ids=()):
        self.status, self.ids, self.urls = status, ids, []

    def get(self, url, headers, timeout):
        self.urls.append(url)
        return FakeResp(self.status, {"data": [{"id": i} for i in self.ids]})


def test_smoke_without_keys_says_so_and_never_crashes(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv("GEMINI_API_KEY", "left-in-bashrc")           # a shell key must be ignored, and not sent anywhere
    http = FakeHttp()
    results = {n: smoke.check(n, session=http) for n in PROVIDERS}
    assert all("no key" in r["status"] for r in results.values()) and http.urls == []
    assert "ignored on purpose" in results["gemini"]["status"] and "ignored" not in results["groq"]["status"]


def test_smoke_lists_models_and_suggests_without_printing_the_key(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("GROQ_API_KEY=SECRETKEY123\n")
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    for v in ("VERIFY_MODEL", "VERIFY_PROVIDER"):
        monkeypatch.delenv(v, raising=False)
    http = FakeHttp(ids=["llama-3.3-70b", "whisper-large", "llama-guard-4", "openai/gpt-oss-120b", "models/x-embed"])
    r = smoke.check("groq", session=http)
    assert r["status"].startswith("OK") and r["models"] == 5 and "whisper-large" not in r["suggested"]
    assert "SECRETKEY123" not in json.dumps(r) and "skipped" in r["json_test"]


def test_smoke_reports_a_rejected_key(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("GEMINI_API_KEY=SECRETKEY123\n")
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    r = smoke.check("gemini", session=FakeHttp(status=401))
    assert "FAIL" in r["status"] and "SECRETKEY123" not in r["status"]
