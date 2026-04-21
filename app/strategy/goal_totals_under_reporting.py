from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.normalize.models import MarketObservation, NormalizedMarket
from app.strategy.goal_totals_under_runtime import GoalTotalsUnderRuntime


def build_goal_totals_under_debug_rows(
    latest: pd.DataFrame,
    markets_by_key: dict[tuple[str, str], NormalizedMarket],
    matcher,
    runtime: GoalTotalsUnderRuntime,
    *,
    parse_dt,
    to_float,
    to_optional_float,
    to_bool,
) -> pd.DataFrame:
    if latest.empty:
        return pd.DataFrame()
    rows: list[dict] = []
    for _, row in latest.iterrows():
        market = markets_by_key.get((str(row.get("event_id", "")), str(row.get("market_id", ""))))
        if market is None:
            continue
        live_state = matcher.match(market)
        if live_state is None:
            continue
        total_goals = row.get("total_goals")
        try:
            total_goals = None if total_goals in ("", None) else int(float(total_goals))
        except (TypeError, ValueError):
            total_goals = None
        observation = MarketObservation(
            timestamp_utc=parse_dt(str(row.get("timestamp_utc", ""))) or datetime.now(timezone.utc),
            event_id=str(row.get("event_id", "")),
            event_slug=str(row.get("event_slug", "")),
            event_title=str(row.get("event_title", "")),
            market_id=str(row.get("market_id", "")),
            market_slug=str(row.get("market_slug", "")),
            question=str(row.get("question", "")),
            token_id=str(row.get("token_id", "")),
            side=str(row.get("side", "")),
            price=to_float(row.get("price")),
            bid=to_optional_float(row.get("bid")),
            ask=to_optional_float(row.get("ask")),
            spread=to_optional_float(row.get("spread")),
            liquidity=to_optional_float(row.get("liquidity")),
            last_trade_price=to_optional_float(row.get("last_trade_price")),
            sport=str(row.get("sport", "")),
            live=to_bool(row.get("live")),
            ended=to_bool(row.get("ended")),
            score=str(row.get("score", "")),
            period=str(row.get("period", "")),
            elapsed=to_optional_float(row.get("elapsed")),
            market_type=str(row.get("market_type", "")),
            total_line=to_optional_float(row.get("total_line")),
            total_selected_side_type=str(row.get("total_selected_side_type", "")),
            total_goals=total_goals,
            total_goal_buffer=to_optional_float(row.get("total_goal_buffer")),
            reason=str(row.get("reason", "")),
        )
        evaluation = runtime.evaluate(market, observation, live_state)
        if not evaluation.applies:
            continue
        payload = evaluation.payload
        rows.append(
            {
                "timestamp_utc": row.get("timestamp_utc", ""),
                "event_title": row.get("event_title", ""),
                "question": row.get("question", ""),
                "side": row.get("side", ""),
                "final_decision": "ENTER" if evaluation.enter else "NO ENTER",
                "rejection_reason": "" if evaluation.enter else evaluation.reason,
                "minute": payload.minute if payload else "",
                "score": payload.score if payload else row.get("score", ""),
                "total_line": payload.total_line if payload else row.get("total_line", ""),
                "total_goals": payload.total_goals if payload else row.get("total_goals", ""),
                "goal_buffer": payload.goal_buffer if payload else row.get("total_goal_buffer", ""),
                "shots_last_10": payload.shots_last_10 if payload else "",
                "shots_on_target_last_10": payload.shots_on_target_last_10 if payload else "",
                "attacks_last_10": payload.attacks_last_10 if payload else "",
                "dangerous_attacks_last_10": payload.dangerous_attacks_last_10 if payload else "",
                "corners_last_10": payload.corners_last_10 if payload else "",
                "total_shots_both_last_10": payload.total_shots_both_last_10 if payload else "",
                "total_dangerous_attacks_both_last_10": payload.total_dangerous_attacks_both_last_10 if payload else "",
                "total_corners_both_last_10": payload.total_corners_both_last_10 if payload else "",
                "pressure_trend_last_10": str(payload.pressure_trend_last_10) if payload else "",
                "shots_trend_last_10": str(payload.shots_trend_last_10) if payload else "",
                "dangerous_attacks_trend_last_10": str(payload.dangerous_attacks_trend_last_10) if payload else "",
                "tempo_change_last_10": str(payload.tempo_change_last_10) if payload else "",
                "goal_in_last_3min": bool(payload.goal_in_last_3min) if payload else False,
                "goal_in_last_5min": bool(payload.goal_in_last_5min) if payload else False,
                "red_card_in_last_10min": bool(payload.red_card_in_last_10min) if payload else False,
                "stable_for_2_snapshots": bool(payload.stable_for_2_snapshots) if payload else False,
                "stable_for_3_snapshots": bool(payload.stable_for_3_snapshots) if payload else False,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("timestamp_utc", ascending=False)
