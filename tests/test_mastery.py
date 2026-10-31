import pytest

from tutor import mastery
from tutor.mastery import Obs


def obs(*flags):
    return [Obs(i, bool(f)) for i, f in enumerate(flags)]


@pytest.mark.parametrize("answers, p, state", [
    ((1, 1, 1, 1), 0.986, "understood"),          # SPEC 7 fixtures
    ((1, 1, 1, 0), 0.727, "shaky"),
    ((1, 1, 0, 0), 0.090, "missing"),
    ((1, 1, 1, 0, 1, 1), 0.972, "understood"),    # 3 of 4, then 2 of 2 in round 3
    ((1, 1, 1, 0, 1, 0), 0.561, "shaky"),         # 3 of 4, then 1 of 2
    ((1, 0, 0, 1, 0, 1), 0.045, "missing"),       # 3 of 6
])
def test_spec_fixtures(answers, p, state):
    got = mastery.final(obs(*answers))
    assert round(got, 3) == p
    assert mastery.state(got) == state


def test_no_answers_is_the_prior():
    assert mastery.final([]) == mastery.DEFAULT.p0
    assert mastery.trail([]) == []


def test_order_does_not_change_the_final_number():
    assert mastery.final(obs(1, 0, 1, 1)) == pytest.approx(mastery.final(obs(1, 1, 1, 0)))


def test_trail_moves_after_each_answer():
    t = mastery.trail(obs(1, 1, 0))
    assert len(t) == 3 and t[0] > mastery.DEFAULT.p0 and t[1] > t[0] and t[2] < t[1]


def test_a_guess_tick_counts_half():
    sure = mastery.final([Obs(0, True)])
    guessed = mastery.final([Obs(0, True, is_guess=True)])
    assert mastery.DEFAULT.p0 < guessed < sure
