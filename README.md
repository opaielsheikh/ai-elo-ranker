# ⚡ AI Elo Ranker (Powered by Jev & Swiss Matchmaking)

A blazing-fast, recursive tournament engine for ranking texts (poems, startup pitches, rap lyrics, cold emails, ad hooks) using Jev LLM, standard Elo rating mechanics, and real-time WebSocket streaming.

Designed for high-throughput concurrency, cinematic live demos on X (Twitter), and web-based interactive exploration.

---

## 🌟 Key Features & Architecture

```
                               ┌──────────────────────────┐
                               │  Dataset (JSON / SQLite) │
                               │ 10,000 Poems / Pitches   │
                               └────────────┬─────────────┘
                                            │
                                            ▼
                               ┌──────────────────────────┐
                               │  Swiss Matchmaker Engine │
                               │ O(N log N) Entropy Max   │
                               └────────────┬─────────────┘
                                            │
                                            ▼
                               ┌──────────────────────────┐
                  ┌────────────┤ Async Concurrency Pool   ├────────────┐
                  │            │ 16 Parallel Jev Workers  │            │
                  ▼            └──────────────────────────┘            ▼
       ┌─────────────────────┐                               ┌─────────────────────┐
       │ Duel A: Pos. Bias   │                               │ Duel B: Pos. Bias   │
       │ Randomization Swap  │                               │ Randomization Swap  │
       └──────────┬──────────┘                               └──────────┬──────────┘
                  │                                                     │
                  ▼                                                     ▼
       ┌─────────────────────┐                               ┌─────────────────────┐
       │ Jev System One LLM  │                               │ Jev System One LLM  │
       │ Winner + Rationale  │                               │ Winner + Rationale  │
       └──────────┬──────────┘                               └──────────┬──────────┘
                  │                                                     │
                  └─────────────────────────┬───────────────────────────┘
                                            │
                                            ▼
                               ┌──────────────────────────┐
                               │ Dynamic K-Factor Elo     │
                               │ K=48 (early) -> K=16     │
                               └────────────┬─────────────┘
                                            │
                  ┌─────────────────────────┴─────────────────────────┐
                  ▼                                                   ▼
       ┌─────────────────────┐                             ┌─────────────────────┐
       │ SQLite Persistence  │                             │ WebSocket Streamer  │
       │ WAL Mode Audit Logs │                             │ Live Web Dashboard  │
       └─────────────────────┘                             └─────────────────────┘
```

1. **$O(N \log N)$ Swiss-System Matchmaker vs $O(N^2)$ Round-Robin**:
   - Instead of comparing all 50,000,000 pairs in a 10,000-item set, the Swiss matchmaker pairs items with adjacent Elo ratings who haven't yet faced each other.
   - Matches with equal expected win probabilities (~50/50) yield **maximum information gain** (~1 bit of entropy reduction per match).
   - Reduces a 10,000-item tournament from 50 million duels down to ~70,000 matches!

2. **Real-Time Visual Web Dashboard**:
   - **Battle Arena**: Dynamic dueling cards with Candidate A vs B, pulsing neon VS orb, winner slam animations, and floating `+Elo` / `-Elo` delta bubbles.
   - **AI Verdict Banner**: Displays Jev's exact critique explaining why the winning text was superior.
   - **Live Definitive Leaderboard**: Automatically re-orders with Gold 🥇, Silver 🥈, and Bronze 🥉 medals and fluid CSS progress bars.
   - **Live Metrics**: Real-time throughput (matches/sec), average model latency (ms), total matches, and convergence stability shift.
   - **Web Audio FX**: Built-in sci-fi cyber sound effects synthesize audio on every match resolution (toggleable 🔊).

3. **Position Bias Elimination**:
   - In pairwise LLM evaluations, models frequently favor the first candidate. The engine randomly coin-flips presentation order (50% probability) and maps decisions back to ground-truth contestant IDs.

4. **Dynamic K-Factor Elo Engine**:
   - Early placement matches utilize $K=48$ ($1.5 \times 32$) for rapid discovery, gradually decaying to $K=24$ and $K=16$ for high-precision convergence.

5. **Instant Cloudflare Public Deployment**:
   - Out-of-the-box support for zero-config public HTTPS streaming via Cloudflare Tunnels, allowing followers on X to watch live on mobile or desktop.

---

## 📂 Project Structure

```
.
├── server.py                # FastAPI WebSocket server streaming duels to the web UI
├── main.py                  # CLI tournament runner with auto-venv detection
├── elo_tournament.db        # SQLite database in WAL mode (auto-created)
├── static/
│   ├── index.html           # High-tech glassmorphism dashboard UI
│   ├── styles.css           # Modern cyber styling with micro-animations
│   └── app.js               # WebSocket client, sound synthesizer, and live DOM updates
├── elo_ranker/
│   ├── elo.py               # Pure math: Expected scores, dynamic K-factor, rating deltas
│   ├── judge.py             # Async Jev wrapper with position bias mitigation & retries
│   ├── matchmaker.py        # Swiss-system pairing & rank convergence evaluator
│   ├── db.py                # SQLite schema, match logs, and leaderboard queries
│   ├── engine.py            # Asyncio tournament orchestrator with worker pools
│   ├── reporter.py          # Terminal visual renderer with ANSI colors & progress bars
│   ├── config.py            # Environment settings and defaults
│   └── datasets/
│       ├── famous_poems_10k.json   # 10,000 classic & historical poems
│       ├── curator_cycle.json      # The Curator's Cycle (17 movements by Opaiel)
│       ├── startup_pitches.json    # 12 iconic startup pitch decks
│       └── poems.json              # Curated classic poetry division
```

---

## ⚡ Quick Start

### 1. Set Your Environment
Ensure your `.env` contains your TypeSafe API credentials:
```env
TYPESAFE_API_KEY=your_key_here
TYPESAFE_MODEL=jev-latest
```

### 2. Launch the Real-Time Web Dashboard
Start the local server (runs automatically inside `.venv`):
```bash
python3 server.py
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser, pick a dataset, and click **START TOURNAMENT**!

### 3. Deploy Live Online (Public HTTPS)
Share your tournament with followers on X in real time:
```bash
cloudflared tunnel --url http://localhost:8000
```
This generates a secure public HTTPS URL (e.g., `https://your-name.trycloudflare.com`).

### 4. Run via Terminal CLI
If you prefer running directly in the shell with real-time ANSI terminal logging:
```bash
# Run 10,000 Poems Tournament (16 parallel workers)
python3 main.py --dataset elo_ranker/datasets/famous_poems_10k.json --concurrency 16 --rounds 6

# Run The Curator's Cycle (17-part sequence)
python3 main.py --dataset elo_ranker/datasets/curator_cycle.json --concurrency 8 --rounds 4

# Run Startup Pitches
python3 main.py --dataset elo_ranker/datasets/startup_pitches.json --concurrency 8 --rounds 6
```

---

## 🏆 Featured Datasets

### 📜 1. The 10,000 Poems Championship (`famous_poems_10k.json`)
A massive corpus of 10,000 classic, historical, and modern poems from over 100 celebrated poets (Shakespeare, Emily Dickinson, Edgar Allan Poe, Percy Bysshe Shelley, Lord Byron, Walt Whitman, John Keats, Robert Frost, etc.).

### 🖋️ 2. The Curator's Cycle (`curator_cycle.json`)
The complete 17-part philosophical epic sequence by Opaiel (*The Storm, The Thing, The Homunculus, O'man, and The Curator*):
- **Intra-Cycle Results**: In head-to-head benchmarking judged by Jev System One, **Movement XIV (*Da Capo: Retreat of Prospero; A Solo*)** took **#1 place undefeated (4W - 0L, 1296.0 Elo)**, praised for *"More profound insights and intellectual depth"*.

### 🚀 3. Startup Pitches (`startup_pitches.json`)
Iconic pitch decks (Stripe, Airbnb, SpaceX, Figma, Uber, Notion, Slack, YouTube, Coinbase, Substack). In initial benchmarking, **Stripe** and **SpaceX** took the top ranks for clarity and solution elegance.

---

## 📊 Dataset Schema (Bring Your Own Texts)

To rank your own texts (rap battles, cold emails, ad copy, philosophical essays), save a JSON file with:

```json
[
  {
    "id": "unique_id_01",
    "title": "Short Title",
    "content": "The actual text body to be evaluated by Jev...",
    "metadata": {
      "author": "Optional Author",
      "year": 2026
    }
  }
]
```
The dashboard and engine will automatically detect it and adjust evaluation prompts dynamically.

---

## 🔒 Security Notice

Your `.env` and SQLite database files (`*.db`) are strictly ignored via `.gitignore` and are never committed to version control. Only `.env.example` is pushed to GitHub.
