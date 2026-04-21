from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from app.dashboard.common import build_bet_label, build_match_overview, filter_snapshots, load_discovery_events
from app.live_state.cache import LiveStateCache
from app.live_state.football_research import FootballResearchStore
from app.live_state.matcher import LiveStateMatcher
from app.normalize.models import LiveState, MarketObservation, NormalizedMarket
from app.normalize.normalizer import normalize_events
from app.strategy.goal_totals_under_calibration import summarize_goal_totals_under_trades
from app.strategy.goal_totals_under_reporting import (
    build_goal_totals_under_debug_rows,
)
from app.strategy.goal_totals_under_runtime import GoalTotalsUnderRuntime
from app.strategy.proof_of_winning_calibration import summarize_proof_of_winning_trades
from app.strategy.proof_of_winning_runtime import ProofOfWinningRuntime
from app.strategy.spread_confirmation_calibration import summarize_spread_confirmation_trades
from app.strategy.spread_confirmation_reporting import build_spread_debug_rows
from app.strategy.spread_confirmation_runtime import SpreadConfirmationRuntime
from app.utils.config import load_settings, resolve_path


ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
SETTINGS = load_settings()


def read_table(name: str) -> pd.DataFrame:
    db_path = resolve_path(SETTINGS["storage"]["sqlite_path"])
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as conn:
        try:
            if name == "snapshots":
                max_age = int(SETTINGS.get("dashboard", {}).get("snapshot_max_age_seconds", 300))
                # Keep a small margin so the dashboard can still show the latest
                # scanner state if one refresh arrives slightly late.
                since = (datetime.now(timezone.utc) - timedelta(seconds=max(max_age * 3, 300))).isoformat().replace("+00:00", "Z")
                return pd.read_sql_query(
                    "SELECT * FROM snapshots WHERE timestamp_utc >= ? ORDER BY timestamp_utc DESC",
                    conn,
                    params=(since,),
                )
            return pd.read_sql_query(f"SELECT * FROM {name}", conn)
        except Exception:
            return pd.DataFrame()


def compact_rows(df: pd.DataFrame, columns: list[str], limit: int = 50) -> list[dict]:
    if df.empty:
        return []
    safe_cols = [col for col in columns if col in df.columns]
    if not safe_cols:
        return []
    rows = df[safe_cols].head(limit).copy().astype(object).where(pd.notna(df[safe_cols].head(limit)), "")
    return json.loads(rows.to_json(orient="records"))


def sort_if_present(df: pd.DataFrame, column: str, *, ascending: bool = False) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return df
    return df.sort_values(column, ascending=ascending)


def summarize_no_play_rejections(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "reason" not in df.columns:
        return pd.DataFrame()
    grouped = (
        df.groupby("reason", dropna=False)
        .agg(
            rows=("reason", "count"),
            events=("event_id", pd.Series.nunique) if "event_id" in df.columns else ("reason", "count"),
            markets=("market_id", pd.Series.nunique) if "market_id" in df.columns else ("reason", "count"),
        )
        .reset_index()
        .rename(columns={"reason": "group"})
    )
    return grouped.sort_values(["rows", "events"], ascending=[False, False]).reset_index(drop=True)


def build_proof_debug_rows(
    latest: pd.DataFrame,
    markets_by_key: dict[tuple[str, str], NormalizedMarket],
    matcher: LiveStateMatcher,
    runtime: ProofOfWinningRuntime,
) -> pd.DataFrame:
    if latest.empty:
        return pd.DataFrame()
    rows: list[dict] = []
    for _, row in latest.iterrows():
        market = markets_by_key.get((str(row.get("event_id", "")), str(row.get("market_id", ""))))
        if market is None:
            continue
        live_state = matcher.match(market)
        if live_state is None:
            continue
        observation = MarketObservation(
            timestamp_utc=parse_dt(str(row.get("timestamp_utc", ""))) or datetime.now(timezone.utc),
            event_id=str(row.get("event_id", "")),
            event_slug=str(row.get("event_slug", "")),
            event_title=str(row.get("event_title", "")),
            market_id=str(row.get("market_id", "")),
            market_slug=str(row.get("market_slug", "")),
            question=str(row.get("question", "")),
            token_id=str(row.get("token_id", "")),
            side=str(row.get("side", "")),
            price=to_float(row.get("price")),
            bid=to_optional_float(row.get("bid")),
            ask=to_optional_float(row.get("ask")),
            spread=to_optional_float(row.get("spread")),
            liquidity=to_optional_float(row.get("liquidity")),
            last_trade_price=to_optional_float(row.get("last_trade_price")),
            sport=str(row.get("sport", "")),
            live=to_bool(row.get("live")),
            ended=to_bool(row.get("ended")),
            score=str(row.get("score", "")),
            period=str(row.get("period", "")),
            elapsed=to_optional_float(row.get("elapsed")),
            reason=str(row.get("reason", "")),
        )
        evaluation = runtime.evaluate(market, observation, live_state)
        if not evaluation.applies:
            continue
        payload = evaluation.payload
        rows.append(
            {
                "timestamp_utc": row.get("timestamp_utc", ""),
                "event_title": row.get("event_title", ""),
                "question": row.get("question", ""),
                "side": row.get("side", ""),
                "final_decision": "ENTER" if evaluation.enter else "NO ENTER",
                "rejection_reason": "" if evaluation.enter else evaluation.reason,
                "minute": payload.minute if payload else "",
                "score": payload.score if payload else row.get("score", ""),
                "goal_difference": payload.goal_difference if payload else "",
                "effective_goal_difference": round(payload.effective_goal_difference, 3) if payload and payload.effective_goal_difference is not None else "",
                "shots_last_10": payload.shots_last_10 if payload else "",
                "shots_on_target_last_10": payload.shots_on_target_last_10 if payload else "",
                "corners_last_10": payload.corners_last_10 if payload else "",
                "dangerous_attacks_last_10": payload.dangerous_attacks_last_10 if payload else "",
                "pressure_trend_last_10": str(payload.pressure_trend_last_10.value if payload else ""),
                "tempo_change_last_10": str(payload.tempo_change_last_10.value if payload else ""),
                "goal_in_last_3min": bool(payload.goal_in_last_3min) if payload else False,
                "red_card_in_last_10min": bool(payload.red_card_in_last_10min) if payload else False,
                "stable_for_2_snapshots": bool(payload.stable_for_2_snapshots) if payload else False,
                "stable_for_3_snapshots": bool(payload.stable_for_3_snapshots) if payload else False,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("timestamp_utc", ascending=False)


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


def dashboard_state() -> dict:
    raw_snapshots = read_table("snapshots")
    snapshots = filter_snapshots(SETTINGS, raw_snapshots)
    trades = read_table("trades")
    events = load_discovery_events(SETTINGS)
    matches = build_match_overview(SETTINGS, events, snapshots) if events else pd.DataFrame()
    normalized_markets = normalize_events(events) if events else []
    markets_by_key = {(market.event_id, market.market_id): market for market in normalized_markets}
    live_cache = LiveStateCache(resolve_path(SETTINGS["storage"]["live_state_json"]))
    matcher = LiveStateMatcher(
        live_cache,
        max_age_seconds=int(
            SETTINGS.get("validation", {}).get(
                "trade_live_state_max_age_seconds",
                SETTINGS.get("dashboard", {}).get("live_state_max_age_seconds", 90),
            )
        ),
    )
    proof_runtime = ProofOfWinningRuntime(
        SETTINGS,
        FootballResearchStore(
            manifest_path=resolve_path(SETTINGS["storage"]["football_research_manifest_json"]),
            raw_dir=resolve_path(SETTINGS["storage"]["raw_dir"]),
        ),
    )
    spread_runtime = SpreadConfirmationRuntime(
        SETTINGS,
        FootballResearchStore(
            manifest_path=resolve_path(SETTINGS["storage"]["football_research_manifest_json"]),
            raw_dir=resolve_path(SETTINGS["storage"]["raw_dir"]),
        ),
    )
    goal_totals_under_runtime = GoalTotalsUnderRuntime(
        SETTINGS,
        FootballResearchStore(
            manifest_path=resolve_path(SETTINGS["storage"]["football_research_manifest_json"]),
            raw_dir=resolve_path(SETTINGS["storage"]["raw_dir"]),
        ),
    )

    if not matches.empty:
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        matches = matches[(matches["start_date_utc"].eq("")) | (matches["start_date_utc"] >= today_utc)]
        if SETTINGS.get("dashboard", {}).get("require_fresh_live_state_for_live_sections", True):
            live_mask = matches["live"] == True
            matches = matches[(~live_mask) | (matches["confirmed_by_sports_api"] == True)]

    open_trades = trades[trades["status"] == "open"].copy() if not trades.empty and "status" in trades else pd.DataFrame()
    if not open_trades.empty and SETTINGS.get("dashboard", {}).get("show_only_today_open_trades", True):
        entry_ts = pd.to_datetime(open_trades["entry_timestamp"], utc=True, errors="coerce")
        open_trades = open_trades[entry_ts.dt.strftime("%Y-%m-%d") == datetime.now(timezone.utc).strftime("%Y-%m-%d")]
    if not open_trades.empty:
        open_trades["bet_label"] = open_trades.apply(lambda row: build_bet_label(str(row.get("question", "")), str(row.get("side", ""))), axis=1)
        open_trades["entry_minute"] = pd.to_numeric(open_trades.get("elapsed", ""), errors="coerce").round(1)
        open_trades["entry_score"] = open_trades.get("score", "")

    live75 = pd.DataFrame()
    started = pd.DataFrame()
    unconfirmed_started = pd.DataFrame()
    unmatched_diagnostic = pd.DataFrame()
    pregame = pd.DataFrame()
    live_event_ids: set[str] = set()
    if not matches.empty:
        minute = pd.to_numeric(matches["match_minute"], errors="coerce")
        minutes_to_start = pd.to_numeric(matches["minutes_to_start"], errors="coerce")
        live = (matches["live"] == True) & (matches["ended"] == False)
        live75 = matches[live & (minute >= 75)].sort_values("match_minute", ascending=False)
        schedule_started = (
            (matches["live"] == False)
            & (matches["ended"] == False)
            & (minutes_to_start < 0)
            & (minutes_to_start >= -20)
        )
        diagnostic_unmatched = (
            (matches["live"] == False)
            & (matches["ended"] == False)
            & (minutes_to_start < -20)
            & (minutes_to_start >= -180)
        )
        started = matches[live & (minute < 75)].copy()
        if not started.empty:
            started = started.copy()
            started["confirmed_match_minute"] = pd.to_numeric(started.get("match_minute", ""), errors="coerce").round(1)
            started["time_source"] = "sports_api_confirmed"
            started["live_source"] = started.apply(
                lambda row: "sports_api" if bool(row.get("confirmed_by_sports_api")) else "polymarket_start_time_unconfirmed",
                axis=1,
            )
            started = started.sort_values(["confirmed_by_sports_api", "match_minute", "minutes_to_start"], ascending=[False, False, True])
        unconfirmed_started = matches[schedule_started].copy()
        if not unconfirmed_started.empty:
            unconfirmed_started["live_source"] = "polymarket_start_time_unconfirmed"
            unconfirmed_started["time_source"] = "polymarket_start_time"
            unconfirmed_started["confirmed_match_minute"] = ""
            unconfirmed_started["status_note"] = "waiting_for_live_api_no_trade"
            unconfirmed_started = unconfirmed_started.sort_values("minutes_to_start", ascending=True)
        unmatched_diagnostic = matches[diagnostic_unmatched].copy()
        if not unmatched_diagnostic.empty:
            unmatched_diagnostic["live_source"] = "polymarket_start_time_unconfirmed"
            unmatched_diagnostic["time_source"] = "polymarket_start_time"
            unmatched_diagnostic["confirmed_match_minute"] = ""
            unmatched_diagnostic["diagnostic_reason"] = "no_sports_api_match_after_20min"
            unmatched_diagnostic = unmatched_diagnostic.sort_values("minutes_to_start", ascending=True)
        pregame = matches[(matches["live"] == False) & (minutes_to_start >= 0) & (minutes_to_start <= 30)].copy()
        if not pregame.empty:
            pregame["time_source"] = "polymarket_start_time"
            pregame["confirmed_match_minute"] = ""
            pregame = pregame.sort_values("minutes_to_start")
        if "event_id" in matches:
            live_event_ids = set(matches[live]["event_id"].astype(str))

    latest = pd.DataFrame()
    if not snapshots.empty:
        if live_event_ids and "event_id" in snapshots:
            snapshots = snapshots[snapshots["event_id"].astype(str).isin(live_event_ids)]
        latest = snapshots.sort_values("timestamp_utc", ascending=False).drop_duplicates(
            subset=["event_id", "market_id", "token_id", "side"],
            keep="first",
        )
        latest = latest.copy()
        if not matches.empty and "event_id" in latest and "event_id" in matches:
            league_map = matches[["event_id", "league"]].drop_duplicates()
            latest = latest.merge(league_map, on="event_id", how="left")
        latest["match_minute"] = pd.to_numeric(latest.get("elapsed", ""), errors="coerce").round(1)
        latest["bet_label"] = latest.apply(lambda row: build_bet_label(str(row.get("question", "")), str(row.get("side", ""))), axis=1)

    no_play_latest = pd.DataFrame()
    no_play_summary = pd.DataFrame()
    no_play_source = snapshots if not snapshots.empty else raw_snapshots
    if not no_play_source.empty and "reason" in no_play_source.columns:
        no_play_rows = no_play_source[
            no_play_source["reason"].astype(str).str.startswith("snapshot_only_no_play_", na=False)
        ].copy()
        if not no_play_rows.empty:
            no_play_rows["match_minute"] = pd.to_numeric(no_play_rows.get("elapsed", ""), errors="coerce").round(1)
            if "event_id" in no_play_rows.columns and not matches.empty and "event_id" in matches.columns:
                league_map = matches[["event_id", "league"]].drop_duplicates()
                no_play_rows = no_play_rows.merge(league_map, on="event_id", how="left")
            no_play_rows["bet_label"] = no_play_rows.apply(
                lambda row: build_bet_label(str(row.get("question", "")), str(row.get("side", ""))),
                axis=1,
            )
            no_play_latest = no_play_rows.sort_values("timestamp_utc", ascending=False).drop_duplicates(
                subset=["event_id", "market_id", "token_id", "side"],
                keep="first",
            )
            no_play_summary = summarize_no_play_rejections(no_play_rows)

    resolved = trades[trades["status"] != "open"] if not trades.empty and "status" in trades else pd.DataFrame()
    if not resolved.empty:
        resolved = resolved.copy()
        resolved["bet_label"] = resolved.apply(lambda row: build_bet_label(str(row.get("question", "")), str(row.get("side", ""))), axis=1)
        resolved["entry_minute"] = pd.to_numeric(resolved.get("elapsed", ""), errors="coerce").round(1)
        resolved["entry_score"] = resolved.get("score", "")
        resolved["win"] = pd.to_numeric(resolved.get("pnl_usd", ""), errors="coerce").map(lambda value: "WIN" if value > 0 else "")
        resolved["loss"] = pd.to_numeric(resolved.get("pnl_usd", ""), errors="coerce").map(lambda value: "LOSS" if value < 0 else "")
    trade_summary = summarize_trades(trades)
    proof_debug = build_proof_debug_rows(latest, markets_by_key, matcher, proof_runtime) if not latest.empty else pd.DataFrame()
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
    goal_totals_under_debug = (
        build_goal_totals_under_debug_rows(
            latest,
            markets_by_key,
            matcher,
            goal_totals_under_runtime,
            parse_dt=parse_dt,
            to_float=to_float,
            to_optional_float=to_optional_float,
            to_bool=to_bool,
        )
        if not latest.empty
        else pd.DataFrame()
    )
    calibration = summarize_proof_of_winning_trades(trades)
    spread_calibration = summarize_spread_confirmation_trades(trades)
    goal_totals_under_calibration = summarize_goal_totals_under_trades(trades)
    latest_snapshot = ""
    if not raw_snapshots.empty and "timestamp_utc" in raw_snapshots:
        latest_snapshot = str(raw_snapshots["timestamp_utc"].max())

    match_cols = [
        "event_title",
        "league",
        "league_source",
        "start_time_utc",
        "minutes_to_start",
        "score",
        "period",
        "match_minute",
        "confirmed_match_minute",
        "live_update_age_sec",
        "time_source",
        "market_count",
        "spread_markets",
        "total_markets",
        "match_markets",
        "candidate_count_95_99",
        "latest_candidate",
        "live_source",
    ]
    trade_cols = [
        "entry_timestamp",
        "event_title",
        "question",
        "bet_label",
        "side",
        "entry_price",
        "stake_usd",
        "shares",
        "entry_minute",
        "entry_score",
        "period",
        "entry_reason",
        "first_hit_99_at",
        "first_hit_999_at",
        "max_favorable_price",
        "status",
    ]
    candidate_cols = [
        "timestamp_utc",
        "event_title",
        "league",
        "question",
        "bet_label",
        "side",
        "price",
        "bid",
        "ask",
        "spread",
        "score",
        "period",
        "match_minute",
        "reason",
    ]
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "health": {
            "events": len(events),
            "soccer_matches": len(matches),
            "live": len(started) + len(live75),
            "live75": len(live75),
            "unconfirmed_started": len(unconfirmed_started),
            "unmatched": len(unmatched_diagnostic),
            "fresh_candidates": len(latest),
            "raw_snapshots": len(raw_snapshots),
            "latest_snapshot": latest_snapshot,
            "open_trades": len(open_trades),
            "resolved": len(resolved),
            "no_play_rejections": len(no_play_latest),
            "pnl_usd": trade_summary["pnl_usd"],
            "win_rate": trade_summary["win_rate"],
        },
        "trade_summary": trade_summary,
        "open_trades": compact_rows(sort_if_present(open_trades, "entry_timestamp", ascending=False), trade_cols, 25),
        "resolved_trades": compact_rows(sort_if_present(resolved, "resolved_at", ascending=False), ["win", "loss"] + trade_cols + ["resolved_at", "result", "pnl_usd"], 40),
        "live75": compact_rows(live75, match_cols, 30),
        "started": compact_rows(started, match_cols, 30),
        "unconfirmed_started": compact_rows(unconfirmed_started, match_cols + ["status_note"], 50),
        "unmatched_diagnostic": compact_rows(unmatched_diagnostic, match_cols + ["diagnostic_reason"], 80),
        "pregame": compact_rows(pregame, match_cols, 30),
        "candidates": compact_rows(latest, candidate_cols, 80),
        "no_play_summary": compact_rows(no_play_summary, ["group", "rows", "events", "markets"], 20),
        "no_play_rejections": compact_rows(
            no_play_latest,
            [
                "timestamp_utc",
                "event_title",
                "league",
                "question",
                "bet_label",
                "side",
                "price",
                "score",
                "period",
                "match_minute",
                "reason",
            ],
            80,
        ),
        "proof_debug": compact_rows(
            proof_debug,
            [
                "timestamp_utc",
                "event_title",
                "question",
                "side",
                "final_decision",
                "rejection_reason",
                "minute",
                "score",
                "goal_difference",
                "effective_goal_difference",
                "shots_last_10",
                "shots_on_target_last_10",
                "corners_last_10",
                "dangerous_attacks_last_10",
                "pressure_trend_last_10",
                "tempo_change_last_10",
                "goal_in_last_3min",
                "red_card_in_last_10min",
                "stable_for_2_snapshots",
                "stable_for_3_snapshots",
            ],
            80,
        ),
        "spread_debug": compact_rows(
            spread_debug,
            [
                "timestamp_utc",
                "event_title",
                "question",
                "side",
                "final_decision",
                "rejection_reason",
                "minute",
                "score",
                "spread_line",
                "spread_side_type",
                "selected_team_margin",
                "goal_difference",
                "leader_shots_last_10",
                "leader_shots_on_target_last_10",
                "leader_dangerous_attacks_last_10",
                "leader_corners_last_10",
                "underdog_shots_last_10",
                "underdog_shots_on_target_last_10",
                "underdog_dangerous_attacks_last_10",
                "underdog_corners_last_10",
                "leader_pressure_trend_last_10",
                "underdog_pressure_trend_last_10",
                "shots_trend_last_10",
                "dangerous_attacks_trend_last_10",
                "tempo_change_last_10",
                "goal_in_last_3min",
                "goal_in_last_5min",
                "red_card_in_last_10min",
                "stable_for_2_snapshots",
                "stable_for_3_snapshots",
            ],
            80,
        ),
        "goal_totals_under_debug": compact_rows(
            goal_totals_under_debug,
            [
                "timestamp_utc",
                "event_title",
                "question",
                "side",
                "final_decision",
                "rejection_reason",
                "minute",
                "score",
                "total_line",
                "total_goals",
                "goal_buffer",
                "shots_last_10",
                "shots_on_target_last_10",
                "attacks_last_10",
                "dangerous_attacks_last_10",
                "corners_last_10",
                "total_shots_both_last_10",
                "total_dangerous_attacks_both_last_10",
                "total_corners_both_last_10",
                "pressure_trend_last_10",
                "shots_trend_last_10",
                "dangerous_attacks_trend_last_10",
                "tempo_change_last_10",
                "goal_in_last_3min",
                "goal_in_last_5min",
                "red_card_in_last_10min",
                "stable_for_2_snapshots",
                "stable_for_3_snapshots",
            ],
            80,
        ),
        "goal_totals_under_calibration_summary": goal_totals_under_calibration.summary,
        "goal_totals_under_calibration_line": compact_rows(
            goal_totals_under_calibration.by_line,
            ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
            20,
        ),
        "goal_totals_under_calibration_entry_bucket": compact_rows(
            goal_totals_under_calibration.by_entry_bucket,
            ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
            20,
        ),
        "goal_totals_under_calibration_league": compact_rows(
            goal_totals_under_calibration.by_league,
            ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"],
            20,
        ),
        "goal_totals_under_calibration_reason": compact_rows(
            goal_totals_under_calibration.by_reason,
            ["group", "trades", "wins", "losses", "pnl_usd"],
            20,
        ),
        "proof_of_winning_calibration_summary": calibration.summary,
        "proof_calibration_market_type": compact_rows(calibration.by_market_type, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
        "proof_calibration_entry_bucket": compact_rows(calibration.by_entry_bucket, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
        "proof_calibration_league": compact_rows(calibration.by_league, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
        "spread_confirmation_calibration_summary": spread_calibration.summary,
        "spread_calibration_line": compact_rows(spread_calibration.by_line, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
        "spread_calibration_side_type": compact_rows(spread_calibration.by_side_type, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
        "spread_calibration_entry_bucket": compact_rows(spread_calibration.by_entry_bucket, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
        "spread_calibration_league": compact_rows(spread_calibration.by_league, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
    }


def summarize_trades(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "total_trades": 0,
            "open_trades": 0,
            "resolved_trades": 0,
            "wins": 0,
            "losses": 0,
            "pushes": 0,
            "stale_closed": 0,
            "stake_usd": 0.0,
            "pnl_usd": 0.0,
            "win_rate": "",
        }
    status = trades.get("status", pd.Series(dtype=str)).astype(str)
    pnl = pd.to_numeric(trades.get("pnl_usd", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    stake = pd.to_numeric(trades.get("stake_usd", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    resolved_mask = status == "resolved"
    wins = int((resolved_mask & (pnl > 0)).sum())
    losses = int((resolved_mask & (pnl < 0)).sum())
    pushes = int((resolved_mask & (pnl == 0)).sum())
    resolved_count = int((status != "open").sum())
    graded = wins + losses
    return {
        "total_trades": int(len(trades)),
        "open_trades": int((status == "open").sum()),
        "resolved_trades": resolved_count,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "stale_closed": int((status == "stale_closed").sum()),
        "stake_usd": round(float(stake.sum()), 2),
        "pnl_usd": round(float(pnl.sum()), 2),
        "win_rate": f"{round((wins / graded) * 100, 1)}%" if graded else "",
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self.send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self.send_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self.send_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/state":
            self.send_json(dashboard_state())
            return
        self.send_error(404)

    def send_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"JS dashboard: http://{host}:{port}")
    server.serve_forever()
