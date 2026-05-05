from __future__ import annotations

from datetime import datetime, timezone

from app.normalize.models import MarketObservation, PaperTrade
from app.paper_trader.exit_rules import under_buffer_exit_candidates


def settings() -> dict:
    return {
        "under_buffer_exit": {
            "enabled": True,
            "max_goal_buffer": 0.5,
            "max_elapsed": 85,
            "min_bid_to_entry_ratio": 0.95,
        }
    }


def trade() -> PaperTrade:
    return PaperTrade(
        trade_id="t1",
        entry_timestamp=datetime(2026, 5, 5, tzinfo=timezone.utc),
        event_slug="match",
        event_title="Match",
        market_id="m1",
        market_slug="m1",
        question="Match: O/U 3.5",
        token_id="tok-under",
        side="Under",
        entry_price=0.80,
        stake_usd=10.0,
        shares=12.5,
        elapsed=78.0,
        score="2-0",
        period="2H",
    )


def observation(*, bid: float, elapsed: float = 83.0, buffer: float = 0.5) -> MarketObservation:
    return MarketObservation(
        timestamp_utc=datetime(2026, 5, 5, 1, tzinfo=timezone.utc),
        event_id="e1",
        event_slug="match",
        event_title="Match",
        market_id="m1",
        market_slug="m1",
        question="Match: O/U 3.5",
        token_id="tok-under",
        side="Under",
        price=0.78,
        bid=bid,
        ask=0.78,
        spread=0.02,
        liquidity=100.0,
        last_trade_price=0.78,
        sport="soccer",
        live=True,
        ended=False,
        score="2-1",
        period="2H",
        elapsed=elapsed,
        market_type="total",
        total_line=3.5,
        total_selected_side_type="under",
        total_goals=3,
        total_goal_buffer=buffer,
    )


def test_under_buffer_exit_closes_trade_when_bid_is_close_to_entry() -> None:
    row = trade()
    exits = under_buffer_exit_candidates([row], [observation(bid=0.76)], settings())

    assert len(exits) == 1
    assert exits[0].trade_id == row.trade_id
    assert exits[0].exit_bid == 0.76
    assert exits[0].exit_pnl_usd == -0.5
    assert row.status == "open"


def test_under_buffer_exit_ignores_low_bid() -> None:
    row = trade()
    exits = under_buffer_exit_candidates([row], [observation(bid=0.70)], settings())

    assert exits == []
    assert row.status == "open"


def test_under_buffer_exit_ignores_late_match() -> None:
    row = trade()
    exits = under_buffer_exit_candidates([row], [observation(bid=0.80, elapsed=86.0)], settings())

    assert exits == []
    assert row.status == "open"
