import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    api_key: str = os.getenv("TYPESAFE_API_KEY", "")
    model: str = os.getenv("TYPESAFE_MODEL", "jev-latest")
    db_path: str = os.getenv("ELO_DB_PATH", "elo_tournament.db")
    default_elo: float = 1200.0
    base_k_factor: float = 32.0
    min_k_factor: float = 16.0
    concurrency: int = int(os.getenv("ELO_CONCURRENCY", "10"))
    convergence_stability_threshold: float = 0.5  # average rank shift below which we consider stable
    min_rounds: int = 5
    max_rounds: int = 15
