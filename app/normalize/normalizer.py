from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from .models import NormalizedMarket


def normalize_events(events: list[dict[str, Any]]) -> list[NormalizedMarket]:
    rows: list[NormalizedMarket] = []
    now = datetime.now(timezone.utc)
    for event in events:
        event_title = str(event.get("title") or event.get("name") or event.get("slug") or "")
        sport = classify_sport(event)
        markets = event.get("markets") if isinstance(event.get("markets"), list) else []
        for market in markets:
            normalized = normalize_market(event, market, sport=sport, timestamp=now)
            if normalized:
                rows.append(normalized)
    return rows


def normalize_standalone_markets(markets: list[dict[str, Any]]) -> list[NormalizedMarket]:
    rows: list[NormalizedMarket] = []
    now = datetime.now(timezone.utc)
    for market in markets:
        event_title = event_title_from_market(str(market.get("question") or ""), str(market.get("description") or ""))
        event = {
            "id": event_key(event_title),
            "slug": event_key(event_title),
            "title": event_title,
            "category": "",
            "startTime": market.get("gameStartTime") or market.get("endDate"),
            "endDate": market.get("endDate"),
            "active": market.get("active"),
            "closed": market.get("closed"),
        }
        normalized = normalize_market(event, market, sport=classify_market_sport(market), timestamp=now)
        if normalized:
            rows.append(normalized)
    return rows


def normalize_market(event: dict[str, Any], market: dict[str, Any], *, sport: str, timestamp: datetime) -> NormalizedMarket | None:
    outcomes = as_list(market.get("outcomes"))
    token_ids = as_list(market.get("clobTokenIds") or market.get("clob_token_ids"))
    if len(outcomes) < 2 or len(token_ids) < 2:
        return None
    best_ask = as_float(market.get("bestAsk") or market.get("best_ask"))
    best_bid = as_float(market.get("bestBid") or market.get("best_bid"))
    yes_bid = best_bid
    yes_ask = best_ask
    no_bid = None
    no_ask = None
    if best_ask is not None:
        no_bid = max(0.0, min(1.0, 1.0 - best_ask))
    if best_bid is not None:
        no_ask = max(0.0, min(1.0, 1.0 - best_bid))

    return NormalizedMarket(
        event_id=str(event.get("id") or event.get("slug") or ""),
        event_slug=str(event.get("slug") or ""),
        event_title=str(event.get("title") or event.get("name") or ""),
        market_id=str(market.get("id") or market.get("conditionId") or market.get("slug") or ""),
        market_slug=str(market.get("slug") or ""),
        question=str(market.get("question") or market.get("title") or market.get("slug") or ""),
        category=str(event.get("category") or ""),
        sport=sport,
        teams=derive_teams(str(event.get("title") or "")),
        end_date=str(market.get("endDate") or event.get("endDate") or ""),
        start_time=str(event.get("startTime") or event.get("startDate") or market.get("gameStartTime") or ""),
        active=bool(market.get("active", event.get("active", False))),
        closed=bool(market.get("closed", event.get("closed", False))),
        token_ids=[str(token_ids[0]), str(token_ids[1])],
        yes_token_id=str(token_ids[0]),
        no_token_id=str(token_ids[1]),
        outcomes=[str(outcomes[0]), str(outcomes[1])],
        best_bid_yes=yes_bid,
        best_ask_yes=yes_ask,
        best_bid_no=no_bid,
        best_ask_no=no_ask,
        spread=as_float(market.get("spread")),
        last_trade_price=as_float(market.get("lastTradePrice")),
        liquidity=as_float(market.get("liquidity") or market.get("liquidityNum")),
        volume=as_float(market.get("volume") or market.get("volumeNum")),
        timestamp_utc=timestamp,
        raw=market,
    )


def classify_sport(event: dict[str, Any]) -> str:
    text = " ".join(str(v).lower() for v in [event.get("title"), event.get("slug"), event.get("category"), json.dumps(event.get("tags", []), default=str)])
    if any(term in text for term in ["cricket", "nfl", "nba", "nhl", "mlb", "tennis", "dota", "lol", "league of legends", "esports", "e-sports", "counter-strike", "valorant"]):
        return "unknown"
    if any(term in text for term in ["soccer", "football", "fc", "cf", "uefa", "fifa", "liga", "mls", "serie"]):
        return "soccer"
    return "unknown"


def classify_market_sport(market: dict[str, Any]) -> str:
    text = " ".join(str(v).lower() for v in [market.get("question"), market.get("slug"), market.get("description"), market.get("sportsMarketType")])
    if any(term in text for term in ["cricket", "nfl", "nba", "nhl", "mlb", "tennis", "dota", "lol", "league of legends", "esports", "e-sports", "counter-strike", "valorant"]):
        return "unknown"
    if str(market.get("sportsMarketType") or "").lower().startswith("soccer") or " fc " in f" {text} " or " vs. " in text:
        return "soccer"
    return "unknown"


def market_type(question: str) -> str:
    q = question.lower()
    if "spread" in q or "handicap" in q:
        return "spread"
    if "o/u" in q or "over" in q or "under" in q:
        return "total"
    if "both teams to score" in q:
        return "btts"
    if "exact score" in q:
        return "exact_score"
    return "match"


def derive_teams(title: str) -> list[str]:
    parts = re.split(r"\s+vs\.?\s+|\s+@\s+", title, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        return [parts[0].strip(), parts[1].replace("- More Markets", "").strip()]
    return []


def event_title_from_market(title: str, description: str) -> str:
    if ":" in title and (" vs. " in title.lower() or " vs " in title.lower()):
        return title.split(":", 1)[0].strip()
    match = re.search(r"between\s+(.+?)\s+and\s+(.+?)(?:,|\s+scheduled|\.)", description, re.IGNORECASE)
    if match:
        return f"{match.group(1).strip()} vs. {match.group(2).strip()}"
    return title


def event_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def as_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
