from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.strategy.proof_of_winning_calibration import entry_bucket, infer_league
from app.strategy.spread_confirmation import parse_spread_market


@dataclass(frozen=True)
class SpreadCalibrationArtifacts:
    summary: dict[str, object]
    by_league: pd.DataFrame
    by_entry_bucket: pd.DataFrame
    by_line: pd.DataFrame
    by_side_type: pd.DataFrame
    by_reason: pd.DataFrame


def spread_line_bucket(question: str, side: str) -> str:
    parsed = parse_spread_market(str(question or ""), str(side or ""))
    if not parsed.valid or parsed.selected_line is None:
        return "unknown"
    return f"{parsed.selected_line:+g}"


def spread_side_type_bucket(question: str, side: str) -> str:
    parsed = parse_spread_market(str(question or ""), str(side or ""))
    if not parsed.valid:
        return "unknown"
    return parsed.selected_side_type.value


def summarize_spread_confirmation_trades(trades: pd.DataFrame) -> SpreadCalibrationArtifacts:
    if trades.empty or "entry_reason" not in trades.columns:
        empty = pd.DataFrame()
        return SpreadCalibrationArtifacts(
            summary={"total": 0, "resolved": 0, "wins": 0, "losses": 0, "pnl_usd": 0.0, "win_rate": ""},
            by_league=empty,
            by_entry_bucket=empty,
            by_line=empty,
            by_side_type=empty,
            by_reason=empty,
        )

    spread = trades[trades["entry_reason"].astype(str).str.startswith("spread_", na=False)].copy()
    if spread.empty:
        empty = pd.DataFrame()
        return SpreadCalibrationArtifacts(
            summary={"total": 0, "resolved": 0, "wins": 0, "losses": 0, "pnl_usd": 0.0, "win_rate": ""},
            by_league=empty,
            by_entry_bucket=empty,
            by_line=empty,
            by_side_type=empty,
            by_reason=empty,
        )

    spread["pnl_usd_num"] = pd.to_numeric(spread.get("pnl_usd", ""), errors="coerce")
    spread["resolved_flag"] = spread.get("status", "").astype(str).eq("resolved")
    spread["win_flag"] = spread["resolved_flag"] & spread["pnl_usd_num"].gt(0)
    spread["loss_flag"] = spread["resolved_flag"] & spread["pnl_usd_num"].lt(0)
    spread["league"] = spread.get("event_slug", "").astype(str).map(infer_league)
    spread["entry_bucket"] = spread.get("elapsed", "").map(entry_bucket)
    spread["spread_line"] = spread.apply(lambda row: spread_line_bucket(row.get("question", ""), row.get("side", "")), axis=1)
    spread["spread_side_type"] = spread.apply(lambda row: spread_side_type_bucket(row.get("question", ""), row.get("side", "")), axis=1)

    resolved = spread[spread["resolved_flag"]].copy()
    wins = int(resolved["win_flag"].sum())
    losses = int(resolved["loss_flag"].sum())
    graded = wins + losses
    summary = {
        "total": int(len(spread)),
        "resolved": int(len(resolved)),
        "wins": wins,
        "losses": losses,
        "pnl_usd": round(float(resolved["pnl_usd_num"].fillna(0.0).sum()), 4),
        "win_rate": f"{round((wins / graded) * 100, 1)}%" if graded else "",
    }

    return SpreadCalibrationArtifacts(
        summary=summary,
        by_league=summarize_group(resolved, "league"),
        by_entry_bucket=summarize_group(resolved, "entry_bucket"),
        by_line=summarize_group(resolved, "spread_line"),
        by_side_type=summarize_group(resolved, "spread_side_type"),
        by_reason=summarize_group(spread, "entry_reason", resolved_only=False),
    )


def summarize_group(df: pd.DataFrame, group_col: str, *, resolved_only: bool = True) -> pd.DataFrame:
    if df.empty or group_col not in df.columns:
        return pd.DataFrame()
    grouped = (
        df.groupby(group_col, dropna=False)
        .agg(
            trades=("trade_id", "count"),
            wins=("win_flag", "sum") if "win_flag" in df.columns else ("trade_id", "count"),
            losses=("loss_flag", "sum") if "loss_flag" in df.columns else ("trade_id", "count"),
            pnl_usd=("pnl_usd_num", "sum") if "pnl_usd_num" in df.columns else ("trade_id", "count"),
        )
        .reset_index()
        .rename(columns={group_col: "group"})
    )
    if resolved_only and "wins" in grouped.columns and "losses" in grouped.columns:
        grouped["win_rate"] = grouped.apply(
            lambda row: f"{round((row['wins'] / (row['wins'] + row['losses'])) * 100, 1)}%"
            if (row["wins"] + row["losses"]) > 0
            else "",
            axis=1,
        )
    grouped["pnl_usd"] = grouped["pnl_usd"].fillna(0.0).round(4)
    return grouped.sort_values(["trades", "pnl_usd"], ascending=[False, False]).reset_index(drop=True)
