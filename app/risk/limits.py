from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.normalize.models import MarketObservation, PaperTrade


class RiskManager:
    def __init__(self, settings: dict) -> None:
        risk = settings["risk"]
        self.max_daily_trades = int(risk.get("max_daily_paper_trades", risk.get("max_daily_trades", 100)))
        self.max_open_trades = int(risk.get("max_simultaneous_open_trades", 20))
        self.max_entries_per_market = int(risk.get("max_entries_per_market", 5))
        self.cooldown_seconds = int(risk.get("cooldown_seconds_per_market", 60))
        self.kill_switch = bool(risk.get("kill_switch", False))

    def can_enter(self, obs: MarketObservation, trades: list[PaperTrade]) -> tuple[bool, str]:
        if self.kill_switch:
            return False, "risk_kill_switch"
        open_trades = [t for t in trades if t.status == "open"]
        if len(open_trades) >= self.max_open_trades:
            return False, "risk_max_open_trades"
        today = datetime.now(timezone.utc).date()
        if sum(1 for t in trades if t.entry_timestamp.date() == today) >= self.max_daily_trades:
            return False, "risk_max_daily_trades"
        market_trades = [t for t in trades if t.market_id == obs.market_id]
        if len(market_trades) >= self.max_entries_per_market:
            return False, "risk_max_entries_per_market"
        if any(t.status == "open" and t.market_id == obs.market_id and t.token_id == obs.token_id for t in trades):
            return False, "risk_duplicate_open_outcome"
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.cooldown_seconds)
        if any(t.market_id == obs.market_id and t.entry_timestamp >= cutoff for t in trades):
            return False, "risk_market_cooldown"
        return True, "risk_ok"
