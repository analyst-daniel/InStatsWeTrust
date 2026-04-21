from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.reporting import write_daily_report
from app.storage.trades import load_trades
from app.utils.config import load_settings, resolve_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", default=None, help="UTC day, e.g. 2026-04-15")
    args = parser.parse_args()
    settings = load_settings()
    trades = load_trades(resolve_path(settings["storage"]["trade_csv"]))
    csv_path, md_path = write_daily_report(trades, resolve_path(settings["storage"]["daily_dir"]), day=args.day)
    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
