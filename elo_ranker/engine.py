import asyncio
import time
from typing import List, Dict, Any, Optional, Callable, Awaitable

from .config import Config
from .db import Database
from .elo import update_elo
from .judge import JevJudge, JudgeResult
from .matchmaker import SwissMatchmaker
from .reporter import TerminalReporter

class TournamentEngine:
    def __init__(
        self,
        config: Config,
        db: Optional[Database] = None,
        judge: Optional[JevJudge] = None,
        matchmaker: Optional[SwissMatchmaker] = None,
        reporter: Optional[TerminalReporter] = None,
        event_callback: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None
    ):
        self.config = config
        self.db = db or Database(config.db_path)
        self.judge = judge or JevJudge(api_key=config.api_key, model=config.model)
        self.matchmaker = matchmaker or SwissMatchmaker(
            stability_threshold=config.convergence_stability_threshold,
            min_rounds=config.min_rounds,
            max_rounds=config.max_rounds
        )
        self.reporter = reporter or TerminalReporter()
        self.event_callback = event_callback
        self.semaphore = asyncio.Semaphore(config.concurrency)
        self.match_counter = 0

    async def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if self.event_callback:
            try:
                res = self.event_callback(event_type, data)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    async def _execute_single_match(
        self,
        round_num: int,
        item_a: Dict[str, Any],
        item_b: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Runs a single match through the judge with concurrency throttling and updates DB."""
        async with self.semaphore:
            self.match_counter += 1
            current_match_idx = self.match_counter

            # Query the judge
            result: JudgeResult = await self.judge.judge_pair(item_a, item_b, round_num=round_num)

            # Determine score for item_a
            winner_id = result.winner_id
            if winner_id == str(item_a["id"]):
                score_a = 1.0
            elif winner_id == str(item_b["id"]):
                score_a = 0.0
            else:
                score_a = 0.5

            # Calculate new Elo ratings
            ra_before = item_a.get("elo", self.config.default_elo)
            rb_before = item_b.get("elo", self.config.default_elo)
            ra_after, rb_after, delta_a, delta_b = update_elo(
                rating_a=ra_before,
                rating_b=rb_before,
                score_a=score_a,
                matches_a=item_a.get("matches_count", 0),
                matches_b=item_b.get("matches_count", 0),
                base_k=self.config.base_k_factor,
                min_k=self.config.min_k_factor
            )

            # Record in database atomically
            self.db.record_match(
                round_num=round_num,
                item_a_id=str(item_a["id"]),
                item_b_id=str(item_b["id"]),
                winner_id=winner_id,
                reason=result.reason,
                confidence=result.confidence,
                elo_a_before=ra_before,
                elo_b_before=rb_before,
                elo_a_after=ra_after,
                elo_b_after=rb_after,
                delta_a=delta_a,
                delta_b=delta_b,
                latency_ms=result.latency_ms
            )

            # Live UI log
            self.reporter.log_match(
                match_idx=current_match_idx,
                round_num=round_num,
                item_a=item_a,
                item_b=item_b,
                winner_id=winner_id,
                reason=result.reason,
                delta_a=delta_a,
                delta_b=delta_b,
                new_elo_a=ra_after,
                new_elo_b=rb_after,
                latency_ms=result.latency_ms
            )

            # Broadcast event to WebSockets
            await self._emit("match_complete", {
                "match_idx": current_match_idx,
                "round_num": round_num,
                "item_a": {
                    "id": str(item_a["id"]),
                    "title": item_a.get("title", "Item A"),
                    "content": item_a.get("content", ""),
                    "elo_before": ra_before,
                    "elo_after": ra_after,
                    "delta": delta_a
                },
                "item_b": {
                    "id": str(item_b["id"]),
                    "title": item_b.get("title", "Item B"),
                    "content": item_b.get("content", ""),
                    "elo_before": rb_before,
                    "elo_after": rb_after,
                    "delta": delta_b
                },
                "winner_id": winner_id,
                "winner_title": item_a.get("title") if winner_id == str(item_a["id"]) else item_b.get("title"),
                "reason": result.reason,
                "confidence": result.confidence,
                "latency_ms": result.latency_ms,
                "current_leaderboard": self.db.get_leaderboard(limit=12)
            })

            return {
                "match_id": current_match_idx,
                "winner_id": winner_id,
                "latency_ms": result.latency_ms
            }

    async def run_round(self, round_num: int) -> int:
        """Runs one full Swiss round with concurrent match resolution."""
        items = self.db.get_items()
        played_pairs = self.db.get_played_pairs()

        pairings = self.matchmaker.generate_pairings(items, played_pairs, round_num=round_num)
        if not pairings:
            return 0

        # Run pairings concurrently
        tasks = [
            self._execute_single_match(round_num, pair[0], pair[1])
            for pair in pairings
        ]
        await asyncio.gather(*tasks)
        return len(pairings)

    async def run_tournament(
        self,
        dataset_name: str,
        items: List[Dict[str, Any]],
        reset_db: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Executes the full tournament until convergence or maximum rounds limit.
        """
        # 1. Initialize dataset in database
        self.db.seed_items(items, default_elo=self.config.default_elo, reset=reset_db)
        initial_items = self.db.get_items()

        # 2. Print initial visual banner
        self.reporter.print_banner(
            dataset_name=dataset_name,
            item_count=len(initial_items),
            model=self.config.model,
            concurrency=self.config.concurrency
        )

        await self._emit("tournament_start", {
            "dataset_name": dataset_name,
            "item_count": len(initial_items),
            "model": self.config.model,
            "concurrency": self.config.concurrency,
            "max_rounds": self.config.max_rounds,
            "initial_leaderboard": self.db.get_leaderboard(limit=12)
        })

        start_time = time.perf_counter()
        round_num = 1

        async with self.judge:
            while round_num <= self.config.max_rounds:
                await self._emit("round_start", {
                    "round_num": round_num,
                    "max_rounds": self.config.max_rounds
                })

                matches_played = await self.run_round(round_num)
                if matches_played == 0:
                    break

                current_items = self.db.get_items()
                is_converged, avg_shift, status_msg = self.matchmaker.check_convergence(
                    current_items,
                    round_num
                )

                self.reporter.print_round_summary(round_num, matches_played, avg_shift, status_msg)
                self.reporter.print_leaderboard(current_items, title=f"LEADERBOARD AFTER ROUND {round_num}", limit=8)

                await self._emit("round_complete", {
                    "round_num": round_num,
                    "matches_played": matches_played,
                    "avg_shift": avg_shift,
                    "is_converged": is_converged,
                    "status_msg": status_msg,
                    "leaderboard": self.db.get_leaderboard(limit=15)
                })

                if is_converged:
                    print(f"\n🎯 [CONVERGENCE ACHIEVED] {status_msg}\n")
                    break

                round_num += 1

        total_time = time.perf_counter() - start_time
        final_items = self.db.get_items()
        stats = self.db.get_tournament_stats()

        matches_per_sec = stats["total_matches"] / total_time if total_time > 0 else 0

        print("=" * 80)
        print(f"🏁 TOURNAMENT FINAL SUMMARY")
        print(f"  • Total Matches Played: {stats['total_matches']}")
        print(f"  • Total Wall Time:      {total_time:.2f}s")
        print(f"  • Throughput:           {matches_per_sec:.1f} matches/sec")
        print(f"  • Average Model Latency:{stats['avg_latency_ms']}ms")
        print("=" * 80)

        self.reporter.print_leaderboard(final_items, title="🏆 FINAL DEFINITIVE ELO RANKINGS", limit=15)

        await self._emit("tournament_complete", {
            "total_matches": stats["total_matches"],
            "total_time": round(total_time, 2),
            "matches_per_sec": round(matches_per_sec, 1),
            "avg_latency_ms": stats["avg_latency_ms"],
            "final_leaderboard": self.db.get_leaderboard(limit=20)
        })

        return final_items
