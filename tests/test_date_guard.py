from __future__ import annotations

from datetime import datetime, timezone

from app.normalize.models import NormalizedMarket
from app.strategy.date_guard import market_date_is_current_or_unknown


def market(question: str, event_slug: str = "soccer-2026-04-15") -> NormalizedMarket:
    return NormalizedMarket(
        event_id="e1",
        event_slug=event_slug,
        event_title="Team A FC vs. Team B FC",
        market_id="m1",
        question=question,
        sport="soccer",
        token_ids=["a", "b"],
        yes_token_id="a",
        no_token_id="b",
        outcomes=["Yes", "No"],
        timestamp_utc=datetime.now(timezone.utc),
    )


def test_rejects_old_market_date() -> None:
    assert not market_date_is_current_or_unknown(market("Will Team A win on 2026-04-10?", "soccer-2026-04-10"), today="2026-04-15")


def test_allows_today_or_unknown_date() -> None:
    assert market_date_is_current_or_unknown(market("Will Team A win on 2026-04-15?"), today="2026-04-15")
    assert market_date_is_current_or_unknown(market("Spread: Team A (-1.5)"), today="2026-04-15")
