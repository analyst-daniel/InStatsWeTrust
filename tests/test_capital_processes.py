from __future__ import annotations

from datetime import datetime, timezone

from app.capital.processes import CapitalProcessManager
from app.normalize.models import PaperTrade


def settings(tmp_path):
    return {
        "capital_processes": {
            "enabled": True,
            "start_balance": 10.0,
            "target_balance": 21.0,
            "max_active_processes": 2,
            "allow_open_new_when_all_funds_locked": True,
        },
        "storage": {
            "capital_processes_json": str(tmp_path / "capital_processes.json"),
        },
    }


def make_trade(process_id: str, *, status: str, trade_id: str = "t1", stake_usd: float = 10.0, pnl_usd: float | None = None) -> PaperTrade:
    return PaperTrade(
        trade_id=trade_id,
        entry_timestamp=datetime.now(timezone.utc),
        event_slug="match-a",
        event_title="Match A",
        market_id="m1",
        market_slug="m1",
        question="Will Team A win?",
        token_id="tok1",
        side="No",
        entry_price=0.97,
        stake_usd=stake_usd,
        shares=stake_usd / 0.97,
        elapsed=76,
        score="1-0",
        period="2H",
        process_id=process_id,
        process_step=1,
        process_balance_before=stake_usd,
        process_target_balance=21.0,
        status=status,
        result="No" if status == "resolved" else "",
        pnl_usd=pnl_usd,
    )


def test_process_is_created_and_completed(tmp_path) -> None:
    manager = CapitalProcessManager(settings(tmp_path), tmp_path / "capital_processes.json")
    process = manager.assign_process([])
    assert process is not None
    open_trade = make_trade(process["process_id"], status="open")
    open_trade.trade_id = "trade-1"
    manager.bind_trade_entry(open_trade)
    resolved_trade = make_trade(process["process_id"], status="resolved", trade_id="trade-1", pnl_usd=11.5)
    manager.apply_trade_updates([resolved_trade])
    summary, rows = manager.summary([resolved_trade])
    assert summary["completed"] == 1
    assert rows[0]["status"] == "completed"
    assert rows[0]["current_balance"] >= 21.0


def test_second_process_created_when_first_locked(tmp_path) -> None:
    manager = CapitalProcessManager(settings(tmp_path), tmp_path / "capital_processes.json")
    first = manager.assign_process([])
    assert first is not None
    open_trade = make_trade(first["process_id"], status="open")
    open_trade.trade_id = "trade-1"
    manager.bind_trade_entry(open_trade)
    second = manager.assign_process([open_trade])
    assert second is not None
    assert second["process_id"] != first["process_id"]
