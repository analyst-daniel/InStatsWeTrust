from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.normalize.models import MarketObservation, PaperTrade


@dataclass(frozen=True)
class UnderBufferExitConfig:
    enabled: bool = False
    max_goal_buffer: float = 0.5
    max_elapsed: float = 85.0
    min_bid_to_entry_ratio: float = 0.95

    @classmethod
    def from_settings(cls, settings: dict) -> "UnderBufferExitConfig":
        cfg = settings.get("under_buffer_exit", {})
        return cls(
            enabled=bool(cfg.get("enabled", False)),
            max_goal_buffer=float(cfg.get("max_goal_buffer", 0.5)),
            max_elapsed=float(cfg.get("max_elapsed", 85.0)),
            min_bid_to_entry_ratio=float(cfg.get("min_bid_to_entry_ratio", 0.95)),
        )


@dataclass(frozen=True)
class UnderBufferExit:
    trade_id: str
    timestamp_utc: datetime
    event_title: str
    market_id: str
    question: str
    token_id: str
    entry_price: float
    stake_usd: float
    shares: float
    exit_bid: float
    exit_pnl_usd: float
    score: str
    elapsed: float
    total_goal_buffer: float
    reason: str = "under_buffer_exit_0_5"


def under_buffer_exit_candidates(
    trades: list[PaperTrade],
    observations: list[MarketObservation],
    settings: dict,
    *,
    now: datetime | None = None,
) -> list[PaperTrade]:
    config = UnderBufferExitConfig.from_settings(settings)
    if not config.enabled:
        return []

    observations_by_token = {
        observation.token_id: observation
        for observation in observations
        if observation.side.lower() == "under"
    }
    exits: list[UnderBufferExit] = []
    timestamp = now or datetime.now(timezone.utc)
    for trade in trades:
        if trade.status != "open" or trade.side.lower() != "under":
            continue
        observation = observations_by_token.get(trade.token_id)
        if observation is None or not should_exit_under_buffer(trade, observation, config):
            continue
        bid = float(observation.bid or 0.0)
        exits.append(
            UnderBufferExit(
                trade_id=trade.trade_id,
                timestamp_utc=timestamp,
                event_title=trade.event_title,
                market_id=trade.market_id,
                question=trade.question,
                token_id=trade.token_id,
                entry_price=trade.entry_price,
                stake_usd=trade.stake_usd,
                shares=trade.shares,
                exit_bid=bid,
                exit_pnl_usd=round((bid - trade.entry_price) * trade.shares, 4),
                score=observation.score,
                elapsed=float(observation.elapsed or 0.0),
                total_goal_buffer=float(observation.total_goal_buffer or 0.0),
            )
        )
    return exits


def should_exit_under_buffer(
    trade: PaperTrade,
    observation: MarketObservation,
    config: UnderBufferExitConfig,
) -> bool:
    if observation.total_goal_buffer is None or observation.elapsed is None or observation.bid is None:
        return False
    if observation.total_goal_buffer > config.max_goal_buffer:
        return False
    if observation.elapsed > config.max_elapsed:
        return False
    return float(observation.bid) >= float(trade.entry_price) * config.min_bid_to_entry_ratio
