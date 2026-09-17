# ⚡ AI Elo Ranker (Powered by Jev & Swiss Matchmaking)

A blazing-fast, recursive tournament engine for ranking texts (poems, startup pitches, rap lyrics, cold emails, marketing hooks) using Jev LLM and standard Elo rating mechanics.

Designed for high-throughput concurrency and visual terminal demos on X (Twitter).

---

## 🚀 Key Architectural Highlights

1. **$O(N \log N)$ Swiss-System Matchmaker vs $O(N^2)$ Round-Robin**:
   - Instead of comparing all 1,225 pairs in a 50-item dataset, the Swiss matchmaker pairs items with similar current Elo ratings who haven't yet played each other.
   - Matches with equal expected win probabilities (~50/50) yield **maximum information gain** (~1 bit of entropy reduction).
   - Achieves stable convergence in only 6–8 rounds (~150 matches vs 1,225 matches).

2. **Position Bias Elimination**:
   - In pairwise LLM evaluations, models often exhibit order bias (e.g., favoring Option A).
   - The engine automatically randomizes presentation order (50% swap chance) and maps decisions back to the ground-truth item ID.

3. **Dynamic K-Factor Elo Engine**:
   - New items start with high $K=48$ during placement rounds to rapidly reach their correct tier.
   - Scales down to $K=24$ and $K=16$ in later rounds to lock in high-precision rankings without oscillating.

4. **Concurrent Jev API Pipeline**:
   - Uses `AsyncTypeSafeClient` with persistent HTTP keep-alive connection pooling.
   - Evaluates 10+ head-to-head duels in parallel, achieving **10+ matches per second** with sub-300ms model latency.

5. **Local SQLite Persistence**:
   - Tracks full audit trails: initial & post Elo, point deltas, winner IDs, Jev rationale, confidence score, and latency.

---

## 📂 Project Structure

```
.
├── main.py                  # CLI runner with domain detection and live visual leaderboard
├── elo_tournament.db        # SQLite database (auto-created)
├── elo_ranker/
│   ├── elo.py               # Pure math: Expected scores, dynamic K-factor, Elo updates
│   ├── judge.py             # Async Jev wrapper with position bias mitigation & retries
│   ├── matchmaker.py        # Swiss-system pairing & rank convergence evaluator
│   ├── db.py                # SQLite schema, match logs, and leaderboard queries
│   ├── engine.py            # Asyncio tournament orchestrator with worker pools
│   ├── reporter.py          # Terminal visual renderer with ANSI colors & progress bars
│   ├── config.py            # Environment settings and defaults
│   └── datasets/
│       ├── poems.json       # 12 famous classic poems
│       └── startup_pitches.json # 12 iconic startup pitch decks
```

---

## ⚡ Quick Start

### 1. Set Your Environment
Ensure your `.env` contains your TypeSafe API credentials:
```env
TYPESAFE_API_KEY=your_key_here
TYPESAFE_MODEL=jev-latest
```

### 2. Run with Startup Pitches
```bash
python main.py --dataset elo_ranker/datasets/startup_pitches.json --concurrency 8 --rounds 6
```

### 3. Run with Famous Poems
```bash
python main.py --dataset elo_ranker/datasets/poems.json --concurrency 8 --rounds 6
```

### 4. Resuming an Existing Tournament
```bash
python main.py --dataset elo_ranker/datasets/startup_pitches.json --resume --rounds 10
```

---

## 📊 Dataset Schema (Easy to Swap)

To rank your own texts (e.g., rap lyrics, cold emails, ad copy), create a JSON file with this format:

```json
[
  {
    "id": "item_01",
    "title": "Short Descriptive Title",
    "content": "The actual text body to be evaluated by Jev...",
    "metadata": {
      "author": "Optional",
      "category": "Optional"
    }
  }
]
```
Then run:
```bash
python main.py --dataset path/to/your_dataset.json
```
