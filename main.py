#!/usr/bin/env python3
import os
import sys

# Automatically re-execute inside the project's .venv if running with system python
_venv_python = os.path.abspath(os.path.join(os.path.dirname(__file__), ".venv", "bin", "python"))
if os.path.exists(_venv_python) and sys.executable != _venv_python:
    try:
        import typesafe_sdk
    except ImportError:
        os.execv(_venv_python, [_venv_python] + sys.argv)

import json
import asyncio
import argparse
from pathlib import Path

from elo_ranker.config import Config
from elo_ranker.engine import TournamentEngine
from elo_ranker.judge import JevJudge
from elo_ranker.db import Database
from elo_ranker.matchmaker import SwissMatchmaker

def load_dataset(file_path: str) -> tuple[str, list[dict]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {file_path}")
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    dataset_name = path.stem.replace("_", " ").title()
    return dataset_name, data

def get_domain_prompt_and_criteria(dataset_name: str) -> tuple[str, dict[str, str]]:
    """Returns domain-tuned comparison instructions and criteria options for Jev System One."""
    name_lower = dataset_name.lower()
    
    if "poem" in name_lower:
        instructions = (
            "You are an elite literary critic. Compare Candidate A and Candidate B on imagery, "
            "rhythm, evocative power, poetic diction, and emotional resonance. Declare the superior poem."
        )
        criteria = {
            "imagery_and_metaphor": "Vivid, original imagery and powerful metaphorical depth",
            "meter_and_cadence": "Superior rhythmic flow, meter, and lyrical musicality",
            "emotional_resonance": "Profound emotional impact and psychological resonance",
            "originality_of_voice": "Distinctive, daring, and authentic poetic voice",
            "structural_craft": "Masterful economy of language and formal structure"
        }
    elif "pitch" in name_lower or "startup" in name_lower:
        instructions = (
            "You are a top-tier venture capitalist. Compare Startup A and Startup B on problem severity, "
            "solution elegance, market inevitability, clarity of value prop, and sheer compelling power. "
            "Declare the superior pitch."
        )
        criteria = {
            "hair_on_fire_problem": "Solves a much more acute, urgent, and painful problem",
            "solution_elegance": "Radically simpler, faster, or 10x better solution approach",
            "scalability_and_tam": "Massive market size potential and explosive scalability",
            "clarity_and_punch": "Crystal-clear, punchy, and instantly understandable narrative",
            "defensibility_and_moat": "Stronger structural moat and competitive advantage"
        }
    else:
        instructions = (
            "Compare Candidate A and Candidate B. Evaluate them on clarity, creativity, persuasion, "
            "and execution quality. Declare which candidate is superior."
        )
        criteria = {
            "clarity_and_flow": "Clearer structure, coherence, and flow",
            "depth_and_insight": "More profound insights and intellectual depth",
            "persuasion_and_punch": "Higher persuasive power and memorable impact",
            "creative_originality": "More innovative and unconventional perspective",
            "economy_of_expression": "Superior conciseness and punchy phrasing"
        }
        
    return instructions, criteria

async def main():
    parser = argparse.ArgumentParser(
        description="⚡ AI Elo Ranker - Fast Recursive Text Tournament powered by Jev"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="elo_ranker/datasets/startup_pitches.json",
        help="Path to JSON dataset file (e.g., elo_ranker/datasets/poems.json or startup_pitches.json)"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent async Jev judge requests (default: 10)"
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=8,
        help="Maximum Swiss tournament rounds (default: 8)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.4,
        help="Convergence rank shift threshold (default: 0.4)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="elo_tournament.db",
        help="Path to SQLite database file"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume existing tournament without clearing database"
    )

    args = parser.parse_args()

    # Verify API key
    api_key = os.getenv("TYPESAFE_API_KEY")
    if not api_key:
        print("\033[91m[ERROR] TYPESAFE_API_KEY environment variable is not set in .env!\033[0m")
        sys.exit(1)

    dataset_name, items = load_dataset(args.dataset)
    instructions, criteria = get_domain_prompt_and_criteria(dataset_name)

    config = Config(
        api_key=api_key,
        model=os.getenv("TYPESAFE_MODEL", "jev-latest"),
        db_path=args.db,
        concurrency=args.concurrency,
        max_rounds=args.rounds,
        convergence_stability_threshold=args.threshold,
        min_rounds=4
    )

    db = Database(config.db_path)
    judge = JevJudge(
        api_key=config.api_key,
        model=config.model,
        instructions=instructions,
        domain_criteria=criteria
    )
    matchmaker = SwissMatchmaker(
        stability_threshold=config.convergence_stability_threshold,
        min_rounds=config.min_rounds,
        max_rounds=config.max_rounds
    )

    engine = TournamentEngine(
        config=config,
        db=db,
        judge=judge,
        matchmaker=matchmaker
    )

    await engine.run_tournament(
        dataset_name=dataset_name,
        items=items,
        reset_db=not args.resume
    )

if __name__ == "__main__":
    asyncio.run(main())
