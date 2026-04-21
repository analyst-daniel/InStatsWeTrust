from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.live_state.cache import LiveStateCache
from app.live_state.matcher import LiveStateMatcher
from app.normalize.models import LiveState, NormalizedMarket


def market() -> NormalizedMarket:
    return NormalizedMarket(
        event_id="e1",
        event_slug="arsenal-fc-vs-sporting-cp",
        event_title="Arsenal FC vs. Sporting CP",
        market_id="m1",
        question="Will Arsenal win?",
        sport="soccer",
        token_ids=["a", "b"],
        yes_token_id="a",
        no_token_id="b",
        outcomes=["Yes", "No"],
        timestamp_utc=datetime.now(timezone.utc),
    )


def test_matcher_rejects_stale_live_state(tmp_path: Path) -> None:
    cache = LiveStateCache(tmp_path / "live.json")
    cache._states["arsenal-fc-vs-sporting-cp"] = LiveState(
        slug="arsenal-fc-vs-sporting-cp",
        sport="soccer",
        live=True,
        elapsed=80,
        last_update=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    assert LiveStateMatcher(cache, max_age_seconds=300).match(market()) is None
