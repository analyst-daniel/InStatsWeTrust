from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from app.dashboard.common import build_match_overview, filter_snapshots, load_discovery_events
from app.live_state.cache import LiveStateCache
from app.live_state.football_research import FootballResearchStore
from app.live_state.matcher import LiveStateMatcher
from app.normalize.normalizer import normalize_events
from app.strategy.spread_confirmation_reporting import build_spread_debug_rows
from app.strategy.spread_confirmation_runtime import SpreadConfirmationRuntime
from app.utils.config import load_settings, resolve_path


settings = load_settings()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", type=float, default=3.0)
    args = parser.parse_args()
    console = Console()
    with Live(render(), console=console, refresh_per_second=1, screen=False) as live:
        while True:
            live.update(render())
            time.sleep(args.refresh)


def read_table(name: str) -> pd.DataFrame:
    db_path = resolve_path(settings["storage"]["sqlite_path"])
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as conn:
        try:
            return pd.read_sql_query(f"SELECT * FROM {name}", conn)
        except Exception:
            return pd.DataFrame()


def render() -> Group:
    raw_snapshots = read_table("snapshots")
    snapshots = filter_snapshots(settings, raw_snapshots)
    trades = read_table("trades")
    events = load_discovery_events(settings)
    matches = build_match_overview(settings, events, snapshots)
    normalized_markets = normalize_events(events) if events else []
    markets_by_key = {(market.event_id, market.market_id): market for market in normalized_markets}
    live_cache = LiveStateCache(resolve_path(settings["storage"]["live_state_json"]))
    matcher = LiveStateMatcher(
        live_cache,
        max_age_seconds=int(
            settings.get("validation", {}).get(
                "trade_live_state_max_age_seconds",
                settings.get("dashboard", {}).get("live_state_max_age_seconds", 90),
            )
        ),
    )
    spread_runtime = SpreadConfirmationRuntime(
        settings,
        FootballResearchStore(
            manifest_path=resolve_path(settings["storage"]["football_research_manifest_json"]),
            raw_dir=resolve_path(settings["storage"]["raw_dir"]),
        ),
    )
    latest = pd.DataFrame()
    if not snapshots.empty:
        latest = snapshots.sort_values("timestamp_utc", ascending=False).drop_duplicates(
            subset=["event_id", "market_id", "token_id", "side"],
            keep="first",
        )
    spread_debug = (
        build_spread_debug_rows(
            latest,
            markets_by_key,
            matcher,
            spread_runtime,
            parse_dt=parse_dt,
            to_float=to_float,
            to_optional_float=to_optional_float,
            to_bool=to_bool,
        )
        if not latest.empty
        else pd.DataFrame()
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    live_count = 0 if matches.empty else len(matches[(matches["live"] == True) & (matches["ended"] == False)])
    live75_count = 0 if matches.empty else len(matches[(matches["live"] == True) & (matches["ended"] == False) & (pd.to_numeric(matches["match_minute"], errors="coerce") >= 75)])
    return Group(
        Panel(f"Polymarket Self Hosted | {now}", style="bold cyan"),
        status_panel(events, matches, raw_snapshots, snapshots, live_count, live75_count),
        open_trades_table(trades),
        live75_table(matches),
        started_table(matches),
        pregame_table(matches),
        candidates_table(snapshots),
        spread_debug_table(spread_debug),
    )


def status_panel(
    events: list[dict],
    matches: pd.DataFrame,
    raw_snapshots: pd.DataFrame,
    filtered_snapshots: pd.DataFrame,
    live_count: int,
    live75_count: int,
) -> Panel:
    latest_snapshot = ""
    if not raw_snapshots.empty and "timestamp_utc" in raw_snapshots:
        latest_snapshot = str(raw_snapshots["timestamp_utc"].max())
    text = (
        f"events={len(events)} | soccer_matches={len(matches)} | live={live_count} | live75={live75_count} | "
        f"fresh_candidates={len(filtered_snapshots)} | raw_snapshots={len(raw_snapshots)} | latest_snapshot={latest_snapshot or 'none'}"
    )
    return Panel(text, title="Scanner Health", style="green")


def open_trades_table(trades: pd.DataFrame) -> Table:
    table = Table(title="Open Paper Trades", expand=True)
    for col in ["event", "bet", "entry", "minute", "score", "status"]:
        table.add_column(col)
    if trades.empty or "status" not in trades:
        table.add_row("empty", "", "", "", "", "")
        return table
    rows = trades[trades["status"] == "open"].copy()
    if rows.empty:
        table.add_row("empty", "", "", "", "", "")
        return table
    for _, row in rows.sort_values("entry_timestamp", ascending=False).head(8).iterrows():
        table.add_row(
            str(row.get("event_title", ""))[:38],
            str(row.get("side", ""))[:20],
            str(row.get("entry_price", "")),
            str(row.get("elapsed", "")),
            str(row.get("score", "")),
            str(row.get("status", "")),
        )
    return table


def live75_table(matches: pd.DataFrame) -> Table:
    table = match_table("Live Matches 75+")
    if matches.empty:
        table.add_row("empty", "", "", "", "", "")
        return table
    rows = matches[(matches["live"] == True) & (matches["ended"] == False) & (pd.to_numeric(matches["match_minute"], errors="coerce") >= 75)]
    add_match_rows(table, rows.sort_values("match_minute", ascending=False).head(10))
    return table


def started_table(matches: pd.DataFrame) -> Table:
    table = match_table("Live Matches Started")
    if matches.empty:
        table.add_row("empty", "", "", "", "", "")
        return table
    rows = matches[(matches["live"] == True) & (matches["ended"] == False) & (pd.to_numeric(matches["match_minute"], errors="coerce") < 75)]
    add_match_rows(table, rows.sort_values("match_minute", ascending=False).head(10))
    return table


def pregame_table(matches: pd.DataFrame) -> Table:
    table = match_table("Pregame Next 30 Min")
    if matches.empty:
        table.add_row("empty", "", "", "", "", "")
        return table
    minutes = pd.to_numeric(matches["minutes_to_start"], errors="coerce")
    rows = matches[(matches["live"] == False) & (minutes >= 0) & (minutes <= 30)]
    add_match_rows(table, rows.sort_values("minutes_to_start", ascending=True).head(10))
    return table


def match_table(title: str) -> Table:
    table = Table(title=title, expand=True)
    for col in ["event", "minute", "score", "period", "markets", "candidates"]:
        table.add_column(col)
    return table


def add_match_rows(table: Table, rows: pd.DataFrame) -> None:
    if rows.empty:
        table.add_row("empty", "", "", "", "", "")
        return
    for _, row in rows.iterrows():
        table.add_row(
            str(row.get("event_title", ""))[:42],
            str(row.get("match_minute", "")),
            str(row.get("score", "")),
            str(row.get("period", "")),
            str(row.get("market_count", "")),
            str(row.get("candidate_count_95_99", "")),
        )


def candidates_table(snapshots: pd.DataFrame) -> Table:
    table = Table(title="Current Live Strategy Candidates", expand=True)
    for col in ["event", "bet", "ask", "minute", "score", "reason"]:
        table.add_column(col)
    if snapshots.empty:
        table.add_row("empty", "", "", "", "", "")
        return table
    latest = snapshots.sort_values("timestamp_utc", ascending=False).drop_duplicates(subset=["event_id", "market_id", "token_id", "side"], keep="first")
    for _, row in latest.head(12).iterrows():
        table.add_row(
            str(row.get("event_title", ""))[:36],
            str(row.get("side", ""))[:20],
            str(row.get("ask", "")),
            str(row.get("elapsed", "")),
            str(row.get("score", "")),
            str(row.get("reason", ""))[:30],
        )
    return table


def spread_debug_table(rows: pd.DataFrame) -> Table:
    table = Table(title="Spread Confirmation Debug", expand=True)
    for col in ["event", "decision", "line", "margin", "minute", "reason"]:
        table.add_column(col)
    if rows.empty:
        table.add_row("empty", "", "", "", "", "")
        return table
    for _, row in rows.head(12).iterrows():
        table.add_row(
            str(row.get("event_title", ""))[:36],
            str(row.get("final_decision", "")),
            f"{row.get('spread_side_type', '')} {row.get('spread_line', '')}",
            str(row.get("selected_team_margin", "")),
            str(row.get("minute", "")),
            str(row.get("rejection_reason", ""))[:40],
        )
    return table


def to_float(value: object) -> float:
    parsed = to_optional_float(value)
    return parsed if parsed is not None else 0.0


def to_optional_float(value: object) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes"}


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    main()
