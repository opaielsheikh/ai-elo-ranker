import time
import random
import asyncio
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
import httpx

try:
    from typesafe_sdk import AsyncTypeSafeClient, Choice
except ImportError:
    AsyncTypeSafeClient = None
    Choice = None


@dataclass
class JudgeResult:
    winner_id: str
    loser_id: str
    reason: str
    confidence: float
    probabilities: Dict[str, float]
    latency_ms: float
    raw_winner_choice: str  # "A" or "B"
    model_name: str = "jev-latest"


@dataclass
class MultiJudgeResult:
    ranked_ids: List[str]  # In order: 1st, 2nd, 3rd, ...
    ranks: List[int]       # 1-indexed ranks, e.g. [1, 2, 3]
    winner_id: str
    reason: str
    confidence: float
    latency_ms: float
    model_name: str
    item_rankings: List[Dict[str, Any]] = field(default_factory=list)


class BaseJudge(ABC):
    """Abstract base class for all LLM and algorithmic judges."""

    def __init__(
        self,
        domain_criteria: Optional[Dict[str, str]] = None,
        instructions: Optional[str] = None,
    ):
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
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    @abstractmethod
    async def judge_pair(
        self,
        item_a: Dict[str, Any],
        item_b: Dict[str, Any],
        round_num: int = 1,
        retries: int = 3
    ) -> JudgeResult:
        """Pairwise comparison for 1v1 Elo."""
        pass

    @abstractmethod
    async def judge_multi(
        self,
        items: List[Dict[str, Any]],
        round_num: int = 1,
        retries: int = 3
    ) -> MultiJudgeResult:
        """N-way comparison for TrueSkill / OpenSkill cohorts."""
        pass


class JevJudge(BaseJudge):
    """TypeSafe Jev System One Judge with position bias mitigation."""

    def __init__(
        self,
        api_key: str,
        model: str = "jev-latest",
        domain_criteria: Optional[Dict[str, str]] = None,
        instructions: Optional[str] = None,
    ):
        super().__init__(domain_criteria=domain_criteria, instructions=instructions)
        self.api_key = api_key
        self.model = model
        self.client: Optional[Any] = None

    async def __aenter__(self):
        if AsyncTypeSafeClient is None:
            raise ImportError("typesafe_sdk is required for JevJudge.")
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
        if not self.client:
            raise RuntimeError("JevJudge must be used within an 'async with' context or client initialized.")

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

                reason_text = self.domain_criteria.get(reason_code, reason_code.replace("_", " ").title())

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
                    raw_winner_choice=raw_choice,
                    model_name=self.model
                )

            except Exception as e:
                last_exception = e
                wait_time = (2 ** attempt) * 0.25
                await asyncio.sleep(wait_time)

        raise RuntimeError(f"Failed to judge pair {item_a['id']} vs {item_b['id']} after {retries} attempts: {last_exception}")

    async def judge_multi(
        self,
        items: List[Dict[str, Any]],
        round_num: int = 1,
        retries: int = 3
    ) -> MultiJudgeResult:
        """
        Multi-candidate ranking for Jev: compares candidates pairwise in a mini round-robin
        or uses tournament reduction to produce complete 1st-to-Nth ordering.
        """
        start_time = time.perf_counter()
        scores = {str(item["id"]): 0 for item in items}
        last_reason = "Superior execution and craft"
        confidences = []

        # Run pairwise comparisons among the cohort
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                res = await self.judge_pair(items[i], items[j], round_num=round_num, retries=retries)
                scores[res.winner_id] += 1
                last_reason = res.reason
                confidences.append(res.confidence)

        # Sort items by score descending
        sorted_items = sorted(items, key=lambda x: scores[str(x["id"])], reverse=True)
        ranked_ids = [str(x["id"]) for x in sorted_items]
        ranks = list(range(1, len(items) + 1))
        
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.85

        item_rankings = [
            {"id": str(x["id"]), "title": x.get("title", f"Item {x['id']}"), "rank": rank, "wins_in_cohort": scores[str(x["id"])]}
            for rank, x in enumerate(sorted_items, 1)
        ]

        return MultiJudgeResult(
            ranked_ids=ranked_ids,
            ranks=ranks,
            winner_id=ranked_ids[0],
            reason=f"Decisive cohort winner: {last_reason}",
            confidence=round(avg_confidence, 2),
            latency_ms=round(latency_ms, 1),
            model_name=self.model,
            item_rankings=item_rankings
        )


class OpenAICompatibleJudge(BaseJudge):
    """
    Open-weight and local model judge supporting any OpenAI-compatible API:
    Ollama, vLLM, llama.cpp, LM Studio, OpenJev, Laya, Qwen 2.5, Gemma 2, etc.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "ollama",
        model: str = "qwen2.5:7b",
        domain_criteria: Optional[Dict[str, str]] = None,
        instructions: Optional[str] = None,
        timeout: float = 30.0
    ):
        super().__init__(domain_criteria=domain_criteria, instructions=instructions)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "none"
        self.model = model
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=self.timeout
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
            self.client = None

    def _clean_json_response(self, text: str) -> Dict[str, Any]:
        """Extracts JSON object from model output text, handling Markdown code fences."""
        text = text.strip()
        # Look for ```json ... ``` or { ... }
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
            
        return json.loads(text)

    async def judge_pair(
        self,
        item_a: Dict[str, Any],
        item_b: Dict[str, Any],
        round_num: int = 1,
        retries: int = 3
    ) -> JudgeResult:
        if not self.client:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=self.timeout
            )

        # Mitigate positional bias by 50% random swap
        swapped = random.random() < 0.5
        first = item_b if swapped else item_a
        second = item_a if swapped else item_b

        prompt = (
            f"You are an impartial, expert tournament judge.\n"
            f"{self.instructions}\n\n"
            f"Evaluation criteria to consider:\n"
            + "\n".join([f"- {k}: {v}" for k, v in self.domain_criteria.items()]) + "\n\n"
            f"### CANDIDATE A: {first.get('title', 'Item A')}\n"
            f"{first.get('content', '')}\n\n"
            f"----------------------------------------\n\n"
            f"### CANDIDATE B: {second.get('title', 'Item B')}\n"
            f"{second.get('content', '')}\n\n"
            f"Return a strict JSON object with NO extra text:\n"
            f'{{"winner": "A" or "B", "reason": "<concise rationale under 20 words>", "confidence": <float between 0.5 and 1.0>}}'
        )

        start_time = time.perf_counter()
        last_exception = None

        for attempt in range(retries):
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a professional tournament judge. Always output valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1
                }

                resp = await self.client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_text = data["choices"][0]["message"]["content"]
                parsed = self._clean_json_response(raw_text)

                raw_choice = str(parsed.get("winner", "A")).strip().upper()
                if raw_choice not in ("A", "B"):
                    raw_choice = "A"

                reason = str(parsed.get("reason", "Superior quality and execution")).strip()
                confidence = float(parsed.get("confidence", 0.8))
                confidence = max(0.5, min(1.0, confidence))

                latency_ms = (time.perf_counter() - start_time) * 1000.0

                winner = second if (raw_choice == "B" and not swapped) or (raw_choice == "A" and swapped) else first
                loser = first if winner == second else second

                return JudgeResult(
                    winner_id=str(winner["id"]),
                    loser_id=str(loser["id"]),
                    reason=reason,
                    confidence=confidence,
                    probabilities={"A": confidence if raw_choice == "A" else 1 - confidence, "B": confidence if raw_choice == "B" else 1 - confidence},
                    latency_ms=round(latency_ms, 1),
                    raw_winner_choice=raw_choice,
                    model_name=self.model
                )

            except Exception as e:
                last_exception = e
                if isinstance(e, httpx.ConnectError):
                    raise RuntimeError(
                        f"Could not connect to {self.base_url}. Is Ollama or your local model runner running? "
                        f"Start it with 'ollama serve' or 'ollama run {self.model}', or use OpenRouter/OpenAI endpoint."
                    )
                await asyncio.sleep((2 ** attempt) * 0.3)

        raise RuntimeError(f"OpenAICompatibleJudge ({self.model}) failed after {retries} attempts: {last_exception}")


    async def judge_multi(
        self,
        items: List[Dict[str, Any]],
        round_num: int = 1,
        retries: int = 3
    ) -> MultiJudgeResult:
        if not self.client:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=self.timeout
            )

        # Shuffle candidates to prevent positional bias
        shuffled_indices = list(range(len(items)))
        random.shuffle(shuffled_indices)
        shuffled_items = [items[i] for i in shuffled_indices]

        # Labels: A, B, C, D...
        labels = [chr(65 + i) for i in range(len(shuffled_items))]
        label_to_item = {labels[i]: shuffled_items[i] for i in range(len(shuffled_items))}

        candidates_text = ""
        for lbl, it in label_to_item.items():
            item_title = it.get('title', f"Item {it['id']}")
            candidates_text += f"### CANDIDATE {lbl}: {item_title}\n{it.get('content', '')}\n\n"

        prompt = (
            f"You are an impartial, expert tournament judge.\n"
            f"Evaluate the following {len(items)} candidates and rank them strictly from best to worst.\n"
            f"{self.instructions}\n\n"
            f"{candidates_text}"
            f"Return a strict JSON object with NO markdown formatting or preamble:\n"
            f'{{"ranking": {json.dumps(labels)}, "winner_reason": "<why the 1st place candidate won>", "confidence": <float between 0.5 and 1.0>}}'
        )

        start_time = time.perf_counter()
        last_exception = None

        for attempt in range(retries):
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a professional tournament judge. Always respond with strict JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1
                }

                resp = await self.client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_text = data["choices"][0]["message"]["content"]
                parsed = self._clean_json_response(raw_text)

                raw_ranking = parsed.get("ranking", labels)
                if not isinstance(raw_ranking, list):
                    raw_ranking = labels

                # Filter and ensure all labels are present
                ordered_labels = [lbl for lbl in raw_ranking if lbl in label_to_item]
                for lbl in labels:
                    if lbl not in ordered_labels:
                        ordered_labels.append(lbl)

                ranked_items = [label_to_item[lbl] for lbl in ordered_labels]
                ranked_ids = [str(x["id"]) for x in ranked_items]
                ranks = list(range(1, len(ranked_items) + 1))

                reason = str(parsed.get("winner_reason", "Superior execution, coherence, and impact")).strip()
                confidence = float(parsed.get("confidence", 0.85))
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                item_rankings = [
                    {"id": str(x["id"]), "title": x.get("title", f"Item {x['id']}"), "rank": rank, "label": ordered_labels[rank - 1]}
                    for rank, x in enumerate(ranked_items, 1)
                ]

                return MultiJudgeResult(
                    ranked_ids=ranked_ids,
                    ranks=ranks,
                    winner_id=ranked_ids[0],
                    reason=reason,
                    confidence=confidence,
                    latency_ms=round(latency_ms, 1),
                    model_name=self.model,
                    item_rankings=item_rankings
                )

            except Exception as e:
                last_exception = e
                if isinstance(e, httpx.ConnectError):
                    raise RuntimeError(
                        f"Could not connect to {self.base_url}. Is Ollama or your local model runner running? "
                        f"Start it with 'ollama serve' or 'ollama run {self.model}', or use OpenRouter/OpenAI endpoint."
                    )
                await asyncio.sleep((2 ** attempt) * 0.3)

        raise RuntimeError(f"OpenAICompatibleJudge multi-evaluation ({self.model}) failed: {last_exception}")



class EnsembleJudge(BaseJudge):
    """
    Committee / Ensemble Judge that queries multiple LLMs concurrently
    and aggregates verdicts via majority vote (1v1) or Borda count (multi-way).
    """

    def __init__(
        self,
        judges: List[BaseJudge],
        domain_criteria: Optional[Dict[str, str]] = None,
        instructions: Optional[str] = None
    ):
        super().__init__(domain_criteria=domain_criteria, instructions=instructions)
        if not judges:
            raise ValueError("EnsembleJudge requires at least one judge.")
        self.judges = judges
        self.model_name = f"Ensemble({', '.join([getattr(j, 'model', getattr(j, 'model_name', 'judge')) for j in judges])})"

    async def __aenter__(self):
        for j in self.judges:
            await j.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for j in self.judges:
            await j.__aexit__(exc_type, exc_val, exc_tb)

    async def judge_pair(
        self,
        item_a: Dict[str, Any],
        item_b: Dict[str, Any],
        round_num: int = 1,
        retries: int = 3
    ) -> JudgeResult:
        start_time = time.perf_counter()
        tasks = [j.judge_pair(item_a, item_b, round_num=round_num, retries=retries) for j in self.judges]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results: List[JudgeResult] = [r for r in results if isinstance(r, JudgeResult)]
        if not valid_results:
            errors = [str(r) for r in results if isinstance(r, Exception)]
            raise RuntimeError(f"All judges in committee failed: {errors}")

        # Tally votes
        votes: Dict[str, int] = {str(item_a["id"]): 0, str(item_b["id"]): 0}
        reasons: List[str] = []
        confidences: List[float] = []

        for r in valid_results:
            votes[r.winner_id] = votes.get(r.winner_id, 0) + 1
            reasons.append(f"[{r.model_name}]: {r.reason}")
            confidences.append(r.confidence)

        id_a, id_b = str(item_a["id"]), str(item_b["id"])
        winner_id = id_a if votes[id_a] >= votes[id_b] else id_b
        loser_id = id_b if winner_id == id_a else id_a
        combined_reason = " | ".join(reasons)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.8
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return JudgeResult(
            winner_id=winner_id,
            loser_id=loser_id,
            reason=combined_reason,
            confidence=round(avg_confidence, 2),
            probabilities={id_a: votes[id_a] / len(valid_results), id_b: votes[id_b] / len(valid_results)},
            latency_ms=round(latency_ms, 1),
            raw_winner_choice="A" if winner_id == id_a else "B",
            model_name=self.model_name
        )

    async def judge_multi(
        self,
        items: List[Dict[str, Any]],
        round_num: int = 1,
        retries: int = 3
    ) -> MultiJudgeResult:
        start_time = time.perf_counter()
        tasks = [j.judge_multi(items, round_num=round_num, retries=retries) for j in self.judges]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results: List[MultiJudgeResult] = [r for r in results if isinstance(r, MultiJudgeResult)]
        if not valid_results:
            errors = [str(r) for r in results if isinstance(r, Exception)]
            raise RuntimeError(f"All judges in multi-committee failed: {errors}")

        # Borda Count aggregation: rank 1 gets N points, rank 2 gets N-1, etc.
        n = len(items)
        borda_scores: Dict[str, float] = {str(it["id"]): 0.0 for it in items}
        reasons: List[str] = []
        confidences: List[float] = []

        for r in valid_results:
            for pos, item_id in enumerate(r.ranked_ids):
                points = n - pos
                borda_scores[item_id] += points
            reasons.append(f"[{r.model_name}]: {r.reason}")
            confidences.append(r.confidence)

        # Sort items by total Borda score descending
        sorted_items = sorted(items, key=lambda x: borda_scores[str(x["id"])], reverse=True)
        ranked_ids = [str(x["id"]) for x in sorted_items]
        ranks = list(range(1, len(items) + 1))

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.85

        item_rankings = [
            {"id": str(x["id"]), "title": x.get("title", f"Item {x['id']}"), "rank": rank, "borda_score": borda_scores[str(x["id"])]}
            for rank, x in enumerate(sorted_items, 1)
        ]

        return MultiJudgeResult(
            ranked_ids=ranked_ids,
            ranks=ranks,
            winner_id=ranked_ids[0],
            reason=" | ".join(reasons),
            confidence=round(avg_confidence, 2),
            latency_ms=round(latency_ms, 1),
            model_name=self.model_name,
            item_rankings=item_rankings
        )


class MockJudge(BaseJudge):
    """
    Deterministic simulated judge for fast offline testing, zero-cost benchmarking,
    and mock unit tests without requiring active LLM servers.
    """

    def __init__(
        self,
        domain_criteria: Optional[Dict[str, str]] = None,
        instructions: Optional[str] = None,
        simulated_delay_ms: float = 15.0
    ):
        super().__init__(domain_criteria=domain_criteria, instructions=instructions)
        self.simulated_delay_ms = simulated_delay_ms
        self.model_name = "mock-judge"

    def _score_item(self, item: Dict[str, Any]) -> float:
        content = item.get("content", "")
        title = item.get("title", "")
        # Heuristic: length, word variety, and deterministic hash
        word_count = len(content.split())
        unique_words = len(set(content.lower().split()))
        hash_factor = (hash(str(item.get("id")) + title) % 100) / 10.0
        return (word_count * 0.5) + (unique_words * 0.8) + hash_factor

    async def judge_pair(
        self,
        item_a: Dict[str, Any],
        item_b: Dict[str, Any],
        round_num: int = 1,
        retries: int = 3
    ) -> JudgeResult:
        if self.simulated_delay_ms > 0:
            await asyncio.sleep(self.simulated_delay_ms / 1000.0)

        score_a = self._score_item(item_a)
        score_b = self._score_item(item_b)

        winner = item_a if score_a >= score_b else item_b
        loser = item_b if winner == item_a else item_a

        reasons = list(self.domain_criteria.values())
        selected_reason = reasons[hash(str(winner["id"])) % len(reasons)]

        return JudgeResult(
            winner_id=str(winner["id"]),
            loser_id=str(loser["id"]),
            reason=f"Superior {selected_reason.lower()}",
            confidence=0.88,
            probabilities={"A": 0.65, "B": 0.35},
            latency_ms=self.simulated_delay_ms,
            raw_winner_choice="A" if winner == item_a else "B",
            model_name=self.model_name
        )

    async def judge_multi(
        self,
        items: List[Dict[str, Any]],
        round_num: int = 1,
        retries: int = 3
    ) -> MultiJudgeResult:
        if self.simulated_delay_ms > 0:
            await asyncio.sleep(self.simulated_delay_ms / 1000.0)

        scored = [(self._score_item(it), it) for it in items]
        scored.sort(key=lambda x: x[0], reverse=True)

        ranked_items = [x[1] for x in scored]
        ranked_ids = [str(x["id"]) for x in ranked_items]
        ranks = list(range(1, len(items) + 1))

        reasons = list(self.domain_criteria.values())
        selected_reason = reasons[hash(ranked_ids[0]) % len(reasons)]

        item_rankings = [
            {"id": str(it["id"]), "title": it.get("title", f"Item {it['id']}"), "rank": rank, "score": round(score, 1)}
            for rank, (score, it) in enumerate(scored, 1)
        ]

        return MultiJudgeResult(
            ranked_ids=ranked_ids,
            ranks=ranks,
            winner_id=ranked_ids[0],
            reason=f"Decisive cohort winner: {selected_reason}",
            confidence=0.91,
            latency_ms=self.simulated_delay_ms,
            model_name=self.model_name,
            item_rankings=item_rankings
        )
