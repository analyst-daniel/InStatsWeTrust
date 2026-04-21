from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.live_state.cache import LiveStateCache
from app.normalize.normalizer import normalize_events
from app.utils.config import load_settings, resolve_path


def main() -> None:
    settings = load_settings()
    cache = LiveStateCache(resolve_path(settings["storage"]["live_state_json"]))
    cache_events = []
    discovery_path = resolve_path(settings["storage"]["discovery_cache_json"])
    if discovery_path.exists():
        cache_events = json.loads(discovery_path.read_text(encoding="utf-8") or "{}").get("events", [])
    markets = normalize_events(cache_events)
    print("Live Soccer Matches")
    for state in cache.all():
        if state.sport.lower() != "soccer" or not state.live or state.ended:
            continue
        age_seconds = (pd_now() - state.last_update).total_seconds()
        if age_seconds > int(settings.get("dashboard", {}).get("live_state_max_age_seconds", 300)):
            continue
        market_count = sum(1 for market in markets if state.slug in {market.event_slug, market.market_slug} or state.slug in market.event_slug)
        print(
            f"{state.slug} period={state.period} minute={state.elapsed} score={state.score} "
            f"matched_market_rows={market_count} last_update={state.last_update}"
        )


def pd_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


if __name__ == "__main__":
    main()
