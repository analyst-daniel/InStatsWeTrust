from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.live_state.cache import LiveStateCache
from app.live_state.matcher import LiveStateMatcher
from app.normalize.models import LiveState, NormalizedMarket


def test_more_markets_slug_matches_base_slug(tmp_path: Path) -> None:
    cache = LiveStateCache(tmp_path / "live.json")
    cache._states["team-a-team-b"] = LiveState(slug="team-a-team-b", live=True, elapsed=76, last_update=datetime.now(timezone.utc))
    matcher = LiveStateMatcher(cache)
    market = NormalizedMarket(
        event_id="e1",
        event_slug="team-a-team-b-more-markets",
        event_title="Team A FC vs. Team B FC - More Markets",
        market_id="m1",
        question="Spread: Team A FC (-1.5)",
        sport="soccer",
        token_ids=["a", "b"],
        yes_token_id="a",
        no_token_id="b",
        outcomes=["Team A FC", "Team B FC"],
        timestamp_utc=datetime.now(timezone.utc),
    )
    assert matcher.match(market) is not None
