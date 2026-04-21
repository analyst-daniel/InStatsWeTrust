from __future__ import annotations

import json
from typing import Any


def resolved_outcome_from_market(market: dict[str, Any]) -> str | None:
    if not bool(market.get("closed")):
        return None

    for key in ["winner", "winningOutcome", "resolvedOutcome", "winning_outcome"]:
        value = market.get(key)
        if value:
            return str(value)

    outcomes = as_list(market.get("outcomes"))
    prices = as_list(market.get("outcomePrices") or market.get("outcome_prices"))
    if len(outcomes) >= 2 and len(prices) >= 2:
        parsed_prices = [as_float(v) for v in prices]
        valid = [(idx, price) for idx, price in enumerate(parsed_prices) if price is not None]
        if valid:
            winner_idx, winner_price = max(valid, key=lambda item: item[1])
            loser_prices = [price for idx, price in valid if idx != winner_idx]
            if winner_price >= 0.999 or (winner_price >= 0.99 and all(price <= 0.01 for price in loser_prices)):
                return str(outcomes[winner_idx])

    return None


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
