from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.normalize.models import PaperTrade
from app.storage.store import Store
from app.storage.trades import load_trades
from app.utils.config import load_settings, resolve_path


def main() -> None:
    settings = load_settings()
    trade_path = resolve_path(settings["storage"]["trade_csv"])
    trades = load_trades(trade_path)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    changed: list[PaperTrade] = []
    for trade in trades:
        if trade.status == "open" and trade.entry_timestamp.strftime("%Y-%m-%d") < today:
            trade.status = "stale_closed"
            trade.resolved_at = datetime.now(timezone.utc)
            trade.result = "stale_open_from_previous_day"
            trade.pnl_usd = None
            changed.append(trade)
    store = Store(
        resolve_path(settings["storage"]["sqlite_path"]),
        resolve_path(settings["storage"]["snapshot_csv"]),
        trade_path,
    )
    store.upsert_trades(changed)
    print(f"stale open trades closed={len(changed)}")


if __name__ == "__main__":
    main()
