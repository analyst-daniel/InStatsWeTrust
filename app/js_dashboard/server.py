from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

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
from app.strategy.proof_of_winning_calibration import entry_bucket, infer_league
from app.strategy.proof_of_winning_runtime import ProofOfWinningRuntime
from app.strategy.spread_confirmation_calibration import summarize_spread_confirmation_trades
from app.strategy.spread_confirmation_reporting import build_spread_debug_rows
from app.strategy.spread_confirmation_runtime import SpreadConfirmationRuntime
from app.storage.trades import load_trades
from app.storage.tracked_matches import TrackedMatches
from app.utils.config import load_settings, resolve_path
from app.capital.processes import CapitalProcessManager


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


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
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


def summarize_missing_fixture_diagnostics(*frames: pd.DataFrame) -> tuple[dict[str, object], pd.DataFrame]:
    combined = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True) if any(not frame.empty for frame in frames) else pd.DataFrame()
    if combined.empty:
        return {"rows": 0, "events": 0, "questions": 0, "leagues": 0}, pd.DataFrame()
    for column in ["rejection_reason", "event_title", "league", "question"]:
        if column not in combined.columns:
            combined[column] = ""
    reason_series = combined.get("rejection_reason", pd.Series(dtype=object)).astype(str)
    filtered = combined[reason_series.str.endswith("missing_fixture_id", na=False)].copy()
    if filtered.empty:
        return {"rows": 0, "events": 0, "questions": 0, "leagues": 0}, pd.DataFrame()
    summary = {
        "rows": int(len(filtered)),
        "events": int(filtered.get("event_title", pd.Series(dtype=object)).nunique()),
        "questions": int(filtered.get("question", pd.Series(dtype=object)).nunique()),
        "leagues": int(filtered.get("league", pd.Series(dtype=object)).replace("", pd.NA).dropna().nunique()),
    }
    rows = (
        filtered.groupby(["rejection_reason", "event_title", "league", "question"], dropna=False)
        .agg(rows=("question", "count"))
        .reset_index()
        .rename(columns={"rejection_reason": "reason"})
        .sort_values(["rows", "event_title", "question"], ascending=[False, True, True])
        .reset_index(drop=True)
    )
    return summary, rows


def summarize_missing_detail_history_diagnostics(*frames: pd.DataFrame) -> tuple[dict[str, object], pd.DataFrame]:
    combined = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True) if any(not frame.empty for frame in frames) else pd.DataFrame()
    if combined.empty:
        return {"rows": 0, "events": 0, "questions": 0, "leagues": 0}, pd.DataFrame()
    for column in ["rejection_reason", "event_title", "league", "question"]:
        if column not in combined.columns:
            combined[column] = ""
    reason_series = combined.get("rejection_reason", pd.Series(dtype=object)).astype(str)
    filtered = combined[reason_series.str.endswith("missing_detail_history", na=False)].copy()
    if filtered.empty:
        return {"rows": 0, "events": 0, "questions": 0, "leagues": 0}, pd.DataFrame()
    summary = {
        "rows": int(len(filtered)),
        "events": int(filtered.get("event_title", pd.Series(dtype=object)).nunique()),
        "questions": int(filtered.get("question", pd.Series(dtype=object)).nunique()),
        "leagues": int(filtered.get("league", pd.Series(dtype=object)).replace("", pd.NA).dropna().nunique()),
    }
    rows = (
        filtered.groupby(["rejection_reason", "event_title", "league", "question"], dropna=False)
        .agg(rows=("question", "count"))
        .reset_index()
        .rename(columns={"rejection_reason": "reason"})
        .sort_values(["rows", "event_title", "question"], ascending=[False, True, True])
        .reset_index(drop=True)
    )
    return summary, rows


def infer_strategy_family(entry_reason: object, question: object) -> str:
    reason = str(entry_reason or "").lower()
    text = str(question or "").lower()
    if reason.startswith("proof_of_winning"):
        return "proof"
    if reason.startswith("spread_confirmation"):
        return "spread"
    if reason.startswith("goal_totals_under"):
        return "under"
    if "spread:" in text:
        return "spread"
    if "o/u" in text or "under" in text:
        return "under"
    if "will " in text and " win" in text:
        return "proof"
    return "other"


def infer_market_subtype(question: object, side: object) -> str:
    text = str(question or "")
    side_text = str(side or "")
    lower = text.lower()
    if "spread:" in lower:
        line = ""
        if "(" in text and ")" in text:
            line = text.split("(", 1)[1].split(")", 1)[0].strip()
        sign = "plus" if "+" in side_text or "+" in line else "minus" if "-" in side_text or "-" in line else "unknown"
        return f"spread_{sign}_{line or 'unknown'}"
    if "o/u" in lower:
        line = lower.split("o/u", 1)[1].strip().split()[0] if "o/u" in lower else "unknown"
        side_norm = "under" if side_text.lower() == "under" else "over" if side_text.lower() == "over" else "unknown"
        return f"total_{side_norm}_{line}"
    if "both teams to score" in lower or "btts" in lower:
        return f"btts_{side_text.lower() or 'unknown'}"
    if "exact score" in lower:
        return "exact_score"
    if "draw" in lower:
        return f"draw_{side_text.lower() or 'unknown'}"
    if "will " in lower and " win" in lower:
        return f"match_winner_{side_text.lower() or 'unknown'}"
    return "other"


def infer_goal_buffer(question: object, score: object, side: object) -> object:
    text = str(question or "").lower()
    score_text = str(score or "")
    try:
        home, away = [int(part.strip()) for part in score_text.split("-", 1)]
    except Exception:
        return ""
    total_goals = home + away
    if "o/u" in text and str(side or "").lower() == "under":
        try:
            line = float(text.split("o/u", 1)[1].strip().split()[0])
            return round(line - total_goals, 2)
        except Exception:
            return ""
    if "will " in text and " win" in text:
        return abs(home - away)
    return ""


def infer_price_bucket(value: object) -> str:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if price < 0.95:
        return "<0.95"
    if price < 0.96:
        return "0.95-0.959"
    if price < 0.97:
        return "0.96-0.969"
    if price < 0.98:
        return "0.97-0.979"
    if price < 0.99:
        return "0.98-0.989"
    return "0.99+"


def summarize_group(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if df.empty or group_col not in df.columns:
        return pd.DataFrame()
    grouped = (
        df.groupby(group_col, dropna=False)
        .agg(
            trades=("trade_id", "count"),
            wins=("win_flag", "sum"),
            losses=("loss_flag", "sum"),
            pnl_usd=("pnl_usd_num", "sum"),
        )
        .reset_index()
        .rename(columns={group_col: "group"})
    )
    grouped["pnl_usd"] = grouped["pnl_usd"].fillna(0.0).round(4)
    grouped["win_rate"] = grouped.apply(
        lambda row: f"{round((row['wins'] / (row['wins'] + row['losses'])) * 100, 1)}%"
        if (row["wins"] + row["losses"]) > 0
        else "",
        axis=1,
    )
    return grouped.sort_values(["trades", "pnl_usd"], ascending=[False, False]).reset_index(drop=True)


def summarize_trade_attribution(
    trades: pd.DataFrame,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if trades.empty:
        empty = pd.DataFrame()
        return (
            {"total": 0, "resolved": 0, "wins": 0, "losses": 0, "pnl_usd": 0.0, "win_rate": ""},
            empty,
            empty,
            empty,
            empty,
            empty,
            empty,
        )
    frame = trades.copy()
    frame["resolved_flag"] = frame.get("status", "").astype(str).eq("resolved")
    resolved = frame[frame["resolved_flag"]].copy()
    if resolved.empty:
        empty = pd.DataFrame()
        return (
            {"total": int(len(frame)), "resolved": 0, "wins": 0, "losses": 0, "pnl_usd": 0.0, "win_rate": ""},
            empty,
            empty,
            empty,
            empty,
            empty,
            empty,
        )
    resolved["pnl_usd_num"] = pd.to_numeric(resolved.get("pnl_usd", ""), errors="coerce").fillna(0.0)
    resolved["win_flag"] = resolved["pnl_usd_num"].gt(0)
    resolved["loss_flag"] = resolved["pnl_usd_num"].lt(0)
    resolved["strategy_family"] = resolved.apply(lambda row: infer_strategy_family(row.get("entry_reason", ""), row.get("question", "")), axis=1)
    resolved["market_subtype"] = resolved.apply(lambda row: infer_market_subtype(row.get("question", ""), row.get("side", "")), axis=1)
    resolved["league"] = resolved.get("event_slug", "").astype(str).map(infer_league)
    resolved["entry_bucket"] = resolved.get("elapsed", "").map(entry_bucket)
    resolved["price_bucket"] = resolved.get("entry_price", "").map(infer_price_bucket)
    resolved["goal_buffer"] = resolved.apply(lambda row: infer_goal_buffer(row.get("question", ""), row.get("score", ""), row.get("side", "")), axis=1)
    resolved["goal_buffer_bucket"] = resolved["goal_buffer"].map(
        lambda value: "unknown"
        if value in ("", None)
        else ("<1" if float(value) < 1 else ("1-1.49" if float(value) < 1.5 else ("1.5-1.99" if float(value) < 2 else "2+")))
    )
    wins = int(resolved["win_flag"].sum())
    losses = int(resolved["loss_flag"].sum())
    summary = {
        "total": int(len(frame)),
        "resolved": int(len(resolved)),
        "wins": wins,
        "losses": losses,
        "pnl_usd": round(float(resolved["pnl_usd_num"].sum()), 4),
        "win_rate": f"{round((wins / (wins + losses)) * 100, 1)}%" if (wins + losses) else "",
    }
    return (
        summary,
        summarize_group(resolved, "strategy_family"),
        summarize_group(resolved, "market_subtype"),
        summarize_group(resolved, "league"),
        summarize_group(resolved, "entry_bucket"),
        summarize_group(resolved, "price_bucket"),
        summarize_group(resolved, "goal_buffer_bucket"),
    )


def build_diagnostic_funnel(
    *,
    events: list[dict],
    matches: pd.DataFrame,
    raw_snapshots: pd.DataFrame,
    snapshots: pd.DataFrame,
    pregame: pd.DataFrame,
    started: pd.DataFrame,
    live75: pd.DataFrame,
    no_play_latest: pd.DataFrame,
    proof_debug: pd.DataFrame,
    spread_debug: pd.DataFrame,
    goal_totals_under_debug: pd.DataFrame,
) -> tuple[dict[str, object], pd.DataFrame]:
    soccer_events = len(matches) if not matches.empty else 0
    tracked_matches = soccer_events
    started_matches = len(started)
    live75_matches = len(live75)
    pregame_matches = len(pregame)
    raw_price_window_rows = len(raw_snapshots)
    fresh_price_window_rows = len(snapshots)
    no_play_rejected_rows = len(no_play_latest)
    proof_rows = len(proof_debug)
    proof_enter = int((proof_debug.get("final_decision", pd.Series(dtype=object)) == "ENTER").sum()) if not proof_debug.empty else 0
    spread_rows = len(spread_debug)
    spread_enter = int((spread_debug.get("final_decision", pd.Series(dtype=object)) == "ENTER").sum()) if not spread_debug.empty else 0
    under_rows = len(goal_totals_under_debug)
    under_enter = int((goal_totals_under_debug.get("final_decision", pd.Series(dtype=object)) == "ENTER").sum()) if not goal_totals_under_debug.empty else 0
    final_trade_eligible = max(proof_enter, spread_enter, under_enter, 0)

    summary = {
        "events_seen": len(events),
        "soccer_events": soccer_events,
        "tracked_matches": tracked_matches,
        "pregame_matches": pregame_matches,
        "started_matches": started_matches,
        "matches_75_plus": live75_matches,
        "raw_price_window_rows": raw_price_window_rows,
        "fresh_price_window_rows": fresh_price_window_rows,
        "no_play_rejected_rows": no_play_rejected_rows,
        "proof_rows": proof_rows,
        "proof_enter": proof_enter,
        "spread_rows": spread_rows,
        "spread_enter": spread_enter,
        "under_rows": under_rows,
        "under_enter": under_enter,
        "final_trade_eligible": final_trade_eligible,
    }
    rows = pd.DataFrame(
        [
            {"stage": "events_seen", "count": len(events), "description": "all discovery events loaded"},
            {"stage": "soccer_events", "count": soccer_events, "description": "soccer matches after event normalization"},
            {"stage": "tracked_matches", "count": tracked_matches, "description": "pregame tracked matches carried forward"},
            {"stage": "pregame_matches", "count": pregame_matches, "description": "matches starting in next 30 minutes"},
            {"stage": "started_matches", "count": started_matches, "description": "confirmed live matches started"},
            {"stage": "matches_75_plus", "count": live75_matches, "description": "live matches in 75+ window"},
            {"stage": "raw_price_window_rows", "count": raw_price_window_rows, "description": "raw live candidate rows before freshness filter"},
            {"stage": "fresh_price_window_rows", "count": fresh_price_window_rows, "description": "fresh live candidate rows shown to dashboard"},
            {"stage": "no_play_rejected_rows", "count": no_play_rejected_rows, "description": "rows rejected by no-play rules"},
            {"stage": "proof_rows", "count": proof_rows, "description": "proof of winning rows evaluated"},
            {"stage": "proof_enter", "count": proof_enter, "description": "proof of winning enter decisions"},
            {"stage": "spread_rows", "count": spread_rows, "description": "spread confirmation rows evaluated"},
            {"stage": "spread_enter", "count": spread_enter, "description": "spread confirmation enter decisions"},
            {"stage": "under_rows", "count": under_rows, "description": "goal totals under rows evaluated"},
            {"stage": "under_enter", "count": under_enter, "description": "goal totals under enter decisions"},
            {"stage": "final_trade_eligible", "count": final_trade_eligible, "description": "max enter count across strategy diagnostics"},
        ]
    )
    return summary, rows


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
                "detail_history_count": evaluation.diagnostics.get("detail_history_count", ""),
                "has_statistics": evaluation.diagnostics.get("has_statistics", False),
                "has_events": evaluation.diagnostics.get("has_events", False),
                "source_fields_present_count": evaluation.diagnostics.get("source_fields_present_count", ""),
                "source_fields_present": evaluation.diagnostics.get("source_fields_present", ""),
                "data_confidence_flag": evaluation.diagnostics.get("data_confidence_flag", False),
                "last_5_ready": evaluation.diagnostics.get("last_5_ready", False),
                "last_10_ready": evaluation.diagnostics.get("last_10_ready", False),
                "stable_snapshot_count": evaluation.diagnostics.get("stable_snapshot_count", ""),
                "confidence_reason": evaluation.diagnostics.get("confidence_reason", ""),
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
    under_buffer_exits = read_csv(resolve_path(SETTINGS["storage"].get("under_buffer_exit_csv", "data/snapshots/under_buffer_exit_log.csv")))
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
    tracked_matches = TrackedMatches(resolve_path(SETTINGS["storage"]["tracked_matches_json"]))
    capital_processes = CapitalProcessManager(SETTINGS, resolve_path(SETTINGS["storage"]["capital_processes_json"]))
    proof_runtime = ProofOfWinningRuntime(
        SETTINGS,
        FootballResearchStore(
            manifest_path=resolve_path(SETTINGS["storage"]["football_research_manifest_json"]),
            raw_dir=resolve_path(SETTINGS["storage"]["raw_dir"]),
        ),
        tracked_matches,
    )
    spread_runtime = SpreadConfirmationRuntime(
        SETTINGS,
        FootballResearchStore(
            manifest_path=resolve_path(SETTINGS["storage"]["football_research_manifest_json"]),
            raw_dir=resolve_path(SETTINGS["storage"]["raw_dir"]),
        ),
        tracked_matches,
    )
    goal_totals_under_runtime = GoalTotalsUnderRuntime(
        SETTINGS,
        FootballResearchStore(
            manifest_path=resolve_path(SETTINGS["storage"]["football_research_manifest_json"]),
            raw_dir=resolve_path(SETTINGS["storage"]["raw_dir"]),
        ),
        tracked_matches,
    )

    if not matches.empty:
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        matches = matches[(matches["start_date_utc"].eq("")) | (matches["start_date_utc"] >= today_utc)]
        if SETTINGS.get("dashboard", {}).get("require_fresh_live_state_for_live_sections", True):
            live_mask = matches["live"] == True
            matches = matches[(~live_mask) | (matches["confirmed_by_sports_api"] == True)]

    all_open_trades = trades[trades["status"] == "open"].copy() if not trades.empty and "status" in trades else pd.DataFrame()
    stale_open_trades = pd.DataFrame()
    open_trades = all_open_trades.copy()
    if not all_open_trades.empty:
        entry_ts = pd.to_datetime(all_open_trades["entry_timestamp"], utc=True, errors="coerce")
        is_today = entry_ts.dt.strftime("%Y-%m-%d") == datetime.now(timezone.utc).strftime("%Y-%m-%d")
        stale_open_trades = all_open_trades[~is_today].copy()
        if SETTINGS.get("dashboard", {}).get("show_only_today_open_trades", True):
            open_trades = all_open_trades[is_today].copy()
        for frame in (open_trades, stale_open_trades):
            if not frame.empty:
                frame["bet_label"] = frame.apply(lambda row: build_bet_label(str(row.get("question", "")), str(row.get("side", ""))), axis=1)
                frame["entry_minute"] = pd.to_numeric(frame.get("elapsed", ""), errors="coerce").round(1)
                frame["entry_score"] = frame.get("score", "")

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
        live75 = matches[live & (minute >= 70)].sort_values("match_minute", ascending=False)
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

    resolved = trades[trades["status"].astype(str) == "resolved"] if not trades.empty and "status" in trades else pd.DataFrame()
    if not resolved.empty:
        resolved = resolved.copy()
        resolved["bet_label"] = resolved.apply(lambda row: build_bet_label(str(row.get("question", "")), str(row.get("side", ""))), axis=1)
        resolved["entry_minute"] = pd.to_numeric(resolved.get("elapsed", ""), errors="coerce").round(1)
        resolved["entry_score"] = resolved.get("score", "")
        resolved["win"] = pd.to_numeric(resolved.get("pnl_usd", ""), errors="coerce").map(lambda value: "WIN" if value > 0 else "")
        resolved["loss"] = pd.to_numeric(resolved.get("pnl_usd", ""), errors="coerce").map(lambda value: "LOSS" if value < 0 else "")
    capital_summary, capital_rows = capital_processes.summary(load_trades(resolve_path(SETTINGS["storage"]["trade_csv"])))
    capital_start_balance = float(SETTINGS.get("capital_processes", {}).get("start_balance", 10.0))
    capital_usage = summarize_capital_usage(pd.DataFrame(capital_rows), start_balance=capital_start_balance)
    yesterday_capital_usage = summarize_yesterday_capital_usage(trades, start_balance=capital_start_balance)
    capital_record = update_capital_high_watermark(
        resolve_path(SETTINGS["storage"].get("capital_high_watermark_json", "data/snapshots/capital_high_watermark.json")),
        yesterday_capital_usage,
    )
    trade_summary = summarize_trades(trades) | capital_usage | yesterday_capital_usage | capital_record
    under_buffer_exit_summary, under_buffer_exit_rows = summarize_under_buffer_exit_scenario(under_buffer_exits, trades)
    trade_summary["pnl_v2_usd"] = round(
        float(trade_summary.get("pnl_usd", 0.0) or 0.0) + float(under_buffer_exit_summary.get("delta_pnl_usd", 0.0) or 0.0),
        4,
    )
    process_focus_summary, process_focus_rows = summarize_process_focus(
        pd.DataFrame(capital_rows),
        start_balance=capital_start_balance,
    )
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
    (
        attribution_summary,
        attribution_strategy,
        attribution_subtype,
        attribution_league,
        attribution_entry_bucket,
        attribution_price_bucket,
        attribution_goal_buffer,
    ) = summarize_trade_attribution(trades)
    missing_fixture_summary, missing_fixture_rows = summarize_missing_fixture_diagnostics(
        proof_debug,
        spread_debug,
        goal_totals_under_debug,
    )
    missing_detail_history_summary, missing_detail_history_rows = summarize_missing_detail_history_diagnostics(
        proof_debug,
        spread_debug,
        goal_totals_under_debug,
    )
    funnel_summary, funnel_rows = build_diagnostic_funnel(
        events=events,
        matches=matches,
        raw_snapshots=raw_snapshots,
        snapshots=snapshots,
        pregame=pregame,
        started=started,
        live75=live75,
        no_play_latest=no_play_latest,
        proof_debug=proof_debug,
        spread_debug=spread_debug,
        goal_totals_under_debug=goal_totals_under_debug,
    )
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
        "max_stake_usd_at_entry",
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
            "resolved": int((trades.get("status", pd.Series(dtype=str)).astype(str) == "resolved").sum()) if not trades.empty and "status" in trades else 0,
            "no_play_rejections": len(no_play_latest),
            "pnl_usd": trade_summary["pnl_usd"],
            "pnl_v2_usd": trade_summary["pnl_v2_usd"],
            "win_rate": trade_summary["win_rate"],
            "capital_runs": capital_usage["capital_runs"],
            "continuations": capital_usage["continuations"],
            "max_parallel_runs": capital_usage["max_parallel_runs"],
            "min_start_capital": capital_usage["min_start_capital"],
            "yday_peak_open_trades": yesterday_capital_usage["yday_peak_open_trades"],
            "yday_peak_stake_locked": yesterday_capital_usage["yday_peak_stake_locked"],
            "yday_min_capital": yesterday_capital_usage["yday_min_capital"],
            "capital_record": capital_record["capital_record"],
            "capital_record_date": capital_record["capital_record_date"],
        },
        "trade_summary": trade_summary,
        "under_buffer_exit_summary": under_buffer_exit_summary,
        "under_buffer_exit_rows": compact_rows(
            sort_if_present(under_buffer_exit_rows, "timestamp_utc", ascending=False),
            [
                "timestamp_utc",
                "event_title",
                "question",
                "score",
                "elapsed",
                "entry_price",
                "exit_bid",
                "hold_pnl_usd",
                "exit_pnl_usd",
                "delta_pnl_usd",
            ],
            30,
        ),
        "capital_process_summary": capital_summary,
        "process_focus_summary": process_focus_summary,
        "pnl_attribution_summary": attribution_summary,
        "diagnostic_funnel_summary": funnel_summary,
        "diagnostic_funnel_rows": compact_rows(funnel_rows, ["stage", "count", "description"], 30),
        "open_trades": compact_rows(sort_if_present(open_trades, "entry_timestamp", ascending=False), trade_cols, 25),
        "stale_open_trades": compact_rows(sort_if_present(stale_open_trades, "entry_timestamp", ascending=False), trade_cols, 25),
        "process_focus_rows": compact_rows(
            pd.DataFrame(process_focus_rows),
            ["process_id", "status", "current_balance", "next_stake", "profit_over_start", "step_count", "open_trade_id", "last_result"],
            25,
        ),
        "capital_process_rows": compact_rows(
            pd.DataFrame(capital_rows),
            ["process_id", "status", "current_balance", "target_balance", "step_count", "wins", "losses", "open_trade_id", "last_result"],
            40,
        ),
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
        "missing_fixture_summary": missing_fixture_summary,
        "missing_fixture_rows": compact_rows(
            missing_fixture_rows,
            ["reason", "event_title", "league", "question", "rows"],
            80,
        ),
        "missing_detail_history_summary": missing_detail_history_summary,
        "missing_detail_history_rows": compact_rows(
            missing_detail_history_rows,
            ["reason", "event_title", "league", "question", "rows"],
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
        "pnl_attribution_strategy": compact_rows(attribution_strategy, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
        "pnl_attribution_subtype": compact_rows(attribution_subtype, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 30),
        "pnl_attribution_league": compact_rows(attribution_league, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
        "pnl_attribution_entry_bucket": compact_rows(attribution_entry_bucket, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
        "pnl_attribution_price_bucket": compact_rows(attribution_price_bucket, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
        "pnl_attribution_goal_buffer": compact_rows(attribution_goal_buffer, ["group", "trades", "wins", "losses", "pnl_usd", "win_rate"], 20),
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
            "voided_bad_feed": 0,
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
    open_count = int((status == "open").sum())
    resolved_count = int(resolved_mask.sum())
    graded = wins + losses
    return {
        "total_trades": open_count + resolved_count,
        "open_trades": open_count,
        "resolved_trades": resolved_count,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "stale_closed": int((status == "stale_closed").sum()),
        "voided_bad_feed": int((status == "voided_bad_feed").sum()),
        "stake_usd": round(float(stake[resolved_mask].sum()), 2),
        "pnl_usd": round(float(pnl[resolved_mask].sum()), 2),
        "win_rate": f"{round((wins / graded) * 100, 1)}%" if graded else "",
    }


def summarize_under_buffer_exit_scenario(exits: pd.DataFrame, trades: pd.DataFrame) -> tuple[dict[str, object], pd.DataFrame]:
    empty_summary = {
        "triggered": 0,
        "hold_pnl_usd": 0.0,
        "exit_rule_pnl_usd": 0.0,
        "delta_pnl_usd": 0.0,
    }
    if exits.empty:
        return empty_summary, pd.DataFrame()

    frame = exits.copy()
    if "trade_id" in frame.columns:
        frame = frame.drop_duplicates(subset=["trade_id"], keep="first")
    frame["exit_pnl_usd"] = pd.to_numeric(frame.get("exit_pnl_usd", pd.Series(dtype=float)), errors="coerce").fillna(0.0)

    if not trades.empty and "trade_id" in trades.columns and "pnl_usd" in trades.columns:
        trade_pnl = trades[["trade_id", "pnl_usd"]].copy()
        trade_pnl["hold_pnl_usd"] = pd.to_numeric(trade_pnl["pnl_usd"], errors="coerce")
        frame = frame.merge(trade_pnl[["trade_id", "hold_pnl_usd"]], on="trade_id", how="left")
    else:
        frame["hold_pnl_usd"] = pd.NA

    frame["hold_pnl_usd"] = pd.to_numeric(frame.get("hold_pnl_usd", pd.Series(dtype=float)), errors="coerce")
    frame["delta_pnl_usd"] = frame["exit_pnl_usd"] - frame["hold_pnl_usd"].fillna(0.0)
    resolved = frame[frame["hold_pnl_usd"].notna()]
    summary = {
        "triggered": int(len(frame)),
        "resolved_compared": int(len(resolved)),
        "hold_pnl_usd": round(float(resolved["hold_pnl_usd"].sum()), 4) if not resolved.empty else 0.0,
        "exit_rule_pnl_usd": round(float(resolved["exit_pnl_usd"].sum()), 4) if not resolved.empty else 0.0,
        "delta_pnl_usd": round(float(resolved["delta_pnl_usd"].sum()), 4) if not resolved.empty else 0.0,
    }
    for column in ["exit_bid", "entry_price", "elapsed", "total_goal_buffer", "hold_pnl_usd", "exit_pnl_usd", "delta_pnl_usd"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").round(4)
    return summary, frame


def summarize_process_focus(processes: pd.DataFrame, *, start_balance: float) -> tuple[dict[str, object], list[dict[str, object]]]:
    if processes.empty:
        return {
            "active_processes": 0,
            "active_above_start": 0,
            "ready_processes": 0,
            "in_trade_processes": 0,
            "balance_above_start": 0.0,
        }, []
    frame = processes.copy()
    frame["current_balance"] = pd.to_numeric(frame.get("current_balance", ""), errors="coerce").fillna(0.0)
    frame["step_count"] = pd.to_numeric(frame.get("step_count", ""), errors="coerce").fillna(0).astype(int)
    active = frame[frame.get("status", "").astype(str).isin(["ready", "in_trade"])].copy()
    active["profit_over_start"] = (active["current_balance"] - float(start_balance)).round(4)
    active["next_stake"] = active["current_balance"].round(4)
    above_start = active[active["current_balance"] > float(start_balance)].copy()
    summary = {
        "active_processes": int(len(active)),
        "active_above_start": int(len(above_start)),
        "ready_processes": int((active["status"].astype(str) == "ready").sum()) if not active.empty else 0,
        "in_trade_processes": int((active["status"].astype(str) == "in_trade").sum()) if not active.empty else 0,
        "balance_above_start": round(float(above_start["current_balance"].sum()), 4) if not above_start.empty else 0.0,
    }
    rows = sort_if_present(above_start, "current_balance", ascending=False).to_dict(orient="records") if not above_start.empty else []
    return summary, rows


def summarize_capital_usage(processes: pd.DataFrame, *, start_balance: float) -> dict[str, object]:
    if processes.empty:
        return {
            "capital_runs": 0,
            "continuations": 0,
            "max_parallel_runs": 0,
            "min_start_capital": 0.0,
        }
    frame = processes.copy()
    frame["step_count"] = pd.to_numeric(frame.get("step_count", ""), errors="coerce").fillna(0).astype(int)
    total_runs = int(frame["process_id"].astype(str).replace("", pd.NA).dropna().nunique()) if "process_id" in frame else int(len(frame))
    total_steps = int(frame["step_count"].sum())
    max_parallel = max_parallel_processes(frame)
    return {
        "capital_runs": total_runs,
        "continuations": max(total_steps - total_runs, 0),
        "max_parallel_runs": max_parallel,
        "min_start_capital": round(float(max_parallel) * float(start_balance), 2),
    }


def summarize_yesterday_capital_usage(trades: pd.DataFrame, *, start_balance: float, timezone_name: str = "Europe/Berlin") -> dict[str, object]:
    empty = {
        "yday_trades": 0,
        "yday_capital_runs": 0,
        "yday_peak_open_trades": 0,
        "yday_peak_stake_locked": 0.0,
        "yday_min_capital": 0.0,
    }
    if trades.empty or "entry_timestamp" not in trades:
        return empty
    tz = ZoneInfo(timezone_name)
    yesterday = datetime.now(tz).date() - timedelta(days=1)
    frame = trades.copy()
    frame["_entry_dt"] = pd.to_datetime(frame.get("entry_timestamp", ""), errors="coerce", utc=True).dt.tz_convert(tz)
    frame["_resolved_dt"] = pd.to_datetime(frame.get("resolved_at", ""), errors="coerce", utc=True).dt.tz_convert(tz)
    day = frame[frame["_entry_dt"].dt.date == yesterday].copy()
    if day.empty:
        return empty
    day["stake_usd_num"] = pd.to_numeric(day.get("stake_usd", ""), errors="coerce").fillna(0.0)
    peak_open, peak_stake = peak_trade_capital(day, tz)
    process_ids = day.get("process_id", pd.Series(dtype=str)).astype(str).replace("", pd.NA).dropna()
    return {
        "yday_date": yesterday.isoformat(),
        "yday_trades": int(len(day)),
        "yday_capital_runs": int(process_ids.nunique()),
        "yday_peak_open_trades": peak_open,
        "yday_peak_stake_locked": round(peak_stake, 2),
        "yday_min_capital": round(max(peak_stake, peak_open * float(start_balance)), 2),
    }


def peak_trade_capital(trades: pd.DataFrame, tz: ZoneInfo) -> tuple[int, float]:
    events: list[tuple[datetime, int, str, float]] = []
    for idx, row in trades.iterrows():
        entry = row.get("_entry_dt")
        if pd.isna(entry):
            continue
        resolved = row.get("_resolved_dt")
        if pd.isna(resolved):
            resolved = datetime.now(tz)
        stake = float(row.get("stake_usd_num") or 0.0)
        trade_id = str(row.get("trade_id") or idx)
        start_dt = entry.to_pydatetime() if hasattr(entry, "to_pydatetime") else entry
        end_dt = resolved.to_pydatetime() if hasattr(resolved, "to_pydatetime") else resolved
        events.append((start_dt, 1, trade_id, stake))
        events.append((end_dt, -1, trade_id, stake))
    active: dict[str, float] = {}
    peak_open = 0
    peak_stake = 0.0
    for _, delta, trade_id, stake in sorted(events, key=lambda item: (item[0], item[1])):
        if delta > 0:
            active[trade_id] = stake
        else:
            active.pop(trade_id, None)
        peak_open = max(peak_open, len(active))
        peak_stake = max(peak_stake, sum(active.values()))
    return peak_open, peak_stake


def update_capital_high_watermark(path: Path, yesterday_usage: dict[str, object]) -> dict[str, object]:
    current = load_capital_high_watermark(path)
    candidate = float(yesterday_usage.get("yday_min_capital") or 0.0)
    if candidate > float(current.get("capital_record", 0.0) or 0.0):
        current = {
            "capital_record": round(candidate, 2),
            "capital_record_date": str(yesterday_usage.get("yday_date") or ""),
            "capital_record_peak_open_trades": int(yesterday_usage.get("yday_peak_open_trades") or 0),
            "capital_record_peak_stake_locked": round(float(yesterday_usage.get("yday_peak_stake_locked") or 0.0), 2),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return {
        "capital_record": float(current.get("capital_record", 0.0) or 0.0),
        "capital_record_date": str(current.get("capital_record_date", "") or ""),
        "capital_record_peak_open_trades": int(current.get("capital_record_peak_open_trades", 0) or 0),
        "capital_record_peak_stake_locked": float(current.get("capital_record_peak_stake_locked", 0.0) or 0.0),
    }


def load_capital_high_watermark(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "capital_record": 0.0,
            "capital_record_date": "",
            "capital_record_peak_open_trades": 0,
            "capital_record_peak_stake_locked": 0.0,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {
            "capital_record": 0.0,
            "capital_record_date": "",
            "capital_record_peak_open_trades": 0,
            "capital_record_peak_stake_locked": 0.0,
        }
    return payload if isinstance(payload, dict) else {}


def max_parallel_processes(processes: pd.DataFrame) -> int:
    if processes.empty or "created_at" not in processes:
        return int(len(processes))
    events: list[tuple[datetime, int]] = []
    now = datetime.now(timezone.utc)
    for _, row in processes.iterrows():
        start = parse_process_time(row.get("created_at")) or parse_process_time(row.get("started_at"))
        if start is None:
            continue
        end = parse_process_time(row.get("closed_at")) or now
        events.append((start, 1))
        events.append((end, -1))
    if not events:
        return int(len(processes))
    active = 0
    peak = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        peak = max(peak, active)
    return peak


def parse_process_time(value: object) -> datetime | None:
    if value in ("", None):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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
