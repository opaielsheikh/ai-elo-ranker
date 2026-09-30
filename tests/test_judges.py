import pytest
import asyncio
import json
import httpx
from unittest.mock import AsyncMock, patch

from elo_ranker.judge import (
    MockJudge,
    OpenAICompatibleJudge,
    EnsembleJudge,
    JudgeResult,
    MultiJudgeResult
)

@pytest.mark.asyncio
async def test_mock_judge_pair():
    judge = MockJudge(simulated_delay_ms=0)
    item_a = {"id": "p1", "title": "Poem A", "content": "Short verse"}
    item_b = {"id": "p2", "title": "Poem B", "content": "A very elaborate and extensive sonnet with deep rhythmic meters"}
    
    result = await judge.judge_pair(item_a, item_b)
    assert isinstance(result, JudgeResult)
    assert result.winner_id in ["p1", "p2"]
    assert result.confidence >= 0.5
    assert len(result.reason) > 0

@pytest.mark.asyncio
async def test_mock_judge_multi():
    judge = MockJudge(simulated_delay_ms=0)
    items = [
        {"id": "c1", "title": "C1", "content": "Short"},
        {"id": "c2", "title": "C2", "content": "A much longer and comprehensive startup pitch describing a multi-billion dollar market"},
        {"id": "c3", "title": "C3", "content": "Medium length text"}
    ]
    
    result = await judge.judge_multi(items)
    assert isinstance(result, MultiJudgeResult)
    assert len(result.ranked_ids) == 3
    assert result.ranks == [1, 2, 3]
    assert result.winner_id == result.ranked_ids[0]

@pytest.mark.asyncio
async def test_openai_compatible_judge_pair_mocked():
    judge = OpenAICompatibleJudge(
        base_url="http://localhost:11434/v1",
        model="qwen2.5:7b"
    )

    fake_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "winner": "A",
                        "reason": "Superior clarity and narrative punch",
                        "confidence": 0.88
                    })
                }
            }
        ]
    }

    mock_resp = httpx.Response(
        status_code=200,
        json=fake_response,
        request=httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    )

    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_resp)):
        item_a = {"id": "item_1", "title": "Pitch 1", "content": "Content 1"}
        item_b = {"id": "item_2", "title": "Pitch 2", "content": "Content 2"}

        res = await judge.judge_pair(item_a, item_b)
        assert res.winner_id in ["item_1", "item_2"]
        assert "Superior" in res.reason
        assert res.confidence == 0.88

@pytest.mark.asyncio
async def test_openai_compatible_judge_multi_mocked():
    judge = OpenAICompatibleJudge(
        base_url="http://localhost:11434/v1",
        model="gemma2:9b"
    )

    # Return valid multi-candidate ranking
    fake_response = {
        "choices": [
            {
                "message": {
                    "content": '```json\n{"ranking": ["A", "C", "B"], "winner_reason": "Extraordinary lyrical depth", "confidence": 0.92}\n```'
                }
            }
        ]
    }

    mock_resp = httpx.Response(
        status_code=200,
        json=fake_response,
        request=httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    )

    with patch.object(httpx.AsyncClient, "post", new=AsyncMock(return_value=mock_resp)):
        items = [
            {"id": "1", "title": "T1", "content": "C1"},
            {"id": "2", "title": "T2", "content": "C2"},
            {"id": "3", "title": "T3", "content": "C3"}
        ]
        res = await judge.judge_multi(items)
        assert len(res.ranked_ids) == 3
        assert res.ranks == [1, 2, 3]
        assert res.confidence == 0.92
        assert "lyrical" in res.reason.lower()

@pytest.mark.asyncio
async def test_ensemble_judge_pair_and_multi():
    judge_1 = MockJudge(simulated_delay_ms=0)
    judge_2 = MockJudge(simulated_delay_ms=0)
    committee = EnsembleJudge(judges=[judge_1, judge_2])

    items = [
        {"id": "1", "title": "Item 1", "content": "Very extensive detailed analysis"},
        {"id": "2", "title": "Item 2", "content": "Short"}
    ]

    pair_res = await committee.judge_pair(items[0], items[1])
    assert pair_res.winner_id in ["1", "2"]
    assert "Ensemble" in pair_res.model_name

    multi_res = await committee.judge_multi(items)
    assert len(multi_res.ranked_ids) == 2
    assert multi_res.winner_id in ["1", "2"]
