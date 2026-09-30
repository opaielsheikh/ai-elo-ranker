import pytest
from elo_ranker.trueskill_engine import (
    DEFAULT_MU,
    DEFAULT_SIGMA,
    calculate_ordinal,
    to_scaled_rating,
    update_trueskill_multi,
    update_trueskill_pair
)

def test_default_ratings():
    assert DEFAULT_MU == 25.0
    assert pytest.approx(DEFAULT_SIGMA, 0.001) == 8.3333

def test_calculate_ordinal():
    # mu - 3 * sigma
    ord_val = calculate_ordinal(25.0, 8.0)
    assert ord_val == 1.0

def test_to_scaled_rating():
    # default mu=25.0 maps to 1200.0
    scaled = to_scaled_rating(25.0)
    assert scaled == 1200.0
    scaled_higher = to_scaled_rating(26.0)
    assert scaled_higher > 1200.0

def test_update_trueskill_multi_ranking():
    candidates = [
        {"id": "cand_1", "mu": 25.0, "sigma": 8.333},
        {"id": "cand_2", "mu": 25.0, "sigma": 8.333},
        {"id": "cand_3", "mu": 25.0, "sigma": 8.333}
    ]
    # Ranks: cand_1 1st, cand_2 2nd, cand_3 3rd
    ranks = [1, 2, 3]
    results = update_trueskill_multi(candidates, ranks)

    assert len(results) == 3
    r1, r2, r3 = results[0], results[1], results[2]

    # Winner mu increases
    assert r1["new_mu"] > 25.0
    assert r1["delta_mu"] > 0

    # 3rd place mu decreases
    assert r3["new_mu"] < 25.0
    assert r3["delta_mu"] < 0

    # Relative skill ordering preserved
    assert r1["new_mu"] > r2["new_mu"] > r3["new_mu"]

    # All uncertainties (sigma) decrease after match resolution!
    assert r1["new_sigma"] < 8.333
    assert r2["new_sigma"] < 8.333
    assert r3["new_sigma"] < 8.333

def test_update_trueskill_pair():
    mu_a, sig_a, d_a, mu_b, sig_b, d_b = update_trueskill_pair(25.0, 8.333, 25.0, 8.333, 1.0)
    assert mu_a > 25.0
    assert mu_b < 25.0
    assert d_a > 0
    assert d_b < 0
    assert sig_a < 8.333
    assert sig_b < 8.333
