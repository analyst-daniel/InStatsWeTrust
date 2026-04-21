from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


LEAGUE_BY_SLUG_PREFIX = {
    "ucl": "UEFA Champions League",
    "uel": "UEFA Europa League",
    "col": "UEFA Conference League",
    "epl": "English Premier League",
    "elc": "English Championship",
    "el1": "English League One",
    "el2": "English League Two",
    "lal": "La Liga",
    "sea": "Serie A",
    "bun": "Bundesliga",
    "lig1": "Ligue 1",
    "por": "Portugal",
    "spl": "Saudi Pro League",
    "sud": "Copa Sudamericana",
    "bra": "Brazil",
    "j1100": "J1 League",
    "j2": "J2 League",
}


@dataclass(frozen=True)
class CalibrationArtifacts:
    summary: dict[str, object]
    by_league: pd.DataFrame
    by_entry_bucket: pd.DataFrame
    by_market_type: pd.DataFrame
    by_reason: pd.DataFrame


def load_trades_dataframe(sqlite_path: Path) -> pd.DataFrame:
    if not sqlite_path.exists():
        return pd.DataFrame()
    import sqlite3

    with sqlite3.connect(sqlite_path) as conn:
        try:
            return pd.read_sql_query("SELECT * FROM trades", conn)
        except Exception:
            return pd.DataFrame()


def infer_market_type(question: str) -> str:
    text = str(question or "").lower()
    if "exact score" in text:
        return "exact"
    if "btts" in text or "both teams to score" in text:
        return "btts"
    if "spread:" in text or "handicap" in text:
        return "spread"
    if "o/u" in text or "over" in text or "under" in text:
        return "total"
    if "will " in text and " win" in text:
        return "match"
    return "other"


def infer_league(event_slug: str) -> str:
    slug = str(event_slug or "")
    prefix = slug.split("-", 1)[0].lower()
    return LEAGUE_BY_SLUG_PREFIX.get(prefix, prefix or "unknown")


def entry_bucket(value: object) -> str:
    try:
        minute = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if minute < 75:
        return "<75"
    if minute < 80:
        return "75-79"
    if minute < 85:
        return "80-84"
    if minute < 89:
        return "85-88"
    return "89+"


def summarize_proof_of_winning_trades(trades: pd.DataFrame) -> CalibrationArtifacts:
    if trades.empty or "entry_reason" not in trades.columns:
        empty = pd.DataFrame()
        return CalibrationArtifacts(
            summary={
                "total": 0,
                "resolved": 0,
                "wins": 0,
                "losses": 0,
                "pnl_usd": 0.0,
                "win_rate": "",
            },
            by_league=empty,
            by_entry_bucket=empty,
            by_market_type=empty,
            by_reason=empty,
        )

    proof = trades[trades["entry_reason"].astype(str).str.startswith("proof_of_winning", na=False)].copy()
    if proof.empty:
        empty = pd.DataFrame()
        return CalibrationArtifacts(
            summary={
                "total": 0,
                "resolved": 0,
                "wins": 0,
                "losses": 0,
                "pnl_usd": 0.0,
                "win_rate": "",
            },
            by_league=empty,
            by_entry_bucket=empty,
            by_market_type=empty,
            by_reason=empty,
        )

    proof["pnl_usd_num"] = pd.to_numeric(proof.get("pnl_usd", ""), errors="coerce")
    proof["resolved_flag"] = proof.get("status", "").astype(str).eq("resolved")
    proof["win_flag"] = proof["resolved_flag"] & proof["pnl_usd_num"].gt(0)
    proof["loss_flag"] = proof["resolved_flag"] & proof["pnl_usd_num"].lt(0)
    proof["league"] = proof.get("event_slug", "").astype(str).map(infer_league)
    proof["market_type"] = proof.get("question", "").astype(str).map(infer_market_type)
    proof["entry_bucket"] = proof.get("elapsed", "").map(entry_bucket)

    resolved = proof[proof["resolved_flag"]].copy()
    wins = int(resolved["win_flag"].sum())
    losses = int(resolved["loss_flag"].sum())
    graded = wins + losses
    summary = {
        "total": int(len(proof)),
        "resolved": int(len(resolved)),
        "wins": wins,
        "losses": losses,
        "pnl_usd": round(float(resolved["pnl_usd_num"].fillna(0.0).sum()), 4),
        "win_rate": f"{round((wins / graded) * 100, 1)}%" if graded else "",
    }

    by_league = summarize_group(resolved, "league")
    by_entry_bucket = summarize_group(resolved, "entry_bucket")
    by_market_type = summarize_group(resolved, "market_type")
    by_reason = summarize_group(proof, "entry_reason", resolved_only=False)

    return CalibrationArtifacts(
        summary=summary,
        by_league=by_league,
        by_entry_bucket=by_entry_bucket,
        by_market_type=by_market_type,
        by_reason=by_reason,
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
        graded = grouped["wins"] + grouped["losses"]
        grouped["win_rate"] = graded.where(graded > 0, 0)
        grouped["win_rate"] = grouped.apply(
            lambda row: f"{round((row['wins'] / (row['wins'] + row['losses'])) * 100, 1)}%"
            if (row["wins"] + row["losses"]) > 0
            else "",
            axis=1,
        )
    grouped["pnl_usd"] = grouped["pnl_usd"].fillna(0.0).round(4)
    return grouped.sort_values(["trades", "pnl_usd"], ascending=[False, False]).reset_index(drop=True)

