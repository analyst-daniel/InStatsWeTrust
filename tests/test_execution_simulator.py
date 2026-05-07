from __future__ import annotations

import pytest

from app.execution.simulator import DryRunExecutor, simulate_fill


def test_simulate_buy_fill_uses_asks_at_or_below_limit() -> None:
    book = {
        "bids": [{"price": "0.79", "size": "100"}],
        "asks": [
            {"price": "0.80", "size": "5"},
            {"price": "0.81", "size": "5"},
            {"price": "0.82", "size": "100"},
        ],
    }

    fill = simulate_fill(book, action="BUY", limit_price=0.81, requested_shares=8)

    assert fill["filled_shares"] == 8
    assert fill["levels_used"] == 2
    assert fill["notional_usd"] == pytest.approx(6.43)
    assert fill["avg_fill_price"] == pytest.approx(0.80375)
    assert fill["best_ask"] == 0.80


def test_simulate_sell_fill_uses_bids_at_or_above_limit() -> None:
    book = {
        "bids": [
            {"price": "0.82", "size": "3"},
            {"price": "0.81", "size": "3"},
            {"price": "0.80", "size": "100"},
        ],
        "asks": [{"price": "0.83", "size": "100"}],
    }

    fill = simulate_fill(book, action="SELL", limit_price=0.81, requested_shares=5)

    assert fill["filled_shares"] == 5
    assert fill["levels_used"] == 2
    assert fill["notional_usd"] == pytest.approx(4.08)
    assert fill["avg_fill_price"] == pytest.approx(0.816)
    assert fill["best_bid"] == 0.82


def test_live_execution_mode_is_disabled() -> None:
    class FakeClob:
        pass

    settings = {
        "execution": {"mode": "live"},
    }

    with pytest.raises(RuntimeError, match="Live execution is intentionally disabled"):
        DryRunExecutor(settings, FakeClob())  # type: ignore[arg-type]
