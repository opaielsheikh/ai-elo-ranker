import pytest
from httpx import AsyncClient, ASGITransport
from server import app

@pytest.mark.asyncio
async def test_datasets_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/datasets")
        assert response.status_code == 200
        data = response.json()
        assert "datasets" in data
        assert len(data["datasets"]) > 0

@pytest.mark.asyncio
async def test_status_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_running" in data
        assert "stats" in data

@pytest.mark.asyncio
async def test_tournament_start_and_stop():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start_payload = {
            "dataset": "startup_pitches.json",
            "mode": "trueskill",
            "cohort_size": 3,
            "judge_type": "mock",
            "concurrency": 2,
            "rounds": 1,
            "threshold": 0.5,
            "reset_db": True
        }
        res_start = await client.post("/api/tournament/start", json=start_payload)
        assert res_start.status_code == 200
        assert res_start.json()["status"] == "started"

        res_stop = await client.post("/api/tournament/stop")
        assert res_stop.status_code == 200
