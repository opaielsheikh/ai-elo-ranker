import asyncio
import time
from typing import List, Dict, Any, Optional, Callable, Awaitable

from .config import Config
from .db import Database
from .elo import update_elo
from .trueskill_engine import update_trueskill_multi
from .judge import BaseJudge, JevJudge, JudgeResult, MultiJudgeResult
from .matchmaker import SwissMatchmaker
from .reporter import TerminalReporter

class TournamentEngine:
    def __init__(
        self,
        config: Config,
        db: Optional[Database] = None,
        judge: Optional[BaseJudge] = None,
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
        """Runs a 1v1 match through the judge with concurrency throttling and updates DB."""
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
            ra_before = float(item_a.get("elo", self.config.default_elo))
            rb_before = float(item_b.get("elo", self.config.default_elo))
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
                latency_ms=result.latency_ms,
                model_name=getattr(result, "model_name", self.config.model)
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
                "rating_mode": "elo",
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
                "model_name": getattr(result, "model_name", self.config.model),
                "current_leaderboard": self.db.get_leaderboard(limit=12)
            })

            return {
                "match_id": current_match_idx,
                "winner_id": winner_id,
                "latency_ms": result.latency_ms
            }

    async def _execute_cohort_match(
        self,
        round_num: int,
        cohort: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Runs an N-candidate TrueSkill cohort match through the judge and updates Bayesian ratings."""
        async with self.semaphore:
            self.match_counter += 1
            current_match_idx = self.match_counter

            # Query the judge for multi-candidate ranking
            result: MultiJudgeResult = await self.judge.judge_multi(cohort, round_num=round_num)

            # Order cohort in rank order returned by judge
            ranked_id_to_rank = {rid: rank for rank, rid in zip(result.ranks, result.ranked_ids)}
            ordered_cohort = sorted(cohort, key=lambda it: ranked_id_to_rank.get(str(it["id"]), 99))
            ranks = [ranked_id_to_rank.get(str(it["id"]), idx + 1) for idx, it in enumerate(ordered_cohort)]

            # Calculate TrueSkill / OpenSkill Bayesian update
            updated_ratings = update_trueskill_multi(ordered_cohort, ranks)

            winner_id = result.winner_id
            self.db.record_cohort_match(
                round_num=round_num,
                cohort_results=updated_ratings,
                winner_id=winner_id,
                reason=result.reason,
                confidence=result.confidence,
                latency_ms=result.latency_ms,
                model_name=result.model_name
            )

            # Reporter log
            self.reporter.log_cohort_match(
                match_idx=current_match_idx,
                round_num=round_num,
                cohort=ordered_cohort,
                results=updated_ratings,
                winner_id=winner_id,
                reason=result.reason,
                latency_ms=result.latency_ms
            )

            # Map to candidate items for WebSocket payload
            candidate_cards = []
            id_to_item = {str(it["id"]): it for it in ordered_cohort}
            for ur in updated_ratings:
                it = id_to_item[ur["id"]]
                candidate_cards.append({
                    "id": ur["id"],
                    "title": it.get("title", f"Item {ur['id']}"),
                    "content": it.get("content", ""),
                    "rank": ur["rank"],
                    "old_mu": ur["old_mu"],
                    "new_mu": ur["new_mu"],
                    "new_sigma": ur["new_sigma"],
                    "delta_mu": ur["delta_mu"],
                    "scaled_rating": ur["scaled_rating"],
                    "ordinal": ur["ordinal"]
                })

            winner_title = id_to_item.get(winner_id, {}).get("title", f"Item {winner_id}")

            # Emit both cohort_match_complete and standard match_complete for UI
            event_payload = {
                "match_idx": current_match_idx,
                "round_num": round_num,
                "rating_mode": "trueskill",
                "cohort_size": len(cohort),
                "candidates": candidate_cards,
                "item_a": candidate_cards[0] if len(candidate_cards) > 0 else {},
                "item_b": candidate_cards[1] if len(candidate_cards) > 1 else {},
                "winner_id": winner_id,
                "winner_title": winner_title,
                "reason": result.reason,
                "confidence": result.confidence,
                "latency_ms": result.latency_ms,
                "model_name": result.model_name,
                "current_leaderboard": self.db.get_leaderboard(limit=15)
            }

            await self._emit("cohort_match_complete", event_payload)
            await self._emit("match_complete", event_payload)

            return {
                "match_id": current_match_idx,
                "winner_id": winner_id,
                "latency_ms": result.latency_ms
            }

    async def run_round(self, round_num: int) -> int:
        """Runs one full round with concurrent match resolution."""
        items = self.db.get_items()

        if self.config.rating_mode == "trueskill":
            played_cohorts = self.db.get_played_cohorts()
            cohorts = self.matchmaker.generate_cohorts(
                items,
                cohort_size=self.config.cohort_size,
                played_cohorts=played_cohorts,
                round_num=round_num
            )
            if not cohorts:
                return 0

            tasks = [
                self._execute_cohort_match(round_num, cohort)
                for cohort in cohorts
            ]
            await asyncio.gather(*tasks)
            return len(cohorts)
        else:
            played_pairs = self.db.get_played_pairs()
            pairings = self.matchmaker.generate_pairings(items, played_pairs, round_num=round_num)
            if not pairings:
                return 0

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
        model_display = getattr(self.judge, "model_name", getattr(self.judge, "model", self.config.model))
        self.reporter.print_banner(
            dataset_name=dataset_name,
            item_count=len(initial_items),
            model=model_display,
            concurrency=self.config.concurrency
        )

        await self._emit("tournament_start", {
            "dataset_name": dataset_name,
            "item_count": len(initial_items),
            "model": model_display,
            "rating_mode": self.config.rating_mode,
            "cohort_size": self.config.cohort_size if self.config.rating_mode == "trueskill" else 2,
            "concurrency": self.config.concurrency,
            "max_rounds": self.config.max_rounds,
            "initial_leaderboard": self.db.get_leaderboard(limit=15)
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
                rating_key = "mu" if self.config.rating_mode == "trueskill" else "elo"
                is_converged, avg_shift, status_msg = self.matchmaker.check_convergence(
                    current_items,
                    round_num,
                    rating_key=rating_key
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
        print(f"  • Rating Engine:        {self.config.rating_mode.upper()} {'(TrueSkill/OpenSkill)' if self.config.rating_mode == 'trueskill' else '(Pairwise Elo)'}")
        print(f"  • Total Matches:        {stats['total_matches']}")
        print(f"  • Total Wall Time:      {total_time:.2f}s")
        print(f"  • Throughput:           {matches_per_sec:.1f} matches/sec")
        print(f"  • Average Model Latency:{stats['avg_latency_ms']}ms")
        print("=" * 80)

        self.reporter.print_leaderboard(final_items, title=f"🏆 FINAL DEFINITIVE {self.config.rating_mode.upper()} RANKINGS", limit=15)

        await self._emit("tournament_complete", {
            "total_matches": stats["total_matches"],
            "total_time": round(total_time, 2),
            "matches_per_sec": round(matches_per_sec, 1),
            "avg_latency_ms": stats["avg_latency_ms"],
            "rating_mode": self.config.rating_mode,
            "final_leaderboard": self.db.get_leaderboard(limit=25)
        })

        return final_items
