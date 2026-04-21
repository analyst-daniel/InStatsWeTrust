from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from app.normalize.models import PaperTrade


def load_trades(path: Path) -> list[PaperTrade]:
    if not path.exists():
        return []
    rows: list[PaperTrade] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(PaperTrade.model_validate(coerce_trade_row(row)))
    return rows


def coerce_trade_row(row: dict[str, str]) -> dict[str, object]:
    out: dict[str, object] = dict(row)
    for key in ["entry_price", "stake_usd", "shares", "elapsed", "max_favorable_price", "pnl_usd"]:
        out[key] = float(row[key]) if row.get(key) not in ("", None) else None
    if out["max_favorable_price"] is None:
        out["max_favorable_price"] = 0.0
    for key in ["entry_timestamp", "first_hit_99_at", "first_hit_999_at", "resolved_at"]:
        out[key] = datetime.fromisoformat(row[key].replace("Z", "+00:00")) if row.get(key) else None
    out["entry_reason"] = row.get("entry_reason", "") or ""
    return out
