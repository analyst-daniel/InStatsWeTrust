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
    max_age = int(settings.get("dashboard", {}).get("live_state_max_age_seconds", 180))
    cache = LiveStateCache(resolve_path(settings["storage"]["live_state_json"]))
    states = cache.all()
    soccer = [state for state in states if state.sport.lower() == "soccer" or state.period.upper() in {"1H", "2H", "HT"}]
    with_elapsed = [state for state in soccer if state.elapsed is not None]
    now = datetime.now(timezone.utc)
    fresh = [state for state in soccer if (now - state.last_update).total_seconds() <= max_age]
    fresh_with_elapsed = [state for state in fresh if state.elapsed is not None]
    stale = len(soccer) - len(fresh)
    print(
        f"all_live_states={len(states)} soccer_like={len(soccer)} soccer_with_elapsed={len(with_elapsed)} "
        f"fresh_soccer={len(fresh)} fresh_with_elapsed={len(fresh_with_elapsed)} stale_soccer={stale} "
        f"max_age_seconds={max_age}"
    )
    for state in fresh[:30]:
        age = int((now - state.last_update).total_seconds())
        print(
            f"slug={state.slug} sport={state.sport} live={state.live} ended={state.ended} "
            f"period={state.period} elapsed={state.elapsed} score={state.score} "
            f"age_sec={age} last_update={state.last_update}"
        )
    if not fresh:
        print("No fresh soccer live states. Start/restart Football API Fallback and Live State windows.")


if __name__ == "__main__":
    main()
