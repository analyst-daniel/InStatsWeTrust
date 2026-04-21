from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.live_state.cache import LiveStateCache
from app.live_state.football_api_client import FootballApiClient
from app.live_state.football_fallback import update_live_state_from_football_api
from app.utils.config import load_settings, resolve_path
from app.utils.logging import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = load_settings()
    logger = setup_logging(resolve_path(settings["storage"]["log_dir"]), name="football_fallback")
    cache = LiveStateCache(resolve_path(settings["storage"]["live_state_json"]))
    budget_path = resolve_path("data/snapshots/football_api_budget.json")
    interval = int(settings.get("football_api", {}).get("poll_interval_seconds", 60))
    client = FootballApiClient(settings, budget_path)
    print(f"Football fallback running every {interval}s. budget_used_today={client.budget.used_today()}", flush=True)
    while True:
        try:
            updated, with_elapsed, captured = update_live_state_from_football_api(settings, cache, budget_path)
            used = FootballApiClient(settings, budget_path).budget.used_today()
            logger.info("football fallback updated=%s with_elapsed=%s captured=%s budget_used=%s", updated, with_elapsed, captured, used)
            print(f"football_api updated={updated} with_elapsed={with_elapsed} captured={captured} budget_used_today={used}", flush=True)
        except Exception as exc:
            logger.exception("football fallback failed")
            print(f"football_api error={exc}", flush=True)
        if args.once:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
