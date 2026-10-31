from tests.fakes import Boom, ScriptedLLM
from tutor.judge import JudgeItem, credit_of, make_llm_judge, make_lexical_judge, validate

IDS = {"M5.1", "M5.2", "M5.3"}


def item(reason, correct=False, tag="M5.1", aid=1, guess=False, concept="C5"):
    return JudgeItem(aid, concept, "How do the three readings compare?", "chosen text", tag,
                     "All three readings are the same", correct, reason, guess,
                     "The current is the same at every point in a series circuit.")


def test_quote_must_be_in_the_students_own_words():
    it = item("The bulb uses up some of the current to glow.")
    ok = validate({"verdict": "misconception", "misconception_id": "M5.1", "evidence_quote": "uses up some of the current",
                   "confidence": 0.9}, it, IDS)
    assert ok.verdict == "misconception" and ok.misconception_id == "M5.1"
    bad = validate({"verdict": "misconception", "misconception_id": "M5.1", "evidence_quote": "current is destroyed",
                    "confidence": 0.9}, it, IDS)
    assert bad.verdict == "unclear"                                                # invented quote is thrown away


def test_low_confidence_and_bad_values_become_unclear():
    it = item("The bulb uses up some of the current to glow.")
    q = "uses up some of the current"
    assert validate({"verdict": "misconception", "misconception_id": "M5.1", "evidence_quote": q, "confidence": 0.4},
                    it, IDS).verdict == "unclear"
    assert validate({"verdict": "banana", "confidence": 1}, it, IDS).verdict == "unclear"
    assert validate({"verdict": "sound", "confidence": "high?"}, it, IDS).verdict == "unclear"


def test_unknown_id_becomes_other_and_keeps_the_words():
    it = item("I think the bulbs are the same, so it is equal.", correct=True)
    out = validate({"verdict": "misconception", "misconception_id": "M9.9", "evidence_quote": "the bulbs are the same",
                    "confidence": 0.8}, it, IDS)
    assert out.misconception_id == "OTHER" and out.other_text == "the bulbs are the same"


def test_credit_rule():
    assert credit_of(True, "sound") and credit_of(True, "unclear") and credit_of(True, "guess")
    assert not credit_of(True, "misconception") and not credit_of(False, "sound")


def test_the_spec_example_with_four_students(bank):
    items = [item("The bulb uses up some of the current to glow, so less is left after it.", False, "M5.1", 1),
             item("There is only one path, so the same amount of charge passes every point.", True, "correct", 2),
             item("I think the bulbs are the same, so it is equal.", True, "correct", 3),
             item("The current gets divided between both bulbs.", False, "M5.2", 4)]
    answers = {1: ("misconception", "M5.1", "uses up some of the current"), 2: ("sound", None, None),
               3: ("misconception", "M9", "the bulbs are the same"), 4: ("misconception", "M5.2", "divided between both bulbs")}

    def fn(task, prompt):
        assert task == "judge" and "page_text" in prompt and "M5.2" in prompt
        return {"judgements": [{"answer_id": a, "verdict": v, "misconception_id": m, "evidence_quote": qt,
                                "confidence": 0.9} for a, (v, m, qt) in answers.items()]}

    llm = ScriptedLLM(fn)
    out = {o.answer_id: o for o in make_llm_judge(llm, bank)(items)}
    assert len(llm.calls) == 1                                                     # one call for the whole round
    assert out[1].misconception_id == "M5.1" and out[2].verdict == "sound"
    assert out[3].misconception_id == "OTHER" and not credit_of(True, out[3].verdict)   # right for the wrong reason
    assert out[4].misconception_id == "M5.2"


def test_guesses_and_empty_reasons_never_reach_the_ai(bank):
    llm = ScriptedLLM(lambda t, p: (_ for _ in ()).throw(AssertionError("AI must not be called")))
    out = make_llm_judge(llm, bank)([item("", aid=1), item("whatever I like here", aid=2, guess=True)])
    assert [o.verdict for o in out] == ["guess", "guess"] and not llm.calls


def test_ai_failure_falls_back_to_the_lexical_judge(bank):
    out = make_llm_judge(Boom(), bank)([item("The current gets divided between both bulbs.", False, "M5.2")])
    assert out[0].verdict == "misconception" and out[0].misconception_id == "M5.2" and out[0].source == "lexical"


def test_lexical_judge_does_not_flag_a_correct_explanation(bank):
    j = make_lexical_judge(bank)
    right = item("The current is the same at every point in a series circuit.", True, "correct")
    assert j([right])[0].verdict == "sound"
    flawed = item("Current is used up as it passes through each component, so it is smaller after each bulb.", True, "correct")
    assert j([flawed])[0].misconception_id == "M5.1"
    negated = item("Current is not used up as it passes through each component.", True, "correct")
    assert j([negated])[0].verdict in ("sound", "unclear")            # denying a misconception is not flagged
