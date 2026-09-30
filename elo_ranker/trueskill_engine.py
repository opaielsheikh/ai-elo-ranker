"""
TrueSkill / OpenSkill Bayesian Rating Engine.
Supports both multi-candidate (N-way) cohort rankings and 1-vs-1 Bayesian skill updates.
Uses the Plackett-Luce model from openskill.
"""

from typing import List, Tuple, Dict, Any, Optional
from openskill.models import PlackettLuce

# Global Plackett-Luce model instance
_model = PlackettLuce()

DEFAULT_MU = 25.0
DEFAULT_SIGMA = 25.0 / 3.0  # 8.333333333333334

def get_default_rating() -> Tuple[float, float]:
    """Returns default (mu, sigma)."""
    return DEFAULT_MU, DEFAULT_SIGMA

def calculate_ordinal(mu: float, sigma: float) -> float:
    """
    Conservative rating estimate (mu - 3*sigma).
    Standard TrueSkill / OpenSkill metric ensuring 99% confidence.
    """
    return round(mu - 3.0 * sigma, 3)

def to_scaled_rating(mu: float, sigma: Optional[float] = None, base: float = 1200.0, scale: float = 32.0) -> float:
    """
    Maps Bayesian mu to an Elo-comparable 1200-centered scale for user familiarity.
    Default: mu=25.0 -> 1200.0
    """
    scaled = base + (mu - DEFAULT_MU) * scale
    return round(scaled, 1)

def update_trueskill_multi(
    players: List[Dict[str, Any]],
    ranks: List[int]
) -> List[Dict[str, Any]]:
    """
    Updates ratings for N players evaluated in a single multi-candidate match.
    
    Args:
        players: List of dicts containing at least 'id', 'mu', and 'sigma'.
        ranks: List of 1-indexed finishing places, e.g. [1, 2, 3] for 1st, 2nd, 3rd.
               Equal ranks represent ties.
               
    Returns:
        List of dicts with player id, new_mu, new_sigma, delta_mu, delta_sigma, and rank.
    """
    if len(players) != len(ranks):
        raise ValueError("Number of players must equal number of ranks.")

    # Create OpenSkill rating objects
    teams = [[_model.rating(mu=float(p.get("mu", DEFAULT_MU)), sigma=float(p.get("sigma", DEFAULT_SIGMA)))] for p in players]
    
    # Calculate updated ratings using Plackett-Luce
    new_teams = _model.rate(teams, ranks=ranks)

    results = []
    for i, p in enumerate(players):
        old_mu = float(p.get("mu", DEFAULT_MU))
        old_sigma = float(p.get("sigma", DEFAULT_SIGMA))
        
        updated_rating = new_teams[i][0]
        new_mu = round(float(updated_rating.mu), 4)
        new_sigma = round(float(updated_rating.sigma), 4)
        
        delta_mu = round(new_mu - old_mu, 4)
        delta_sigma = round(new_sigma - old_sigma, 4)

        results.append({
            "id": str(p["id"]),
            "rank": ranks[i],
            "old_mu": old_mu,
            "old_sigma": old_sigma,
            "new_mu": new_mu,
            "new_sigma": new_sigma,
            "delta_mu": delta_mu,
            "delta_sigma": delta_sigma,
            "ordinal": calculate_ordinal(new_mu, new_sigma),
            "scaled_rating": to_scaled_rating(new_mu, new_sigma)
        })

    return results

def update_trueskill_pair(
    mu_a: float,
    sigma_a: float,
    mu_b: float,
    sigma_b: float,
    score_a: float
) -> Tuple[float, float, float, float, float, float]:
    """
    1-vs-1 Bayesian TrueSkill update.
    score_a: 1.0 (A wins), 0.0 (B wins), 0.5 (tie).
    Returns (new_mu_a, new_sigma_a, delta_mu_a, new_mu_b, new_sigma_b, delta_mu_b).
    """
    if score_a == 1.0:
        ranks = [1, 2]
    elif score_a == 0.0:
        ranks = [2, 1]
    else:
        ranks = [1, 1]

    players = [
        {"id": "a", "mu": mu_a, "sigma": sigma_a},
        {"id": "b", "mu": mu_b, "sigma": sigma_b}
    ]
    res = update_trueskill_multi(players, ranks)
    a_res = res[0]
    b_res = res[1]

    return (
        a_res["new_mu"],
        a_res["new_sigma"],
        a_res["delta_mu"],
        b_res["new_mu"],
        b_res["new_sigma"],
        b_res["delta_mu"]
    )
