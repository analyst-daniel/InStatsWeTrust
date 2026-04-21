from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.normalize.models import MarketObservation, PaperTrade
from app.risk.limits import RiskManager


class PaperTrader:
    def __init__(self, settings: dict, risk: RiskManager) -> None:
        strategy = settings["strategy"]
        self.stake_usd = float(strategy.get("stake_usd", 10))
        self.targets = [float(v) for v in strategy.get("targets", [0.99, 0.999])]
        self.risk = risk

    def maybe_enter(self, obs: MarketObservation, trades: list[PaperTrade]) -> PaperTrade | None:
        ok, _ = self.risk.can_enter(obs, trades)
        if not ok or obs.price <= 0:
            return None
        return PaperTrade(
            trade_id=str(uuid4()),
            entry_timestamp=datetime.now(timezone.utc),
            event_slug=obs.event_slug,
            event_title=obs.event_title,
            market_id=obs.market_id,
            market_slug=obs.market_slug,
            question=obs.question,
            token_id=obs.token_id,
            side=obs.side,
            entry_price=obs.price,
            stake_usd=self.stake_usd,
            shares=self.stake_usd / obs.price,
            elapsed=obs.elapsed,
            score=obs.score,
            period=obs.period,
            entry_reason=obs.reason,
            max_favorable_price=obs.price,
        )

    def update_open_trades(self, trades: list[PaperTrade], latest_by_token: dict[str, float], resolved_markets: dict[str, str] | None = None) -> list[PaperTrade]:
        now = datetime.now(timezone.utc)
        resolved_markets = resolved_markets or {}
        changed: list[PaperTrade] = []
        for trade in trades:
            if trade.status != "open":
                continue
            price = latest_by_token.get(trade.token_id)
            if price is not None:
                trade.max_favorable_price = max(trade.max_favorable_price, price)
                if price >= 0.99 and trade.first_hit_99_at is None:
                    trade.first_hit_99_at = now
                if price >= 0.999 and trade.first_hit_999_at is None:
                    trade.first_hit_999_at = now
                changed.append(trade)
            result = resolved_markets.get(trade.market_id)
            if result:
                trade.status = "resolved"
                trade.resolved_at = now
                trade.result = result
                trade.pnl_usd = self._pnl(trade, result)
                changed.append(trade)
        return changed

    @staticmethod
    def _pnl(trade: PaperTrade, result: str) -> float:
        if result.lower() == trade.side.lower():
            return round((1.0 - trade.entry_price) * trade.shares, 4)
        return round(-trade.stake_usd, 4)
