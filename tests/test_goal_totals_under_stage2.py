from datetime import datetime, timezone

from app.normalize.models import LiveState, NormalizedMarket
from app.strategy.engine import StrategyEngine


def make_market(question: str = "Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5") -> NormalizedMarket:
    return NormalizedMarket(
        event_id="296790",
        event_slug="j1100-cer-kyo-2026-04-19-more-markets",
        event_title="Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        market_id="1674823",
        market_slug="j1100-cer-kyo-2026-04-19-ou-3pt5",
        question=question,
        sport="soccer",
        category="sports",
        teams=["Cerezo Osaka", "Kyoto Sanga FC"],
        active=True,
        closed=False,
        token_ids=["over-token", "under-token"],
        yes_token_id="over-token",
        no_token_id="under-token",
        outcomes=["Over", "Under"],
        best_bid_yes=0.96,
        best_ask_yes=0.97,
        best_bid_no=0.95,
        best_ask_no=0.96,
        timestamp_utc=datetime.now(timezone.utc),
    )


def make_live_state() -> LiveState:
    return LiveState(
        slug="cerezo-osaka-vs-kyoto-sanga-fc",
        sport="soccer",
        live=True,
        ended=False,
        score="2-0",
        period="2H",
        elapsed=78.0,
        last_update=datetime.now(timezone.utc),
        raw={},
    )


def test_strategy_engine_populates_totals_metadata_on_observation() -> None:
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
    decisions = engine.evaluate_market(make_market(), make_live_state())
    assert len(decisions) == 2
    under = next(row for row in decisions if row.observation.side == "Under")
    over = next(row for row in decisions if row.observation.side == "Over")
    assert under.observation.total_line == 3.5
    assert under.observation.total_selected_side_type == "under"
    assert under.observation.total_goals == 2
    assert under.observation.total_goal_buffer == 1.5
    assert over.observation.total_line == 3.5
    assert over.observation.total_selected_side_type == "over"
    assert over.observation.total_goals == 2
    assert over.observation.total_goal_buffer == 1.5
