import time
import random
import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Optional
from typesafe_sdk import AsyncTypeSafeClient, Choice

@dataclass
class JudgeResult:
    winner_id: str
    loser_id: str
    reason: str
    confidence: float
    probabilities: Dict[str, float]
    latency_ms: float
    raw_winner_choice: str  # "A" or "B"

class JevJudge:
    def __init__(
        self,
        api_key: str,
        model: str = "jev-latest",
        domain_criteria: Optional[Dict[str, str]] = None,
        instructions: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.client: Optional[AsyncTypeSafeClient] = None
        
        # Customizable evaluation criteria per domain
        self.instructions = instructions or (
            "Evaluate Candidate A and Candidate B thoroughly. Compare them on clarity, creativity, "
            "execution quality, and overall impact. Declare which candidate is superior."
        )
        self.domain_criteria = domain_criteria or {
            "execution_and_craft": "Superior execution, craft, and precision",
            "creativity_and_originality": "More innovative, novel, and compelling concept",
            "clarity_and_structure": "Clearer structure, coherence, and flow",
            "emotional_and_rhetorical_impact": "Stronger resonance, persuasion, and memorable impact",
            "conciseness_and_punch": "More concise, punchy, and engaging delivery"
        }

    async def __aenter__(self):
        self.client = AsyncTypeSafeClient(api_key=self.api_key)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
            self.client = None

    async def judge_pair(
        self,
        item_a: Dict[str, Any],
        item_b: Dict[str, Any],
        round_num: int = 1,
        retries: int = 3
    ) -> JudgeResult:
        """
        Asynchronously compares two items using Jev System One.
        Applies positional randomization to eliminate presentation order bias.
        """
        if not self.client:
            raise RuntimeError("JevJudge must be used within an 'async with' context.")

        # Mitigate positional bias: 50% chance of swapping A and B presentation
        swapped = random.random() < 0.5
        first = item_b if swapped else item_a
        second = item_a if swapped else item_b

        state_prompt = (
            f"### CANDIDATE A: {first.get('title', 'Item A')}\n"
            f"{first.get('content', '')}\n\n"
            f"----------------------------------------\n\n"
            f"### CANDIDATE B: {second.get('title', 'Item B')}\n"
            f"{second.get('content', '')}"
        )

        questions = {
            "winner": Choice(
                instructions=self.instructions,
                criteria={
                    "A": "Candidate A is superior",
                    "B": "Candidate B is superior"
                }
            ),
            "reason": Choice(
                instructions="What is the primary factor that makes the winning candidate superior?",
                criteria=self.domain_criteria
            )
        }

        start_time = time.perf_counter()
        last_exception = None

        for attempt in range(retries):
            try:
                response = await self.client.system_one(
                    state=state_prompt,
                    questions=questions,
                    model=self.model,
                    timeout=15.0
                )
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                winner_ans = response.choices.get("winner")
                reason_ans = response.choices.get("reason")

                raw_choice = winner_ans.choice if winner_ans else "A"
                confidence = float(winner_ans.confidence) if winner_ans else 0.5
                probs = dict(winner_ans.probabilities) if winner_ans and winner_ans.probabilities else {"A": 0.5, "B": 0.5}
                reason_code = reason_ans.choice if reason_ans else "execution_and_craft"

                # Human-readable reason explanation
                reason_text = self.domain_criteria.get(reason_code, reason_code.replace("_", " ").title())

                # Map raw choice ('A' or 'B') back to original items taking swap into account
                if raw_choice == "A":
                    winner = first
                    loser = second
                else:
                    winner = second
                    loser = first

                return JudgeResult(
                    winner_id=str(winner["id"]),
                    loser_id=str(loser["id"]),
                    reason=reason_text,
                    confidence=confidence,
                    probabilities=probs,
                    latency_ms=round(latency_ms, 1),
                    raw_winner_choice=raw_choice
                )

            except Exception as e:
                last_exception = e
                wait_time = (2 ** attempt) * 0.25
                await asyncio.sleep(wait_time)

        raise RuntimeError(f"Failed to judge pair {item_a['id']} vs {item_b['id']} after {retries} attempts: {last_exception}")
