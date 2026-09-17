from typing import Tuple

def calculate_expected_score(rating_a: float, rating_b: float) -> float:
    """
    Calculates the expected score of contestant A against contestant B.
    Standard Elo formula: E_A = 1 / (1 + 10^((R_B - R_A) / 400))
    Returns a probability between 0.0 and 1.0.
    """
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))

def get_dynamic_k_factor(matches_played: int, base_k: float = 32.0, min_k: float = 16.0) -> float:
    """
    Dynamic K-factor: Higher K for early matches to allow rapid rating exploration,
    gradually decaying to min_k as more matches are played to achieve stability.
    """
    if matches_played < 5:
        return base_k * 1.5  # Early placement phase
    elif matches_played < 12:
        return base_k        # Mid calibration phase
    else:
        return max(min_k, base_k * 0.75) # Fine-tuning phase

def update_elo(
    rating_a: float,
    rating_b: float,
    score_a: float,  # 1.0 for A win, 0.0 for B win (A loss), 0.5 for tie
    matches_a: int = 0,
    matches_b: int = 0,
    base_k: float = 32.0,
    min_k: float = 16.0,
) -> Tuple[float, float, float, float]:
    """
    Calculates updated Elo ratings for both contestants after a match.
    
    Args:
        rating_a: Current rating of contestant A
        rating_b: Current rating of contestant B
        score_a: Actual outcome for contestant A (1.0 = win, 0.0 = loss, 0.5 = draw)
        matches_a: Total matches contestant A has played so far
        matches_b: Total matches contestant B has played so far
        base_k: Base K-factor multiplier
        min_k: Minimum K-factor
        
    Returns:
        (new_rating_a, new_rating_b, delta_a, delta_b)
    """
    expected_a = calculate_expected_score(rating_a, rating_b)
    expected_b = 1.0 - expected_a
    score_b = 1.0 - score_a

    k_a = get_dynamic_k_factor(matches_a, base_k, min_k)
    k_b = get_dynamic_k_factor(matches_b, base_k, min_k)

    delta_a = k_a * (score_a - expected_a)
    delta_b = k_b * (score_b - expected_b)

    new_rating_a = round(rating_a + delta_a, 2)
    new_rating_b = round(rating_b + delta_b, 2)

    return new_rating_a, new_rating_b, round(delta_a, 2), round(delta_b, 2)
