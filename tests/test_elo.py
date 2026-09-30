import pytest
from elo_ranker.elo import calculate_expected_score, get_dynamic_k_factor, update_elo

def test_expected_score_equal():
    score = calculate_expected_score(1200.0, 1200.0)
    assert pytest.approx(score, 0.001) == 0.5

def test_expected_score_dominant():
    score_favored = calculate_expected_score(1600.0, 1200.0)
    score_underdog = calculate_expected_score(1200.0, 1600.0)
    assert score_favored > 0.9
    assert score_underdog < 0.1
    assert pytest.approx(score_favored + score_underdog, 0.001) == 1.0

def test_dynamic_k_factor():
    k_early = get_dynamic_k_factor(2, base_k=32.0, min_k=16.0)
    k_mid = get_dynamic_k_factor(8, base_k=32.0, min_k=16.0)
    k_late = get_dynamic_k_factor(20, base_k=32.0, min_k=16.0)
    assert k_early == 48.0
    assert k_mid == 32.0
    assert k_late == 24.0

def test_update_elo_win():
    new_a, new_b, delta_a, delta_b = update_elo(
        rating_a=1200.0,
        rating_b=1200.0,
        score_a=1.0,
        matches_a=10,
        matches_b=10,
        base_k=32.0
    )
    assert new_a > 1200.0
    assert new_b < 1200.0
    assert delta_a == 16.0
    assert delta_b == -16.0
    assert delta_a == -delta_b

def test_update_elo_tie():
    new_a, new_b, delta_a, delta_b = update_elo(
        rating_a=1200.0,
        rating_b=1200.0,
        score_a=0.5,
        matches_a=10,
        matches_b=10,
        base_k=32.0
    )
    assert new_a == 1200.0
    assert new_b == 1200.0
    assert delta_a == 0.0
    assert delta_b == 0.0
