from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.capital.processes import CapitalProcessManager
from app.normalize.models import MarketObservation, PaperTrade
from app.risk.limits import RiskManager
from app.utils.config import resolve_path


class PaperTrader:
    def __init__(self, settings: dict, risk: RiskManager) -> None:
        self.settings = settings
        strategy = settings["strategy"]
        self.stake_usd = float(strategy.get("stake_usd", 10))
        self.targets = [float(v) for v in strategy.get("targets", [0.99, 0.999])]
        self.risk = risk
        self.processes = CapitalProcessManager(settings, resolve_path(settings["storage"]["capital_processes_json"]))

    def maybe_enter(self, obs: MarketObservation, trades: list[PaperTrade], *, max_stake_usd_at_entry: float | None = None) -> PaperTrade | None:
        ok, _ = self.risk.can_enter(obs, trades)
        if not ok or obs.price <= 0:
            return None
        process = self.processes.assign_process(trades)
        if self.processes.enabled and process is None:
            return None
        stake_usd = float(process.get("current_balance", self.stake_usd)) if process else self.stake_usd
        process_id = str(process.get("process_id", "")) if process else ""
        process_step = int(process.get("step_count", 0)) + 1 if process else None
        process_target_balance = float(process.get("target_balance", 0.0)) if process else None
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
            stake_usd=stake_usd,
            max_stake_usd_at_entry=max_stake_usd_at_entry,
            shares=stake_usd / obs.price,
            elapsed=obs.elapsed,
            score=obs.score,
            period=obs.period,
            entry_reason=obs.reason,
            process_id=process_id,
            process_step=process_step,
            process_balance_before=stake_usd,
            process_target_balance=process_target_balance,
            max_favorable_price=obs.price,
        )

    def update_open_trades(
        self,
        trades: list[PaperTrade],
        latest_by_token: dict[str, float],
        resolved_markets: dict[str, str] | None = None,
    ) -> list[PaperTrade]:
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
        changed_by_id = {trade.trade_id: trade for trade in changed}
        changed = list(changed_by_id.values())
        self.processes.apply_trade_updates(changed)
        return changed

    def bind_entries(self, entries: list[PaperTrade]) -> None:
        for trade in entries:
            self.processes.bind_trade_entry(trade)

    @staticmethod
    def _pnl(trade: PaperTrade, result: str) -> float:
        if result.lower() == trade.side.lower():
            return round((1.0 - trade.entry_price) * trade.shares, 4)
        return round(-trade.stake_usd, 4)
