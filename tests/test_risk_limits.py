from datetime import datetime, timezone

from app.normalize.models import MarketObservation, PaperTrade
from app.risk.limits import RiskManager


def settings() -> dict:
    return {
        "risk": {
            "max_daily_paper_trades": 100,
            "max_simultaneous_open_trades": 20,
            "max_entries_per_market": 5,
            "cooldown_seconds_per_market": 60,
            "kill_switch": False,
        }
    }


def make_obs(market_id: str, token_id: str, question: str = "Cerezo O/U 4.5") -> MarketObservation:
    now = datetime.now(timezone.utc)
    return MarketObservation(
        event_id="296790",
        event_slug="j1100-cer-kyo-2026-04-18-more-markets",
        event_title="Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        market_id=market_id,
        market_slug=f"slug-{market_id}",
        question=question,
        category="sports",
        sport="soccer",
        token_ids=[token_id],
        yes_token_id=None,
        no_token_id=None,
        best_bid_yes=None,
        best_ask_yes=None,
        best_bid_no=None,
        best_ask_no=None,
        spread=0.01,
        last_trade_price=0.95,
        timestamp_utc=now,
        side="Under",
        token_id=token_id,
        price=0.95,
        bid=0.91,
        ask=0.95,
        liquidity=1000.0,
        live=True,
        ended=False,
        score="2-0",
        period="2H",
        elapsed=76.0,
        reason="trade_eligible_price_held_10.0s",
    )


def make_trade(market_id: str, token_id: str) -> PaperTrade:
    now = datetime.now(timezone.utc)
    return PaperTrade(
        trade_id=f"trade-{market_id}-{token_id}",
        entry_timestamp=now,
        event_slug="j1100-cer-kyo-2026-04-18-more-markets",
        event_title="Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        market_id=market_id,
        market_slug=f"slug-{market_id}",
        question="existing market",
        token_id=token_id,
        side="Under",
        entry_price=0.95,
        stake_usd=10.0,
        shares=10.0 / 0.95,
        elapsed=76.0,
        score="2-0",
        period="2H",
        status="open",
        max_favorable_price=0.95,
    )


def test_allows_multiple_open_trades_for_same_event_if_market_differs() -> None:
    risk = RiskManager(settings())
    existing = [make_trade("1683189", "token-under-4.5")]
    obs = make_obs("1683188", "token-under-3.5", "Cerezo O/U 3.5")
    ok, reason = risk.can_enter(obs, existing)
    assert ok is True
    assert reason == "risk_ok"


def test_blocks_exact_duplicate_open_outcome() -> None:
    risk = RiskManager(settings())
    existing = [make_trade("1683189", "token-under-4.5")]
    obs = make_obs("1683189", "token-under-4.5", "Cerezo O/U 4.5")
    ok, reason = risk.can_enter(obs, existing)
    assert ok is False
    assert reason == "risk_duplicate_open_outcome"
