from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.normalize.models import PaperTrade
from app.storage.store import model_row


def write_daily_report(trades: list[PaperTrade], daily_dir: Path, day: str | None = None) -> tuple[Path, Path]:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_dir.mkdir(parents=True, exist_ok=True)
    day_trades = [trade for trade in trades if trade.entry_timestamp.strftime("%Y-%m-%d") == day]
    csv_path = daily_dir / f"trade_report_{day}.csv"
    md_path = daily_dir / f"summary_{day}.md"
    write_trade_csv(csv_path, day_trades)
    write_summary(md_path, day, day_trades)
    return csv_path, md_path


def write_trade_csv(path: Path, trades: list[PaperTrade]) -> None:
    rows = [model_row(trade) for trade in trades]
    if not rows:
        path.write_text("no rows\n", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, day: str, trades: list[PaperTrade]) -> None:
    statuses = Counter(trade.status for trade in trades)
    resolved = [trade for trade in trades if trade.pnl_usd is not None]
    pnl = round(sum(float(trade.pnl_usd or 0) for trade in resolved), 4)
    hit_99 = sum(1 for trade in trades if trade.first_hit_99_at)
    hit_999 = sum(1 for trade in trades if trade.first_hit_999_at)
    lines = [
        f"# Daily Summary {day}",
        "",
        f"- trades: {len(trades)}",
        f"- open: {statuses.get('open', 0)}",
        f"- resolved: {statuses.get('resolved', 0)}",
        f"- hit_99: {hit_99}",
        f"- hit_999: {hit_999}",
        f"- realized_pnl_usd: {pnl}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
