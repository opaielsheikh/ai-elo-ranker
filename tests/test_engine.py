import pytest
from elo_ranker.config import Config
from elo_ranker.db import Database
from elo_ranker.judge import MockJudge
from elo_ranker.matchmaker import SwissMatchmaker
from elo_ranker.engine import TournamentEngine

@pytest.mark.asyncio
async def test_tournament_engine_elo_run():
    events_received = []

    async def test_callback(event_type: str, data: dict):
        events_received.append((event_type, data))

    config = Config(
        rating_mode="elo",
        concurrency=4,
        min_rounds=2,
        max_rounds=3,
        convergence_stability_threshold=0.5
    )

    db = Database(":memory:")
    judge = MockJudge(simulated_delay_ms=0)
    matchmaker = SwissMatchmaker(min_rounds=2, max_rounds=3)

    engine = TournamentEngine(
        config=config,
        db=db,
        judge=judge,
        matchmaker=matchmaker,
        event_callback=test_callback
    )

    sample_items = [
        {"id": "1", "title": "Stripe", "content": "Online payments infrastructure API for the internet"},
        {"id": "2", "title": "Airbnb", "content": "AirBed and breakfast for travelers"},
        {"id": "3", "title": "Dropbox", "content": "Simple file synchronization across multiple devices"},
        {"id": "4", "title": "Coinbase", "content": "Easy cryptocurrency exchange and digital wallet"}
    ]

    final_items = await engine.run_tournament(
        dataset_name="Test Pitches",
        items=sample_items,
        reset_db=True
    )

    assert len(final_items) == 4
    # Ensure matches were played and recorded
    stats = db.get_tournament_stats()
    assert stats["total_matches"] > 0

    # Ensure events were emitted
    event_types = [e[0] for e in events_received]
    assert "tournament_start" in event_types
    assert "round_start" in event_types
    assert "match_complete" in event_types
    assert "round_complete" in event_types
    assert "tournament_complete" in event_types

@pytest.mark.asyncio
async def test_tournament_engine_trueskill_run():
    events_received = []

    async def test_callback(event_type: str, data: dict):
        events_received.append((event_type, data))

    config = Config(
        rating_mode="trueskill",
        cohort_size=3,
        concurrency=4,
        min_rounds=2,
        max_rounds=2,
        convergence_stability_threshold=0.5
    )

    db = Database(":memory:")
    judge = MockJudge(simulated_delay_ms=0)
    matchmaker = SwissMatchmaker(min_rounds=2, max_rounds=2)

    engine = TournamentEngine(
        config=config,
        db=db,
        judge=judge,
        matchmaker=matchmaker,
        event_callback=test_callback
    )

    sample_items = [
        {"id": f"item_{i}", "title": f"Idea {i}", "content": f"Content of item {i} describing features and market"}
        for i in range(6)
    ]

    final_items = await engine.run_tournament(
        dataset_name="Test Trueskill Cohorts",
        items=sample_items,
        reset_db=True
    )

    assert len(final_items) == 6
    stats = db.get_tournament_stats()
    assert stats["total_cohort_matches"] > 0

    event_types = [e[0] for e in events_received]
    assert "cohort_match_complete" in event_types
    assert "tournament_complete" in event_types
