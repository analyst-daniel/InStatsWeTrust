import pandas as pd

from app.strategy.proof_of_winning_calibration import infer_market_type, summarize_proof_of_winning_trades


def test_infer_market_type_variants() -> None:
    assert infer_market_type("Will Cerezo Osaka win on 2026-04-19?") == "match"
    assert infer_market_type("Spread: Cerezo Osaka (-1.5)") == "spread"
    assert infer_market_type("Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5") == "total"
    assert infer_market_type("Both Teams To Score") == "btts"
    assert infer_market_type("Exact Score: 2-0") == "exact"


def test_summarize_proof_of_winning_trades_groups_resolved_results() -> None:
    trades = pd.DataFrame(
        [
            {
                "trade_id": "1",
                "event_slug": "ucl-aaa-bbb-2026-04-19",
                "question": "Will A win on 2026-04-19?",
                "entry_reason": "proof_of_winning_enter",
                "elapsed": 76,
                "status": "resolved",
                "pnl_usd": 0.42,
            },
            {
                "trade_id": "2",
                "event_slug": "ucl-ccc-ddd-2026-04-19",
                "question": "Spread: C (-1.5)",
                "entry_reason": "proof_of_winning_enter",
                "elapsed": 84,
                "status": "resolved",
                "pnl_usd": -10.0,
            },
            {
                "trade_id": "3",
                "event_slug": "spl-eee-fff-2026-04-19",
                "question": "Will E win on 2026-04-19?",
                "entry_reason": "other_strategy",
                "elapsed": 80,
                "status": "resolved",
                "pnl_usd": 0.11,
            },
        ]
    )
    artifacts = summarize_proof_of_winning_trades(trades)
    assert artifacts.summary["total"] == 2
    assert artifacts.summary["resolved"] == 2
    assert artifacts.summary["wins"] == 1
    assert artifacts.summary["losses"] == 1
    assert artifacts.summary["pnl_usd"] == -9.58
    assert list(artifacts.by_market_type["group"]) == ["match", "spread"]
    assert "UEFA Champions League" in list(artifacts.by_league["group"])
