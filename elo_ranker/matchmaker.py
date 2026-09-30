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
        Generates Swiss-style pairings for 1-vs-1 matches (standard Elo).
        Pairs items with similar ratings who haven't played each other yet.
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

        # Sort items by rating descending. Break ties by fewest matches played (exploration)
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
            # pair with closest available in rating
            if best_idx is None:
                best_idx = 0

            opponent = unpaired.pop(best_idx)
            pairings.append((current, opponent))

        return pairings

    def generate_cohorts(
        self,
        items: List[Dict[str, Any]],
        cohort_size: int = 3,
        played_cohorts: Optional[Set[Tuple[str, ...]]] = None,
        round_num: int = 1
    ) -> List[List[Dict[str, Any]]]:
        """
        Generates multi-candidate cohorts of size N (e.g., 3 or 4) for TrueSkill ranking.
        Groups contestants with similar skill or high uncertainty (sigma) to maximize
        information gain and Bayesian entropy reduction.
        """
        if len(items) < cohort_size:
            if len(items) >= 2:
                return [list(items)]
            return []

        played = played_cohorts or set()

        if round_num == 1:
            shuffled = list(items)
            random.shuffle(shuffled)
            cohorts = []
            for i in range(0, len(shuffled), cohort_size):
                cohort = shuffled[i:i + cohort_size]
                if len(cohort) >= 2:  # Accept cohorts of at least 2
                    cohorts.append(cohort)
            return cohorts

        # Sort primarily by uncertainty (highest sigma first for rapid exploration)
        # and then by current skill (mu or scaled_rating)
        pool = sorted(
            items,
            key=lambda x: (
                x.get("sigma", 8.333),
                x.get("mu", 25.0)
            ),
            reverse=True
        )

        unassigned = list(pool)
        cohorts: List[List[Dict[str, Any]]] = []

        while len(unassigned) >= cohort_size:
            current = unassigned.pop(0)
            cohort = [current]

            # Greedily find (cohort_size - 1) candidates that have the closest skill
            # and minimize repeated co-appearances
            best_candidates = []
            for candidate in unassigned:
                cand_mu = candidate.get("mu", 25.0)
                diff = abs(cand_mu - current.get("mu", 25.0))
                best_candidates.append((diff, candidate))

            best_candidates.sort(key=lambda x: x[0])

            # Select candidates prioritizing unplayed combinations
            chosen_for_cohort = []
            for _, cand in best_candidates:
                test_group = tuple(sorted([str(current["id"])] + [str(c["id"]) for c in chosen_for_cohort] + [str(cand["id"])]))
                if len(test_group) == cohort_size and test_group in played and len(best_candidates) > cohort_size:
                    continue
                chosen_for_cohort.append(cand)
                if len(chosen_for_cohort) == cohort_size - 1:
                    break

            for c in chosen_for_cohort:
                unassigned.remove(c)
                cohort.append(c)

            cohorts.append(cohort)

        # Handle remaining 1 or 2 items by appending to previous cohorts
        if unassigned:
            if cohorts:
                for rem in unassigned:
                    # Append leftover item to the smallest cohort
                    smallest = min(cohorts, key=len)
                    smallest.append(rem)
            elif len(unassigned) >= 2:
                cohorts.append(unassigned)

        return cohorts

    def check_convergence(
        self,
        current_items: List[Dict[str, Any]],
        current_round: int,
        rating_key: str = "elo"
    ) -> Tuple[bool, float, str]:
        """
        Calculates ranking stability between consecutive rounds.
        Works for both Elo ('elo') and TrueSkill ('mu' or 'ordinal').
        Returns: (is_converged, average_rank_shift, reason_message)
        """
        # Determine sorting key
        def get_score(it: Dict[str, Any]) -> float:
            if rating_key in it:
                return float(it[rating_key])
            if "ordinal" in it:
                return float(it["ordinal"])
            if "mu" in it:
                return float(it["mu"])
            return float(it.get("elo", 1200.0))

        current_ranking = [str(item["id"]) for item in sorted(current_items, key=get_score, reverse=True)]

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
