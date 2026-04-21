from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.normalize.models import MarketObservation
from app.strategy.hold_confirm import HoldConfirmation


def obs() -> MarketObservation:
    return MarketObservation(
        timestamp_utc=datetime.now(timezone.utc),
        event_id="e1",
        event_slug="e1",
        event_title="Team A FC vs. Team B FC",
        market_id="m1",
        market_slug="m1",
        question="Will Team A win?",
        token_id="t1",
        side="No",
        price=0.97,
        sport="soccer",
        live=True,
        ended=False,
        elapsed=76,
    )


def test_hold_requires_minimum_seconds(tmp_path: Path) -> None:
    hold = HoldConfirmation(tmp_path / "hold.json", 5)
    first_ok, _ = hold.check(obs())
    assert not first_ok
    key = hold.key(obs())
    hold.state[key]["first_seen_at"] = (datetime.now(timezone.utc) - timedelta(seconds=6)).isoformat()
    second_ok, reason = hold.check(obs())
    assert second_ok
    assert reason.startswith("price_held_")
