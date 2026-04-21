import pandas as pd

from app.strategy.spread_confirmation_calibration import (
    spread_line_bucket,
    spread_side_type_bucket,
    summarize_spread_confirmation_trades,
)


def test_spread_bucket_helpers() -> None:
    assert spread_line_bucket("Spread: Cerezo Osaka (-1.5)", "Cerezo Osaka") == "-1.5"
    assert spread_line_bucket("Spread: Cerezo Osaka (-1.5)", "Kyoto Sanga FC") == "+1.5"
    assert spread_side_type_bucket("Spread: Cerezo Osaka (-1.5)", "Cerezo Osaka") == "minus"
    assert spread_side_type_bucket("Spread: Cerezo Osaka (-1.5)", "Kyoto Sanga FC") == "plus"


def test_summarize_spread_confirmation_trades_groups_results() -> None:
    trades = pd.DataFrame(
        [
            {
                "trade_id": "1",
                "event_slug": "j2-aaa-bbb-2026-04-19",
                "question": "Spread: A (-1.5)",
                "side": "A",
                "entry_reason": "spread_minus_enter_price_held_5.0s",
                "elapsed": 76,
                "status": "resolved",
                "pnl_usd": 0.42,
            },
            {
                "trade_id": "2",
                "event_slug": "j2-ccc-ddd-2026-04-19",
                "question": "Spread: C (-2.5)",
                "side": "D",
                "entry_reason": "spread_plus_enter_price_held_5.0s",
                "elapsed": 84,
                "status": "resolved",
                "pnl_usd": -10.0,
            },
            {
                "trade_id": "3",
                "event_slug": "spl-eee-fff-2026-04-19",
                "question": "Will E win on 2026-04-19?",
                "side": "Yes",
                "entry_reason": "proof_of_winning_enter",
                "elapsed": 80,
                "status": "resolved",
                "pnl_usd": 0.11,
            },
        ]
    )
    artifacts = summarize_spread_confirmation_trades(trades)
    assert artifacts.summary["total"] == 2
    assert artifacts.summary["resolved"] == 2
    assert artifacts.summary["wins"] == 1
    assert artifacts.summary["losses"] == 1
    assert artifacts.summary["pnl_usd"] == -9.58
    assert set(artifacts.by_side_type["group"]) == {"minus", "plus"}
    assert set(artifacts.by_line["group"]) == {"-1.5", "+2.5"}
