from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.live_state.cache import LiveStateCache
from app.utils.config import load_settings, resolve_path


def main() -> None:
    settings = load_settings()
    max_age = int(settings.get("dashboard", {}).get("live_state_max_age_seconds", 300))
    cache = LiveStateCache(resolve_path(settings["storage"]["live_state_json"]))
    now = datetime.now(timezone.utc)
    before = len(cache._states)
    cache._states = {
        slug: state
        for slug, state in cache._states.items()
        if (now - state.last_update).total_seconds() <= max_age
    }
    cache.save()
    print(f"pruned live_state_cache before={before} after={len(cache._states)} max_age_seconds={max_age}")


if __name__ == "__main__":
    main()
