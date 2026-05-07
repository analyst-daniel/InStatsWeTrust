from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.config import load_settings, resolve_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2026-05-03")
    args = parser.parse_args()

    settings = load_settings()
    since = datetime.fromisoformat(f"{args.since}T00:00:00+00:00")
    cooldown_minutes = int(settings.get("parallel_research", {}).get("goal_cooldown_minutes", 5))
    trade_csv = resolve_path(settings["storage"]["trade_csv"])
    snapshot_csv = resolve_path(settings["storage"]["snapshot_csv"])
    output_csv = resolve_path(settings["storage"].get("goal_cooldown_research_csv", "data/snapshots/goal_cooldown_research.csv"))

    trades = load_under_trades(trade_csv, since)
    goal_times = infer_goal_times(snapshot_csv, {trade["event_slug"] for trade in trades})
    rows = []
    for trade in trades:
        recent_goal_at = latest_goal_before(goal_times.get(trade["event_slug"], []), trade["entry_dt"], cooldown_minutes)
        minutes_since_goal = None
        if recent_goal_at:
            minutes_since_goal = round((trade["entry_dt"] - recent_goal_at).total_seconds() / 60.0, 2)
        rows.append(
            {
                "trade_id": trade["trade_id"],
                "entry_timestamp": trade["entry_timestamp"],
                "event_title": trade["event_title"],
                "event_slug": trade["event_slug"],
                "market_id": trade["market_id"],
                "question": trade["question"],
                "side": trade["side"],
                "entry_price": trade["entry_price"],
                "score": trade["score"],
                "elapsed": trade["elapsed"],
                "pnl_usd": trade["pnl_usd"],
                "blocked_by_goal_cooldown": bool(recent_goal_at),
                "recent_goal_at": recent_goal_at.isoformat() if recent_goal_at else "",
                "minutes_since_goal": minutes_since_goal if minutes_since_goal is not None else "",
            }
        )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "trade_id",
        "entry_timestamp",
        "event_title",
        "event_slug",
        "market_id",
        "question",
        "side",
        "entry_price",
        "score",
        "elapsed",
        "pnl_usd",
        "blocked_by_goal_cooldown",
        "recent_goal_at",
        "minutes_since_goal",
    ]
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    blocked = [row for row in rows if row["blocked_by_goal_cooldown"]]
    blocked_pnl = round(sum(float(row["pnl_usd"] or 0.0) for row in blocked), 4)
    total_pnl = round(sum(float(row["pnl_usd"] or 0.0) for row in rows), 4)
    print(f"written={len(rows)} blocked={len(blocked)} blocked_pnl={blocked_pnl} pnl_without_blocked={round(total_pnl - blocked_pnl, 4)} file={output_csv}")


def load_under_trades(path: Path, since: datetime) -> list[dict[str, object]]:
    trades = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            entry_dt = parse_dt(row.get("entry_timestamp", ""))
            if not entry_dt or entry_dt < since:
                continue
            if row.get("status") != "resolved" or row.get("side", "").lower() != "under":
                continue
            pnl = to_float(row.get("pnl_usd"))
            if pnl is None:
                continue
            row["entry_dt"] = entry_dt
            row["pnl_usd"] = pnl
            trades.append(row)
    return trades


def infer_goal_times(snapshot_csv: Path, event_slugs: set[str]) -> dict[str, list[datetime]]:
    last_goals_by_event: dict[str, int] = {}
    goal_times: dict[str, list[datetime]] = {event_slug: [] for event_slug in event_slugs}
    with snapshot_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            event_slug = row.get("event_slug", "")
            if event_slug not in event_slugs:
                continue
            goals = total_goals(row.get("score", ""))
            timestamp = parse_dt(row.get("timestamp_utc", ""))
            if goals is None or timestamp is None:
                continue
            previous = last_goals_by_event.get(event_slug)
            if previous is not None and goals > previous:
                goal_times[event_slug].append(timestamp)
            last_goals_by_event[event_slug] = goals
    return goal_times


def latest_goal_before(goal_times: list[datetime], entry_dt: datetime, cooldown_minutes: int) -> datetime | None:
    cutoff = entry_dt - timedelta(minutes=cooldown_minutes)
    candidates = [goal_at for goal_at in goal_times if cutoff <= goal_at <= entry_dt]
    return max(candidates) if candidates else None


def total_goals(score: str) -> int | None:
    match = re.match(r"\s*(\d+)\s*-\s*(\d+)\s*$", str(score or ""))
    if not match:
        return None
    return int(match.group(1)) + int(match.group(2))


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
