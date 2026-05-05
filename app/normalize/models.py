from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class NormalizedMarket(BaseModel):
    event_id: str
    event_slug: str = ""
    event_title: str
    market_id: str
    market_slug: str = ""
    question: str
    category: str = ""
    sport: str = ""
    teams: list[str] = Field(default_factory=list)
    end_date: str = ""
    start_time: str = ""
    active: bool = False
    closed: bool = False
    token_ids: list[str] = Field(default_factory=list)
    yes_token_id: str = ""
    no_token_id: str = ""
    outcomes: list[str] = Field(default_factory=list)
    best_bid_yes: Optional[float] = None
    best_ask_yes: Optional[float] = None
    best_bid_no: Optional[float] = None
    best_ask_no: Optional[float] = None
    spread: Optional[float] = None
    last_trade_price: Optional[float] = None
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    timestamp_utc: datetime
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)


class LiveState(BaseModel):
    slug: str
    sport: str = ""
    live: bool = False
    ended: bool = False
    score: str = ""
    period: str = ""
    elapsed: Optional[float] = None
    last_update: datetime
    raw: dict[str, Any] = Field(default_factory=dict)


class MarketObservation(BaseModel):
    timestamp_utc: datetime
    event_id: str
    event_slug: str
    event_title: str
    market_id: str
    market_slug: str
    question: str
    token_id: str
    side: str
    price: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    liquidity: Optional[float] = None
    last_trade_price: Optional[float] = None
    sport: str
    live: bool
    ended: bool
    score: str = ""
    period: str = ""
    elapsed: Optional[float] = None
    market_type: str = ""
    spread_listed_team: str = ""
    spread_listed_line: Optional[float] = None
    spread_listed_side_type: str = ""
    spread_selected_team: str = ""
    spread_selected_line: Optional[float] = None
    spread_selected_side_type: str = ""
    total_line: Optional[float] = None
    total_selected_side_type: str = ""
    total_goals: Optional[int] = None
    total_goal_buffer: Optional[float] = None
    reason: str = ""


class PaperTrade(BaseModel):
    trade_id: str
    entry_timestamp: datetime
    event_slug: str
    event_title: str
    market_id: str
    market_slug: str
    question: str
    token_id: str
    side: str
    entry_price: float
    stake_usd: float
    max_stake_usd_at_entry: Optional[float] = None
    shares: float
    elapsed: Optional[float]
    score: str = ""
    period: str = ""
    entry_reason: str = ""
    process_id: str = ""
    process_step: Optional[int] = None
    process_balance_before: Optional[float] = None
    process_target_balance: Optional[float] = None
    status: str = "open"
    first_hit_99_at: Optional[datetime] = None
    first_hit_999_at: Optional[datetime] = None
    max_favorable_price: float = 0.0
    resolved_at: Optional[datetime] = None
    result: str = ""
    pnl_usd: Optional[float] = None
