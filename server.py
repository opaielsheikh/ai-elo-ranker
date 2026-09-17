#!/usr/bin/env python3
import os
import sys

# Automatically re-execute inside the project's .venv if running with system python
_venv_python = os.path.abspath(os.path.join(os.path.dirname(__file__), ".venv", "bin", "python"))
if os.path.exists(_venv_python) and sys.executable != _venv_python:
    try:
        import fastapi
    except ImportError:
        os.execv(_venv_python, [_venv_python] + sys.argv)

import json
import asyncio
from pathlib import Path
from typing import Set, Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from elo_ranker.config import Config
from elo_ranker.db import Database
from elo_ranker.judge import JevJudge
from elo_ranker.matchmaker import SwissMatchmaker
from elo_ranker.engine import TournamentEngine
from main import load_dataset, get_domain_prompt_and_criteria

app = FastAPI(title="⚡ AI Elo Ranker Live Dashboard")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        if not self.active_connections:
            return
        payload = json.dumps({"type": event_type, "data": data})
        stale = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                stale.append(connection)
        for dead in stale:
            self.active_connections.discard(dead)

manager = ConnectionManager()

# Global state
active_tournament_task: Optional[asyncio.Task] = None
current_tournament_state = {
    "is_running": False,
    "dataset": None,
    "current_round": 0,
    "matches_played": 0,
    "stats": {}
}

class StartTournamentRequest(BaseModel):
    dataset: str = "startup_pitches.json"
    concurrency: int = 8
    rounds: int = 6
    threshold: float = 0.4
    reset_db: bool = False  # Keep history by default!
    api_key: Optional[str] = None

@app.get("/api/datasets")
async def list_datasets():
    datasets_dir = Path("elo_ranker/datasets")
    files = []
    if datasets_dir.exists():
        for f in datasets_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    items = json.load(fp)
                    files.append({
                        "filename": f.name,
                        "name": f.stem.replace("_", " ").title(),
                        "count": len(items)
                    })
            except Exception:
                pass
    return {"datasets": files}

@app.get("/api/status")
async def get_status():
    db = Database(os.getenv("ELO_DB_PATH", "elo_tournament.db"))
    return {
        "is_running": current_tournament_state["is_running"],
        "dataset": current_tournament_state["dataset"],
        "stats": db.get_tournament_stats(),
        "leaderboard": db.get_leaderboard(limit=25),
        "recent_matches": db.get_match_history(limit=30)
    }

async def _run_tournament_job(req: StartTournamentRequest):
    global current_tournament_state
    try:
        # Determine API key: prefer user-supplied key, fallback to server environment
        api_key = (req.api_key or "").strip() or os.getenv("TYPESAFE_API_KEY", "")
        if not api_key:
            await manager.broadcast("tournament_error", {
                "error": "No TypeSafe API Key provided. Please enter your Jev API key in the dashboard."
            })
            return

        current_tournament_state["is_running"] = True
        current_tournament_state["dataset"] = req.dataset

        dataset_path = f"elo_ranker/datasets/{req.dataset}"
        dataset_name, items = load_dataset(dataset_path)
        instructions, criteria = get_domain_prompt_and_criteria(dataset_name)

        config = Config(
            api_key=api_key,
            model=os.getenv("TYPESAFE_MODEL", "jev-latest"),
            db_path="elo_tournament.db",
            concurrency=req.concurrency,
            max_rounds=req.rounds,
            convergence_stability_threshold=req.threshold,
            min_rounds=3
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

        async def ws_event_emitter(event_type: str, data: Dict[str, Any]):
            await manager.broadcast(event_type, data)

        engine = TournamentEngine(
            config=config,
            db=db,
            judge=judge,
            matchmaker=matchmaker,
            event_callback=ws_event_emitter
        )

        await engine.run_tournament(
            dataset_name=dataset_name,
            items=items,
            reset_db=req.reset_db
        )
    except asyncio.CancelledError:
        await manager.broadcast("tournament_stopped", {"reason": "Cancelled by user"})
    except Exception as e:
        await manager.broadcast("tournament_error", {"error": str(e)})
    finally:
        current_tournament_state["is_running"] = False

@app.post("/api/tournament/start")
async def start_tournament(req: StartTournamentRequest):
    global active_tournament_task
    if current_tournament_state["is_running"]:
        return JSONResponse(status_code=400, content={"error": "A tournament is already in progress"})

    active_tournament_task = asyncio.create_task(_run_tournament_job(req))
    return {"status": "started", "dataset": req.dataset}

@app.post("/api/tournament/stop")
async def stop_tournament():
    global active_tournament_task
    if active_tournament_task and not active_tournament_task.done():
        active_tournament_task.cancel()
        current_tournament_state["is_running"] = False
        return {"status": "stopping"}
    return {"status": "not_running"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    db = Database(os.getenv("ELO_DB_PATH", "elo_tournament.db"))
    # Send initial state with past match history and leaderboard
    await websocket.send_text(json.dumps({
        "type": "init",
        "data": {
            "is_running": current_tournament_state["is_running"],
            "dataset": current_tournament_state["dataset"],
            "stats": db.get_tournament_stats(),
            "leaderboard": db.get_leaderboard(limit=50),
            "recent_matches": db.get_match_history(limit=35)
        }
    }))
    try:
        while True:
            await websocket.receive_text()  # Keep alive / listen
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    print(f"\n🚀 AI Elo Ranker Live Dashboard running at http://localhost:{port}\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
