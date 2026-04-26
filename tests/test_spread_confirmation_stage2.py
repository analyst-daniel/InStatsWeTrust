from datetime import datetime, timezone

from app.normalize.models import LiveState, NormalizedMarket
from app.strategy.engine import StrategyEngine


def test_strategy_engine_populates_spread_snapshot_metadata() -> None:
    engine = StrategyEngine(
        {
            "strategy": {
                "sport": "soccer",
                "min_elapsed": 70,
                "max_elapsed": 89,
                "min_price": 0.95,
                "max_price": 0.99,
                "require_live_state": True,
                "min_liquidity_usd": 0,
                "max_spread": 1.0,
            }
        }
    )
    market = NormalizedMarket(
        event_id="1",
        event_slug="j2-iwa-nag-2026-04-19-more-markets",
        event_title="Iwaki FC vs. AC Nagano Parceiro - More Markets",
        market_id="m1",
        market_slug="j2-iwa-nag-2026-04-19-spread-home-2pt5",
        question="Spread: Iwaki FC (-2.5)",
        sport="soccer",
        teams=["Iwaki FC", "AC Nagano Parceiro"],
        active=True,
        closed=False,
        yes_token_id="yes-token",
        no_token_id="no-token",
        outcomes=["Iwaki FC", "AC Nagano Parceiro"],
        best_bid_yes=0.95,
        best_ask_yes=0.96,
        best_bid_no=0.02,
        best_ask_no=0.98,
        timestamp_utc=datetime.now(timezone.utc),
    )
    live_state = LiveState(
        slug="j2-iwa-nag-2026-04-19-more-markets",
        sport="soccer",
        live=True,
        ended=False,
        score="1-0",
        period="2H",
        elapsed=81.0,
        last_update=datetime.now(timezone.utc),
        raw={},
    )
    rows = engine.evaluate_market(market, live_state)
    assert len(rows) == 2
    listed = rows[0].observation
    opposite = rows[1].observation

    assert listed.market_type == "spread"
    assert listed.spread_listed_team == "Iwaki FC"
    assert listed.spread_listed_line == -2.5
    assert listed.spread_listed_side_type == "minus"
    assert listed.spread_selected_team == "Iwaki FC"
    assert listed.spread_selected_line == -2.5
    assert listed.spread_selected_side_type == "minus"

    assert opposite.market_type == "spread"
    assert opposite.spread_listed_team == "Iwaki FC"
    assert opposite.spread_selected_team == "AC Nagano Parceiro"
    assert opposite.spread_selected_line == 2.5
    assert opposite.spread_selected_side_type == "plus"
