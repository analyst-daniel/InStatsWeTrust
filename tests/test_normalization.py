from __future__ import annotations

from datetime import datetime, timezone

from app.normalize.normalizer import normalize_market


def test_second_outcome_ask_uses_one_minus_best_bid() -> None:
    event = {"id": "1", "slug": "team-a-team-b", "title": "Team A FC vs. Team B FC", "active": True}
    market = {
        "id": "m1",
        "slug": "m1",
        "question": "Will Team A FC win?",
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": '["yes-token", "no-token"]',
        "bestBid": "0.03",
        "bestAsk": "0.04",
        "active": True,
        "closed": False,
    }
    row = normalize_market(event, market, sport="soccer", timestamp=datetime.now(timezone.utc))
    assert row is not None
    assert row.best_ask_yes == 0.04
    assert row.best_bid_no == 0.96
    assert row.best_ask_no == 0.97
