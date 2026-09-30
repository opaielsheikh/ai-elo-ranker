import pytest
from elo_ranker.db import Database
from elo_ranker.trueskill_engine import update_trueskill_multi

def test_database_initialization_and_seeding():
    db = Database(":memory:")
    items = [
        {"id": "1", "title": "Poem 1", "content": "Roses are red", "metadata": {"author": "Author A"}},
        {"id": "2", "title": "Poem 2", "content": "Violets are blue", "metadata": {"author": "Author B"}}
    ]
    db.seed_items(items, default_elo=1200.0, reset=True)
    fetched = db.get_items()
    assert len(fetched) == 2
    assert fetched[0]["elo"] == 1200.0
    assert fetched[0]["mu"] == 25.0
    assert fetched[0]["sigma"] > 8.0

def test_database_1v1_match_recording():
    db = Database(":memory:")
    items = [
        {"id": "1", "title": "A", "content": "text A"},
        {"id": "2", "title": "B", "content": "text B"}
    ]
    db.seed_items(items, reset=True)

    db.record_match(
        round_num=1,
        item_a_id="1",
        item_b_id="2",
        winner_id="1",
        reason="Superior rhyme",
        confidence=0.9,
        elo_a_before=1200.0,
        elo_b_before=1200.0,
        elo_a_after=1224.0,
        elo_b_after=1176.0,
        delta_a=24.0,
        delta_b=-24.0,
        latency_ms=20.0
    )

    history = db.get_match_history()
    assert len(history) == 1
    assert history[0]["winner_id"] == "1"

    leaderboard = db.get_leaderboard()
    assert leaderboard[0]["id"] == "1"
    assert leaderboard[0]["elo"] == 1224.0
    assert leaderboard[0]["wins"] == 1

def test_database_cohort_match_recording():
    db = Database(":memory:")
    items = [
        {"id": "1", "title": "P1", "mu": 25.0, "sigma": 8.333},
        {"id": "2", "title": "P2", "mu": 25.0, "sigma": 8.333},
        {"id": "3", "title": "P3", "mu": 25.0, "sigma": 8.333}
    ]
    db.seed_items(items, reset=True)

    updated = update_trueskill_multi(items, ranks=[1, 2, 3])
    db.record_cohort_match(
        round_num=1,
        cohort_results=updated,
        winner_id="1",
        reason="Dominant market size",
        confidence=0.95,
        latency_ms=25.0
    )

    stats = db.get_tournament_stats()
    assert stats["total_matches"] == 1
    assert stats["total_cohort_matches"] == 1

    leaderboard = db.get_leaderboard(sort_by="ordinal")
    assert leaderboard[0]["id"] == "1"
    assert leaderboard[0]["wins"] == 1
    assert leaderboard[0]["mu"] > 25.0
