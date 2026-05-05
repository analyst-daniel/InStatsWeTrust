from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.config import load_settings, resolve_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2026-05-03")
    args = parser.parse_args()

    settings = load_settings()
    cfg = settings.get("under_buffer_exit", {})
    since = datetime.fromisoformat(f"{args.since}T00:00:00+00:00")
    rows = compare_hold_vs_exit(
        resolve_path(settings["storage"]["trade_csv"]),
        resolve_path(settings["storage"]["snapshot_csv"]),
        since=since,
        max_goal_buffer=float(cfg.get("max_goal_buffer", 0.5)),
        max_elapsed=float(cfg.get("max_elapsed", 85.0)),
        min_bid_to_entry_ratio=float(cfg.get("min_bid_to_entry_ratio", 0.95)),
    )
    final_total = round(sum(row["final_pnl"] for row in rows), 4)
    exit_total = round(sum(row["exit_pnl"] for row in rows), 4)
    print(f"triggered={len(rows)} hold_pnl={final_total} exit_rule_pnl={exit_total} delta={round(exit_total - final_total, 4)}")
    for row in rows:
        print(
            "|".join(
                [
                    str(row["market_id"]),
                    f"min={row['elapsed']}",
                    f"score={row['score']}",
                    f"entry={row['entry_price']}",
                    f"bid={row['bid']}",
                    f"hold={round(row['final_pnl'], 4)}",
                    f"exit={round(row['exit_pnl'], 4)}",
                    str(row["question"]),
                ]
            )
        )


def compare_hold_vs_exit(
    trade_csv: Path,
    snapshot_csv: Path,
    *,
    since: datetime,
    max_goal_buffer: float,
    max_elapsed: float,
    min_bid_to_entry_ratio: float,
) -> list[dict[str, object]]:
    trades: dict[str, dict[str, object]] = {}
    with trade_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            entry = parse_dt(row.get("entry_timestamp", ""))
            pnl = to_float(row.get("pnl_usd"))
            if not entry or entry < since or row.get("status") != "resolved" or pnl is None:
                continue
            if row.get("side", "").lower() != "under":
                continue
            entry_price = to_float(row.get("entry_price"))
            stake = to_float(row.get("stake_usd"))
            resolved = parse_dt(row.get("resolved_at", ""))
            if not entry_price or not stake or not resolved:
                continue
            row["_entry_dt"] = entry
            row["_resolved_dt"] = resolved
            row["_entry_price"] = entry_price
            row["_stake"] = stake
            row["_pnl"] = pnl
            trades[str(row["market_id"])] = row

    triggered: dict[str, dict[str, object]] = {}
    with snapshot_csv.open(newline="", encoding="utf-8") as handle:
        for snapshot in csv.DictReader(handle):
            market_id = str(snapshot.get("market_id", ""))
            trade = trades.get(market_id)
            if trade is None or market_id in triggered or snapshot.get("side", "").lower() != "under":
                continue
            timestamp = parse_dt(snapshot.get("timestamp_utc", ""))
            if not timestamp or not (trade["_entry_dt"] <= timestamp <= trade["_resolved_dt"]):
                continue
            buffer = to_float(snapshot.get("total_goal_buffer"))
            elapsed = to_float(snapshot.get("elapsed"))
            bid = to_float(snapshot.get("bid"))
            if buffer is None or elapsed is None or bid is None:
                continue
            entry_price = float(trade["_entry_price"])
            if buffer > max_goal_buffer or elapsed > max_elapsed or bid < entry_price * min_bid_to_entry_ratio:
                continue
            stake = float(trade["_stake"])
            shares = stake / entry_price
            exit_pnl = round((bid - entry_price) * shares, 4)
            triggered[market_id] = {
                "market_id": market_id,
                "question": trade.get("question", ""),
                "entry_price": entry_price,
                "stake": stake,
                "final_pnl": float(trade["_pnl"]),
                "exit_pnl": exit_pnl,
                "timestamp": snapshot.get("timestamp_utc", ""),
                "elapsed": elapsed,
                "score": snapshot.get("score", ""),
                "bid": bid,
            }
    return list(triggered.values())


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def to_float(value: object) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
