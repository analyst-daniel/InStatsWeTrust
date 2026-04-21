from __future__ import annotations

from app.paper_trader.settlement import resolved_outcome_from_market


def test_resolved_outcome_from_closed_market_prices() -> None:
    market = {
        "closed": True,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0", "1"]',
    }
    assert resolved_outcome_from_market(market) == "No"


def test_open_market_has_no_result() -> None:
    market = {
        "closed": False,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0", "1"]',
    }
    assert resolved_outcome_from_market(market) is None
