from __future__ import annotations

from datetime import datetime, timezone

from app.normalize.models import MarketObservation
from app.paper_trader.trader import PaperTrader
from app.risk.limits import RiskManager


def settings(tmp_path):
    return {
        "strategy": {"stake_usd": 10.0, "targets": [0.99, 0.999]},
        "risk": {
            "max_daily_paper_trades": 100,
            "max_simultaneous_open_trades": 20,
            "max_entries_per_market": 5,
            "cooldown_seconds_per_market": 60,
            "kill_switch": False,
        },
        "capital_processes": {
            "enabled": True,
            "start_balance": 10.0,
            "target_balance": 21.0,
            "max_active_processes": 1,
            "allow_open_new_when_all_funds_locked": True,
        },
        "storage": {"capital_processes_json": str(tmp_path / "capital_processes.json")},
    }


def observation() -> MarketObservation:
    return MarketObservation(
        timestamp_utc=datetime.now(timezone.utc),
        event_id="e1",
        event_slug="match-a",
        event_title="Match A",
        market_id="m1",
        market_slug="m1",
        question="Will Team A win?",
        token_id="tok1",
        side="No",
        price=0.97,
        bid=0.96,
        ask=0.97,
        spread=0.01,
        liquidity=100.0,
        last_trade_price=0.97,
        sport="soccer",
        live=True,
        ended=False,
        score="1-0",
        period="2H",
        elapsed=76.0,
        reason="trade_eligible_price_held",
    )


def test_trader_uses_process_balance_as_stake(tmp_path) -> None:
    trader = PaperTrader(settings(tmp_path), RiskManager(settings(tmp_path)))
    trade = trader.maybe_enter(observation(), [])
    assert trade is not None
    assert trade.process_id != ""
    assert trade.stake_usd == 10.0
    assert trade.process_balance_before == 10.0
    trader.bind_entries([trade])
    assert trader.maybe_enter(observation(), [trade]) is None
