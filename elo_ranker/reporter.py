import os
import sys
import time
from typing import List, Dict, Any, Optional

class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

class TerminalReporter:
    def __init__(self):
        self.start_time = time.perf_counter()

    def print_banner(self, dataset_name: str, item_count: int, model: str, concurrency: int) -> None:
        banner = f"""
{Colors.CYAN}{Colors.BOLD}╔══════════════════════════════════════════════════════════════════════════════╗
║                       ⚡ AI ELO TOURNAMENT ENGINE ⚡                         ║
║               Recursive Text Rankings powered by Jev Ultra-Fast LLM          ║
╚══════════════════════════════════════════════════════════════════════════════╝{Colors.RESET}
  {Colors.BOLD}• Dataset:{Colors.RESET}     {dataset_name} ({item_count} items)
  {Colors.BOLD}• Model:{Colors.RESET}       {model} (System One)
  {Colors.BOLD}• Concurrency:{Colors.RESET} {concurrency} async workers
  {Colors.BOLD}• Mode:{Colors.RESET}        Swiss-System Dynamic Pairing (O(N log N))
"""
        print(banner)

    def log_match(
        self,
        match_idx: int,
        round_num: int,
        item_a: Dict[str, Any],
        item_b: Dict[str, Any],
        winner_id: str,
        reason: str,
        delta_a: float,
        delta_b: float,
        new_elo_a: float,
        new_elo_b: float,
        latency_ms: float
    ) -> None:
        a_title = item_a.get("title", "Item A")[:28]
        b_title = item_b.get("title", "Item B")[:28]

        winner_title = a_title if winner_id == str(item_a["id"]) else b_title
        winner_delta = f"+{delta_a:.1f}" if winner_id == str(item_a["id"]) else f"+{delta_b:.1f}"
        winner_new_elo = new_elo_a if winner_id == str(item_a["id"]) else new_elo_b

        time_tag = f"{Colors.DIM}[{latency_ms:.0f}ms]{Colors.RESET}"
        match_tag = f"{Colors.YELLOW}[R{round_num} #{match_idx}]{Colors.RESET}"
        vs_str = f"{Colors.BOLD}{a_title}{Colors.RESET} vs {Colors.BOLD}{b_title}{Colors.RESET}"
        winner_str = f"{Colors.GREEN}Winner: {winner_title} ({winner_delta} -> {winner_new_elo:.0f}){Colors.RESET}"
        reason_str = f"{Colors.DIM}Rationale: \"{reason}\"{Colors.RESET}"

        print(f" {match_tag} {time_tag} {vs_str}")
        print(f"    ↳ {winner_str} | {reason_str}")

    def print_leaderboard(self, items: List[Dict[str, Any]], title: str = "CURRENT LEADERBOARD", limit: int = 10) -> None:
        print(f"\n{Colors.CYAN}{Colors.BOLD}─── {title} ───────────────────────────────────────────────────{Colors.RESET}")
        print(f"{Colors.BOLD}{'Rank':<5} {'Title':<35} {'Elo':<8} {'W - L - T':<12} {'Matches':<8} {'Bar'}{Colors.RESET}")
        print("─" * 78)

        top_elo = items[0]["elo"] if items else 1200.0
        min_elo = min(it["elo"] for it in items) if items else 1000.0
        spread = max(1.0, top_elo - min_elo)

        for rank, item in enumerate(items[:limit], start=1):
            t = item.get("title", f"Item {item['id']}")[:33]
            elo = item.get("elo", 1200.0)
            wins = item.get("wins", 0)
            losses = item.get("losses", 0)
            ties = item.get("ties", 0)
            matches = item.get("matches_count", 0)
            record = f"{wins}W-{losses}L-{ties}T"

            # Visual bar
            bar_len = int(((elo - min_elo) / spread) * 15) if spread > 0 else 5
            bar = "█" * max(1, bar_len) + "░" * (15 - max(1, bar_len))

            color = Colors.GREEN if rank <= 3 else (Colors.YELLOW if rank <= 7 else Colors.RESET)
            print(f"{color}{rank:<5} {t:<35} {elo:<8.1f} {record:<12} {matches:<8} [{bar}]{Colors.RESET}")
        print("─" * 78)

    def print_round_summary(self, round_num: int, match_count: int, avg_shift: float, status_msg: str) -> None:
        elapsed = time.perf_counter() - self.start_time
        print(f"\n{Colors.BLUE}{Colors.BOLD}⚡ Round {round_num} Complete!{Colors.RESET} Matches: {match_count} | Avg Rank Shift: {avg_shift:.2f} | Status: {status_msg} | Elapsed: {elapsed:.1f}s\n")
