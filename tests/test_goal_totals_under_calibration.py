import pandas as pd

from app.strategy.goal_totals_under_calibration import summarize_goal_totals_under_trades


def test_summarize_goal_totals_under_trades_groups_resolved_results() -> None:
    trades = pd.DataFrame(
        [
            {
                "trade_id": "t1",
                "event_slug": "j1100-cer-kyo-2026-04-18-more-markets",
                "question": "Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5",
                "side": "Under",
                "elapsed": 78,
                "entry_reason": "goal_totals_under_enter",
                "status": "resolved",
                "pnl_usd": 0.4123,
            },
            {
                "trade_id": "t2",
                "event_slug": "j1100-cer-kyo-2026-04-18-more-markets",
                "question": "Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5",
                "side": "Under",
                "elapsed": 82,
                "entry_reason": "goal_totals_under_enter",
                "status": "resolved",
                "pnl_usd": -10.0,
            },
            {
                "trade_id": "t3",
                "event_slug": "ucl-aaa-bbb-2026-04-18-more-markets",
                "question": "AAA vs BBB: O/U 4.5",
                "side": "Under",
                "elapsed": 86,
                "entry_reason": "goal_totals_under_enter",
                "status": "open",
                "pnl_usd": None,
            },
            {
                "trade_id": "t4",
                "event_slug": "j1100-cer-kyo-2026-04-18-more-markets",
                "question": "Spread: Cerezo Osaka (-1.5)",
                "side": "Cerezo Osaka",
                "elapsed": 80,
                "entry_reason": "spread_minus_enter",
                "status": "resolved",
                "pnl_usd": 0.3,
            },
        ]
    )

    artifacts = summarize_goal_totals_under_trades(trades)

    assert artifacts.summary["total"] == 3
    assert artifacts.summary["resolved"] == 2
    assert artifacts.summary["wins"] == 1
    assert artifacts.summary["losses"] == 1
    assert artifacts.summary["pnl_usd"] == round(0.4123 - 10.0, 4)
    assert artifacts.summary["win_rate"] == "50.0%"

    assert not artifacts.by_line.empty
    assert artifacts.by_line.iloc[0]["group"] == "3.5"

    assert not artifacts.by_entry_bucket.empty
    assert set(artifacts.by_entry_bucket["group"].tolist()) >= {"75-79", "80-84"}

    assert not artifacts.by_league.empty
    assert "J1 League" in set(artifacts.by_league["group"].tolist())
