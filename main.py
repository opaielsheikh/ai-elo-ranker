#!/usr/bin/env python3
import os
import sys

# Automatically re-execute inside the project's .venv if running with system python
_venv_python = os.path.abspath(os.path.join(os.path.dirname(__file__), ".venv", "bin", "python"))
if os.path.exists(_venv_python) and sys.executable != _venv_python:
    os.execv(_venv_python, [_venv_python] + sys.argv)


import json
import asyncio
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from elo_ranker.config import Config
from elo_ranker.engine import TournamentEngine
from elo_ranker.judge import (
    BaseJudge, JevJudge, OpenAICompatibleJudge, EnsembleJudge, MockJudge
)
from elo_ranker.db import Database
from elo_ranker.matchmaker import SwissMatchmaker

def load_dataset(file_path: str) -> Tuple[str, list[dict]]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {file_path}")
    
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    dataset_name = path.stem.replace("_", " ").title()
    return dataset_name, data

def get_domain_prompt_and_criteria(dataset_name: str) -> Tuple[str, dict[str, str]]:
    """Returns domain-tuned comparison instructions and criteria options."""
    name_lower = dataset_name.lower()
    
    if "poem" in name_lower:
        instructions = (
            "You are an elite literary critic. Compare the candidates with discernment. "
            "Evaluate lyrical musicality, rhyme craft, metrical precision, and profound thematic meaning. "
            "Declare the superior work."
        )
        criteria = {
            "musicality_and_cadence": "Superior lyrical musicality, melodic cadence, and auditory flow",
            "rhyme_and_craft": "Masterful rhyme scheme, metrical precision, and formal craft",
            "thematic_meaning": "Profound philosophical meaning, emotional depth, and substance",
            "imagery_and_metaphor": "Vivid metaphorical imagery, symbolism, and evocative power",
            "originality_and_voice": "Distinctive poetic voice and unforgettable resonance"
        }
    elif "pitch" in name_lower or "startup" in name_lower:
        instructions = (
            "You are a top-tier venture capitalist. Compare the startup pitches on problem severity, "
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
            "Compare the candidates. Evaluate them on clarity, creativity, persuasion, "
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

def build_judge(
    judge_type: str,
    api_key: str = "",
    model: str = "jev-latest",
    local_url: str = "http://localhost:11434/v1",
    local_model: str = "qwen2.5:7b",
    local_key: Optional[str] = None,
    instructions: Optional[str] = None,
    criteria: Optional[Dict[str, str]] = None
) -> BaseJudge:
    """Factory helper to construct the selected judge."""
    jtype = judge_type.lower().strip()
    resolved_local_key = local_key or os.getenv("LOCAL_API_KEY") or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "ollama"

    if jtype == "mock":
        return MockJudge(domain_criteria=criteria, instructions=instructions)
    elif jtype in ("local", "openai", "openjev", "laya", "ollama", "vllm"):
        return OpenAICompatibleJudge(
            base_url=local_url,
            api_key=resolved_local_key,
            model=local_model,
            domain_criteria=criteria,
            instructions=instructions
        )

    elif jtype == "ensemble":
        # Committee consisting of available judges
        judges: list[BaseJudge] = []
        if api_key:
            judges.append(JevJudge(api_key=api_key, model=model, domain_criteria=criteria, instructions=instructions))
        judges.append(OpenAICompatibleJudge(base_url=local_url, api_key=local_key, model=local_model, domain_criteria=criteria, instructions=instructions))
        judges.append(MockJudge(domain_criteria=criteria, instructions=instructions))
        return EnsembleJudge(judges=judges, domain_criteria=criteria, instructions=instructions)
    else:
        return JevJudge(
            api_key=api_key,
            model=model,
            domain_criteria=criteria,
            instructions=instructions
        )

async def main():
    parser = argparse.ArgumentParser(
        description="⚡ AI Elo & TrueSkill Ranker - Fast Recursive Text Tournament powered by Open-Weight Models & Jev"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="elo_ranker/datasets/startup_pitches.json",
        help="Path to JSON dataset file"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["elo", "trueskill"],
        default="elo",
        help="Rating algorithm: 'elo' (1v1 Swiss) or 'trueskill' (N-candidate Bayesian)"
    )
    parser.add_argument(
        "--cohort-size",
        type=int,
        default=3,
        help="Cohort size for TrueSkill mode (e.g. 3 or 4 candidates per match)"
    )
    parser.add_argument(
        "--judge",
        type=str,
        choices=["jev", "local", "ensemble", "mock"],
        default="jev",
        help="Judge backend: 'jev' (TypeSafe API), 'local' (Ollama/vLLM/Qwen/Gemma), 'ensemble' (Committee), 'mock' (Offline)"
    )
    parser.add_argument(
        "--local-url",
        type=str,
        default=os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1"),
        help="Base URL for OpenAI-compatible local server (default: http://localhost:11434/v1)"
    )
    parser.add_argument(
        "--local-model",
        type=str,
        default=os.getenv("LOCAL_MODEL", "qwen2.5:7b"),
        help="Model name for local server (e.g. qwen2.5:7b, gemma2:9b, openjev, laya)"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Number of concurrent async judge workers (default: 8)"
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=6,
        help="Maximum tournament rounds (default: 6)"
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

    api_key = os.getenv("TYPESAFE_API_KEY", "")
    if args.judge == "jev" and not api_key:
        print("\033[93m[NOTICE] No TYPESAFE_API_KEY found. Falling back to local/mock judge.\033[0m")
        args.judge = "mock"

    dataset_name, items = load_dataset(args.dataset)
    instructions, criteria = get_domain_prompt_and_criteria(dataset_name)

    config = Config(
        api_key=api_key,
        model=os.getenv("TYPESAFE_MODEL", "jev-latest"),
        judge_type=args.judge,
        local_base_url=args.local_url,
        local_model=args.local_model,
        rating_mode=args.mode,
        cohort_size=args.cohort_size,
        db_path=args.db,
        concurrency=args.concurrency,
        max_rounds=args.rounds,
        convergence_stability_threshold=args.threshold,
        min_rounds=3
    )

    db = Database(config.db_path)
    judge = build_judge(
        judge_type=args.judge,
        api_key=config.api_key,
        model=config.model,
        local_url=config.local_base_url,
        local_model=config.local_model,
        instructions=instructions,
        criteria=criteria
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
