from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.discovery.gamma_client import GammaClient
from app.paper_trader.settlement import resolved_outcome_from_market
from app.paper_trader.trader import PaperTrader
from app.reporting import write_daily_report
from app.risk.limits import RiskManager
from app.storage.store import Store
from app.storage.trades import load_trades
from app.utils.config import load_settings, resolve_path
from app.utils.logging import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = load_settings()
    logger = setup_logging(resolve_path(settings["storage"]["log_dir"]), name="settlement")
    store = Store(
        resolve_path(settings["storage"]["sqlite_path"]),
        resolve_path(settings["storage"]["snapshot_csv"]),
        resolve_path(settings["storage"]["trade_csv"]),
    )
    client = GammaClient(settings, resolve_path(settings["storage"]["raw_dir"]))
    trader = PaperTrader(settings, RiskManager(settings))
    interval = int(settings.get("settlement", {}).get("interval_seconds", 60))
    print(f"Settlement checker running every {interval}s...", flush=True)

    while True:
        try:
            trades = load_trades(resolve_path(settings["storage"]["trade_csv"]))
            open_trades = [trade for trade in trades if trade.status == "open"]
            resolved: dict[str, str] = {}
            for trade in open_trades:
                try:
                    market = client.fetch_market(trade.market_id)
                    outcome = resolved_outcome_from_market(market)
                    if outcome:
                        resolved[trade.market_id] = outcome
                except Exception:
                    logger.exception("failed to settle market_id=%s", trade.market_id)
            updates = trader.update_open_trades(trades, latest_by_token={}, resolved_markets=resolved)
            store.upsert_trades(updates)
            all_after = load_trades(resolve_path(settings["storage"]["trade_csv"]))
            csv_path, md_path = write_daily_report(all_after, resolve_path(settings["storage"]["daily_dir"]))
            logger.info("settlement open=%s resolved_now=%s report=%s summary=%s", len(open_trades), len(updates), csv_path, md_path)
            print(f"settlement open={len(open_trades)} resolved_now={len(updates)} daily_report={csv_path.name}", flush=True)
        except Exception:
            logger.exception("settlement cycle failed")
        if args.once:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
