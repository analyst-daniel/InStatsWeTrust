from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.market_data.clob_client import ClobClient, to_float
from app.normalize.models import MarketObservation, PaperTrade
from app.paper_trader.exit_rules import UnderBufferExit


@dataclass
class SimulatedExecution:
    execution_id: str
    timestamp_utc: datetime
    mode: str
    action: str
    status: str
    trade_id: str
    event_title: str
    market_id: str
    question: str
    token_id: str
    side: str
    limit_price: float
    requested_shares: float
    filled_shares: float
    avg_fill_price: float
    notional_usd: float
    best_bid: float | None
    best_ask: float | None
    levels_used: int
    reason: str


@dataclass(frozen=True)
class ExecutionConfig:
    mode: str = "dry_run"
    gate_entries: bool = True
    require_full_fill: bool = True

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "ExecutionConfig":
        raw = settings.get("execution", {})
        return cls(
            mode=str(raw.get("mode", "dry_run")).lower(),
            gate_entries=bool(raw.get("gate_entries", True)),
            require_full_fill=bool(raw.get("require_full_fill", True)),
        )


class DryRunExecutor:
    def __init__(self, settings: dict[str, Any], clob_client: ClobClient) -> None:
        self.config = ExecutionConfig.from_settings(settings)
        self.clob_client = clob_client
        if self.config.mode == "live":
            raise RuntimeError("Live execution is intentionally disabled. Use execution.mode=dry_run.")

    @property
    def enabled(self) -> bool:
        return self.config.mode in {"dry_run", "paper"}

    @property
    def gate_entries(self) -> bool:
        return self.config.mode == "dry_run" and self.config.gate_entries

    def simulate_entry(self, trade: PaperTrade, obs: MarketObservation) -> SimulatedExecution:
        return self._simulate(
            execution_id=f"buy:{trade.trade_id}",
            action="BUY",
            trade=trade,
            token_id=trade.token_id,
            side=trade.side,
            limit_price=trade.entry_price,
            requested_shares=trade.shares,
            event_title=trade.event_title,
            market_id=trade.market_id,
            question=trade.question,
            reason=obs.reason or trade.entry_reason or "entry",
        )

    def simulate_under_buffer_exit(self, exit_row: UnderBufferExit) -> SimulatedExecution:
        trade = PaperTrade(
            trade_id=exit_row.trade_id,
            entry_timestamp=exit_row.timestamp_utc,
            event_slug="",
            event_title=exit_row.event_title,
            market_id=exit_row.market_id,
            market_slug="",
            question=exit_row.question,
            token_id=exit_row.token_id,
            side="Under",
            entry_price=exit_row.entry_price,
            stake_usd=exit_row.stake_usd,
            shares=exit_row.shares,
            elapsed=exit_row.elapsed,
            score=exit_row.score,
            period="",
        )
        return self._simulate(
            execution_id=f"sell_under_buffer:{exit_row.trade_id}",
            action="SELL",
            trade=trade,
            token_id=exit_row.token_id,
            side="Under",
            limit_price=exit_row.exit_bid,
            requested_shares=exit_row.shares,
            event_title=exit_row.event_title,
            market_id=exit_row.market_id,
            question=exit_row.question,
            reason=exit_row.reason,
        )

    def _simulate(
        self,
        *,
        execution_id: str,
        action: str,
        trade: PaperTrade,
        token_id: str,
        side: str,
        limit_price: float,
        requested_shares: float,
        event_title: str,
        market_id: str,
        question: str,
        reason: str,
    ) -> SimulatedExecution:
        if self.config.mode == "paper":
            return SimulatedExecution(
                execution_id=execution_id,
                timestamp_utc=datetime.now(timezone.utc),
                mode=self.config.mode,
                action=action,
                status="paper_not_checked",
                trade_id=trade.trade_id,
                event_title=event_title,
                market_id=market_id,
                question=question,
                token_id=token_id,
                side=side,
                limit_price=limit_price,
                requested_shares=requested_shares,
                filled_shares=0.0,
                avg_fill_price=0.0,
                notional_usd=0.0,
                best_bid=None,
                best_ask=None,
                levels_used=0,
                reason=reason,
            )
        try:
            book = self.clob_client.get_book(token_id)
        except Exception:
            return SimulatedExecution(
                execution_id=execution_id,
                timestamp_utc=datetime.now(timezone.utc),
                mode=self.config.mode,
                action=action,
                status="skipped_clob_error",
                trade_id=trade.trade_id,
                event_title=event_title,
                market_id=market_id,
                question=question,
                token_id=token_id,
                side=side,
                limit_price=limit_price,
                requested_shares=round(requested_shares, 8),
                filled_shares=0.0,
                avg_fill_price=0.0,
                notional_usd=0.0,
                best_bid=None,
                best_ask=None,
                levels_used=0,
                reason=reason,
            )
        fill = simulate_fill(book, action=action, limit_price=limit_price, requested_shares=requested_shares)
        status = "filled"
        if fill["filled_shares"] <= 0:
            status = "skipped_no_liquidity"
        elif fill["filled_shares"] < requested_shares:
            status = "partial_fill"
        if self.config.require_full_fill and status == "partial_fill":
            status = "skipped_partial_fill"
        return SimulatedExecution(
            execution_id=execution_id,
            timestamp_utc=datetime.now(timezone.utc),
            mode=self.config.mode,
            action=action,
            status=status,
            trade_id=trade.trade_id,
            event_title=event_title,
            market_id=market_id,
            question=question,
            token_id=token_id,
            side=side,
            limit_price=limit_price,
            requested_shares=round(requested_shares, 8),
            filled_shares=round(fill["filled_shares"], 8),
            avg_fill_price=round(fill["avg_fill_price"], 6),
            notional_usd=round(fill["notional_usd"], 4),
            best_bid=fill["best_bid"],
            best_ask=fill["best_ask"],
            levels_used=int(fill["levels_used"]),
            reason=reason,
        )


def simulate_fill(
    book: dict[str, Any],
    *,
    action: str,
    limit_price: float,
    requested_shares: float,
) -> dict[str, float | int | None]:
    bids = parse_levels(book.get("bids", []), reverse=True)
    asks = parse_levels(book.get("asks", []), reverse=False)
    if action.upper() == "BUY":
        eligible = [(price, size) for price, size in asks if price <= limit_price]
    else:
        eligible = [(price, size) for price, size in bids if price >= limit_price]
    remaining = requested_shares
    filled = 0.0
    notional = 0.0
    levels_used = 0
    for price, size in eligible:
        if remaining <= 0:
            break
        take = min(size, remaining)
        filled += take
        notional += take * price
        remaining -= take
        levels_used += 1
    avg = notional / filled if filled > 0 else 0.0
    return {
        "filled_shares": filled,
        "avg_fill_price": avg,
        "notional_usd": notional,
        "levels_used": levels_used,
        "best_bid": bids[0][0] if bids else None,
        "best_ask": asks[0][0] if asks else None,
    }


def parse_levels(raw_levels: object, *, reverse: bool) -> list[tuple[float, float]]:
    if not isinstance(raw_levels, list):
        return []
    levels: list[tuple[float, float]] = []
    for level in raw_levels:
        if not isinstance(level, dict):
            continue
        price = to_float(level.get("price"))
        size = to_float(level.get("size"))
        if price is None or size is None or size <= 0:
            continue
        levels.append((price, size))
    return sorted(levels, key=lambda row: row[0], reverse=reverse)
