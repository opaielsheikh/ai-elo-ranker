import pytest
from elo_ranker.matchmaker import SwissMatchmaker

def test_generate_pairings_1v1():
    mm = SwissMatchmaker(min_rounds=2, max_rounds=5)
    items = [
        {"id": "1", "elo": 1250.0, "matches_count": 1},
        {"id": "2", "elo": 1240.0, "matches_count": 1},
        {"id": "3", "elo": 1160.0, "matches_count": 1},
        {"id": "4", "elo": 1150.0, "matches_count": 1}
    ]

    # Round 2: items with adjacent Elo should be paired
    pairings = mm.generate_pairings(items, played_pairs=set(), round_num=2)
    assert len(pairings) == 2
    # Item 1 and Item 2 should face each other
    assert pairings[0][0]["id"] == "1"
    assert pairings[0][1]["id"] == "2"
    # Item 3 and Item 4 should face each other
    assert pairings[1][0]["id"] == "3"
    assert pairings[1][1]["id"] == "4"

def test_generate_cohorts_trueskill():
    mm = SwissMatchmaker(min_rounds=2, max_rounds=5)
    items = [
        {"id": f"item_{i}", "mu": 25.0 + i, "sigma": 8.0} for i in range(6)
    ]

    cohorts = mm.generate_cohorts(items, cohort_size=3, round_num=1)
    assert len(cohorts) == 2
    assert len(cohorts[0]) == 3
    assert len(cohorts[1]) == 3

def test_generate_cohorts_leftovers():
    mm = SwissMatchmaker(min_rounds=2, max_rounds=5)
    # 7 items with cohort_size 3 -> two cohorts of 3 and 4
    items = [
        {"id": f"item_{i}", "mu": 25.0 + i, "sigma": 8.0} for i in range(7)
    ]
    cohorts = mm.generate_cohorts(items, cohort_size=3, round_num=2)
    assert len(cohorts) == 2
    total_assigned = sum(len(c) for c in cohorts)
    assert total_assigned == 7

def test_check_convergence():
    mm = SwissMatchmaker(stability_threshold=0.5, min_rounds=2, max_rounds=10)
    items = [
        {"id": "1", "elo": 1300.0},
        {"id": "2", "elo": 1200.0},
        {"id": "3", "elo": 1100.0}
    ]

    # Round 1
    converged, shift, msg = mm.check_convergence(items, current_round=1)
    assert not converged

    # Round 2: same order -> shift should be 0.0 -> convergence reached!
    converged, shift, msg = mm.check_convergence(items, current_round=2)
    assert converged
    assert shift == 0.0
