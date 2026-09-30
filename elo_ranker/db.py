import sqlite3
import json
import time
from typing import List, Dict, Any, Set, Tuple, Optional
from .trueskill_engine import DEFAULT_MU, DEFAULT_SIGMA, calculate_ordinal, to_scaled_rating

class Database:
    def __init__(self, db_path: str = "elo_tournament.db"):
        self.db_path = db_path
        self._shared_conn = None
        if db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:")
            self._shared_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")  # Fast concurrent reads/writes
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn


    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    elo REAL NOT NULL DEFAULT 1200.0,
                    mu REAL NOT NULL DEFAULT 25.0,
                    sigma REAL NOT NULL DEFAULT 8.333333333333334,
                    ordinal REAL NOT NULL DEFAULT 0.0,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    ties INTEGER NOT NULL DEFAULT 0,
                    matches_count INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT
                );
            """)

            # Safe migrations if existing database table is missing columns
            cursor = conn.execute("PRAGMA table_info(items);")
            columns = [row["name"] for row in cursor.fetchall()]
            if "mu" not in columns:
                conn.execute("ALTER TABLE items ADD COLUMN mu REAL NOT NULL DEFAULT 25.0;")
            if "sigma" not in columns:
                conn.execute("ALTER TABLE items ADD COLUMN sigma REAL NOT NULL DEFAULT 8.333333333333334;")
            if "ordinal" not in columns:
                conn.execute("ALTER TABLE items ADD COLUMN ordinal REAL NOT NULL DEFAULT 0.0;")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_num INTEGER NOT NULL,
                    item_a_id TEXT NOT NULL,
                    item_b_id TEXT NOT NULL,
                    winner_id TEXT NOT NULL,
                    reason TEXT,
                    confidence REAL,
                    elo_a_before REAL NOT NULL,
                    elo_b_before REAL NOT NULL,
                    elo_a_after REAL NOT NULL,
                    elo_b_after REAL NOT NULL,
                    delta_a REAL NOT NULL,
                    delta_b REAL NOT NULL,
                    latency_ms REAL,
                    model_name TEXT,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(item_a_id) REFERENCES items(id),
                    FOREIGN KEY(item_b_id) REFERENCES items(id)
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS cohort_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_num INTEGER NOT NULL,
                    participants_json TEXT NOT NULL,
                    ranks_json TEXT NOT NULL,
                    winner_id TEXT NOT NULL,
                    reason TEXT,
                    confidence REAL,
                    latency_ms REAL,
                    model_name TEXT,
                    created_at REAL NOT NULL
                );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_items_elo ON items(elo DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_items_ordinal ON items(ordinal DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_round ON matches(round_num);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_pair ON matches(item_a_id, item_b_id);")

    def seed_items(self, items: List[Dict[str, Any]], default_elo: float = 1200.0, reset: bool = False) -> None:
        with self._get_connection() as conn:
            if reset:
                conn.execute("DELETE FROM matches;")
                conn.execute("DELETE FROM cohort_matches;")
                conn.execute("DELETE FROM items;")
            
            for item in items:
                item_id = str(item["id"])
                title = item.get("title", f"Item {item_id}")
                content = item.get("content", "")
                metadata = json.dumps(item.get("metadata", {}))
                mu = float(item.get("mu", DEFAULT_MU))
                sigma = float(item.get("sigma", DEFAULT_SIGMA))
                ordinal = calculate_ordinal(mu, sigma)

                conn.execute("""
                    INSERT INTO items (id, title, content, elo, mu, sigma, ordinal, wins, losses, ties, matches_count, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, ?)
                    ON CONFLICT(id) DO NOTHING;
                """, (item_id, title, content, default_elo, mu, sigma, ordinal, metadata))

    def get_items(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM items ORDER BY elo DESC;")
            return [dict(row) for row in cursor.fetchall()]

    def get_played_pairs(self) -> Set[Tuple[str, str]]:
        """Returns set of (min_id, max_id) for all previously played 1v1 pairings."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT item_a_id, item_b_id FROM matches;")
            pairs = set()
            for row in cursor.fetchall():
                a, b = row["item_a_id"], row["item_b_id"]
                pair = (min(a, b), max(a, b))
                pairs.add(pair)
            return pairs

    def get_played_cohorts(self) -> Set[Tuple[str, ...]]:
        """Returns set of sorted tuple participant IDs for previous multi-candidate cohorts."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT participants_json FROM cohort_matches;")
            cohorts = set()
            for row in cursor.fetchall():
                try:
                    p = tuple(sorted(json.loads(row["participants_json"])))
                    cohorts.add(p)
                except Exception:
                    pass
            return cohorts

    def record_match(
        self,
        round_num: int,
        item_a_id: str,
        item_b_id: str,
        winner_id: str,
        reason: str,
        confidence: float,
        elo_a_before: float,
        elo_b_before: float,
        elo_a_after: float,
        elo_b_after: float,
        delta_a: float,
        delta_b: float,
        latency_ms: float = 0.0,
        model_name: str = "jev-latest",
        mu_a: Optional[float] = None,
        sigma_a: Optional[float] = None,
        mu_b: Optional[float] = None,
        sigma_b: Optional[float] = None,
    ) -> None:
        with self._get_connection() as conn:
            # 1. Insert 1v1 match
            conn.execute("""
                INSERT INTO matches (
                    round_num, item_a_id, item_b_id, winner_id, reason,
                    confidence, elo_a_before, elo_b_before, elo_a_after, elo_b_after,
                    delta_a, delta_b, latency_ms, model_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                round_num, item_a_id, item_b_id, winner_id, reason,
                confidence, elo_a_before, elo_b_before, elo_a_after, elo_b_after,
                delta_a, delta_b, latency_ms, model_name, time.time()
            ))

            # 2. Update contestant A
            is_win_a = 1 if winner_id == item_a_id else 0
            is_loss_a = 1 if (winner_id == item_b_id and winner_id != "TIE") else 0
            is_tie_a = 1 if winner_id == "TIE" else 0

            if mu_a is not None and sigma_a is not None:
                ord_a = calculate_ordinal(mu_a, sigma_a)
                conn.execute("""
                    UPDATE items
                    SET elo = ?,
                        mu = ?,
                        sigma = ?,
                        ordinal = ?,
                        wins = wins + ?,
                        losses = losses + ?,
                        ties = ties + ?,
                        matches_count = matches_count + 1
                    WHERE id = ?;
                """, (elo_a_after, mu_a, sigma_a, ord_a, is_win_a, is_loss_a, is_tie_a, item_a_id))
            else:
                conn.execute("""
                    UPDATE items
                    SET elo = ?,
                        wins = wins + ?,
                        losses = losses + ?,
                        ties = ties + ?,
                        matches_count = matches_count + 1
                    WHERE id = ?;
                """, (elo_a_after, is_win_a, is_loss_a, is_tie_a, item_a_id))

            # 3. Update contestant B
            is_win_b = 1 if winner_id == item_b_id else 0
            is_loss_b = 1 if (winner_id == item_a_id and winner_id != "TIE") else 0
            is_tie_b = 1 if winner_id == "TIE" else 0

            if mu_b is not None and sigma_b is not None:
                ord_b = calculate_ordinal(mu_b, sigma_b)
                conn.execute("""
                    UPDATE items
                    SET elo = ?,
                        mu = ?,
                        sigma = ?,
                        ordinal = ?,
                        wins = wins + ?,
                        losses = losses + ?,
                        ties = ties + ?,
                        matches_count = matches_count + 1
                    WHERE id = ?;
                """, (elo_b_after, mu_b, sigma_b, ord_b, is_win_b, is_loss_b, is_tie_b, item_b_id))
            else:
                conn.execute("""
                    UPDATE items
                    SET elo = ?,
                        wins = wins + ?,
                        losses = losses + ?,
                        ties = ties + ?,
                        matches_count = matches_count + 1
                    WHERE id = ?;
                """, (elo_b_after, is_win_b, is_loss_b, is_tie_b, item_b_id))

    def record_cohort_match(
        self,
        round_num: int,
        cohort_results: List[Dict[str, Any]],
        winner_id: str,
        reason: str,
        confidence: float,
        latency_ms: float = 0.0,
        model_name: str = "trueskill-judge",
    ) -> None:
        """
        Records an N-candidate TrueSkill cohort match and updates Bayesian ratings for all participants.
        cohort_results: output from trueskill_engine.update_trueskill_multi()
        """
        participants = [r["id"] for r in cohort_results]
        ranks = [r["rank"] for r in cohort_results]

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO cohort_matches (
                    round_num, participants_json, ranks_json, winner_id,
                    reason, confidence, latency_ms, model_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                round_num, json.dumps(participants), json.dumps(ranks),
                winner_id, reason, confidence, latency_ms, model_name, time.time()
            ))

            for r in cohort_results:
                item_id = r["id"]
                new_mu = r["new_mu"]
                new_sigma = r["new_sigma"]
                ordinal = r["ordinal"]
                scaled_elo = r["scaled_rating"]
                is_win = 1 if r["rank"] == 1 else 0
                is_loss = 1 if r["rank"] > 1 else 0

                conn.execute("""
                    UPDATE items
                    SET elo = ?,
                        mu = ?,
                        sigma = ?,
                        ordinal = ?,
                        wins = wins + ?,
                        losses = losses + ?,
                        matches_count = matches_count + 1
                    WHERE id = ?;
                """, (scaled_elo, new_mu, new_sigma, ordinal, is_win, is_loss, item_id))

    def get_leaderboard(self, limit: Optional[int] = None, sort_by: str = "elo") -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            order_col = "ordinal" if sort_by == "ordinal" else "elo"
            query = f"SELECT * FROM items ORDER BY {order_col} DESC"
            if limit:
                query += f" LIMIT {int(limit)}"
            cursor = conn.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def get_match_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT m.*, 
                       ia.title AS item_a_title, 
                       ib.title AS item_b_title
                FROM matches m
                JOIN items ia ON m.item_a_id = ia.id
                JOIN items ib ON m.item_b_id = ib.id
                ORDER BY m.id DESC
                LIMIT ?;
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_tournament_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            total_items = conn.execute("SELECT COUNT(*) FROM items;").fetchone()[0]
            total_1v1_matches = conn.execute("SELECT COUNT(*) FROM matches;").fetchone()[0]
            total_cohort_matches = conn.execute("SELECT COUNT(*) FROM cohort_matches;").fetchone()[0]
            avg_elo = conn.execute("SELECT AVG(elo) FROM items;").fetchone()[0] or 1200.0
            avg_latency = conn.execute("SELECT AVG(latency_ms) FROM matches;").fetchone()[0] or 0.0
            return {
                "total_items": total_items,
                "total_matches": total_1v1_matches + total_cohort_matches,
                "total_1v1_matches": total_1v1_matches,
                "total_cohort_matches": total_cohort_matches,
                "avg_elo": round(avg_elo, 1),
                "avg_latency_ms": round(avg_latency, 1),
            }
