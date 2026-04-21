from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.live_state.ws_client import run_sports_ws
from app.utils.config import load_settings, resolve_path
from app.utils.logging import setup_logging


def main() -> None:
    settings = load_settings()
    setup_logging(resolve_path(settings["storage"]["log_dir"]), name="live_state")
    print("Live State WS connecting to Polymarket sports websocket...", flush=True)
    asyncio.run(run_sports_ws(settings, resolve_path(settings["storage"]["live_state_json"])))


if __name__ == "__main__":
    main()
