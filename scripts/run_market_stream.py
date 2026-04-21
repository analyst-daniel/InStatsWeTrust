from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.market_data.market_ws import run_market_ws
from app.utils.config import load_settings, resolve_path
from app.utils.logging import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", action="append", default=[])
    args = parser.parse_args()
    settings = load_settings()
    setup_logging(resolve_path(settings["storage"]["log_dir"]), name="market_ws")
    output = resolve_path("data/logs/clob_market_ws.ndjson")
    asyncio.run(run_market_ws(settings, args.token, output))


if __name__ == "__main__":
    main()
