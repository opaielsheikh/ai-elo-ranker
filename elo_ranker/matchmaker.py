import random
from typing import List, Dict, Any, Set, Tuple, Optional

class SwissMatchmaker:
    def __init__(self, stability_threshold: float = 0.5, min_rounds: int = 5, max_rounds: int = 15):
        self.stability_threshold = stability_threshold
        self.min_rounds = min_rounds
        self.max_rounds = max_rounds
        self.previous_rankings: List[str] = []

    def generate_pairings(
        self,
        items: List[Dict[str, Any]],
        played_pairs: Set[Tuple[str, str]],
        round_num: int
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """
        Generates Swiss-style pairings for the current round.
        Pairs items with similar Elo ratings who haven't played each other yet.
        """
        if len(items) < 2:
            return []

        # In round 1, randomize slightly or pair adjacent to seed initial variance
        if round_num == 1:
            shuffled = list(items)
            random.shuffle(shuffled)
            pairings = []
            for i in range(0, len(shuffled) - 1, 2):
                pairings.append((shuffled[i], shuffled[i + 1]))
            return pairings

        # Sort items by Elo descending. Break ties by fewest matches played (exploration)
        pool = sorted(items, key=lambda x: (x.get("elo", 1200.0), -x.get("matches_count", 0)), reverse=True)
        unpaired = list(pool)
        pairings: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []

        while len(unpaired) >= 2:
            current = unpaired.pop(0)
            cur_id = str(current["id"])
            
            # Find closest candidate in rating that hasn't played against current
            best_idx = None
            for idx, candidate in enumerate(unpaired):
                cand_id = str(candidate["id"])
                pair_key = (min(cur_id, cand_id), max(cur_id, cand_id))
                if pair_key not in played_pairs:
                    best_idx = idx
                    break

            # If all remaining opponents in unpaired have already played against current,
            # pair with the opponent with the fewest matches or smallest Elo difference
            if best_idx is None:
                best_idx = 0  # Fallback to closest available in rating

            opponent = unpaired.pop(best_idx)
            pairings.append((current, opponent))

        return pairings

    def check_convergence(
        self,
        current_items: List[Dict[str, Any]],
        current_round: int
    ) -> Tuple[bool, float, str]:
        """
        Calculates ranking stability between consecutive rounds.
        Returns: (is_converged, average_rank_shift, reason_message)
        """
        # Current ordering by Elo
        current_ranking = [str(item["id"]) for item in sorted(current_items, key=lambda x: x["elo"], reverse=True)]

        if not self.previous_rankings:
            self.previous_rankings = current_ranking
            return False, 999.0, "Initial round completed"

        # Calculate Mean Absolute Rank Shift (MARS)
        rank_map_prev = {item_id: rank for rank, item_id in enumerate(self.previous_rankings)}
        rank_shifts = []
        for current_rank, item_id in enumerate(current_ranking):
            if item_id in rank_map_prev:
                shift = abs(current_rank - rank_map_prev[item_id])
                rank_shifts.append(shift)

        avg_shift = sum(rank_shifts) / len(rank_shifts) if rank_shifts else 0.0
        self.previous_rankings = current_ranking

        if current_round >= self.max_rounds:
            return True, round(avg_shift, 2), f"Reached maximum round limit ({self.max_rounds})"

        if current_round >= self.min_rounds and avg_shift <= self.stability_threshold:
            return True, round(avg_shift, 2), f"Leaderboard stabilized (avg rank shift: {avg_shift:.2f} <= {self.stability_threshold})"

        return False, round(avg_shift, 2), f"Rank shift: {avg_shift:.2f} (threshold: {self.stability_threshold})"
