from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from app.strategy.goal_totals_under import GoalTotalsUnderInput
from app.strategy.proof_of_winning import TrendState
from app.strategy.proof_of_winning_metrics import (
    MatchWindowStats,
    diff_match_totals,
    event_flags_for_current,
    fixture_elapsed_from_detail,
    nearest_snapshot_before_elapsed,
    parse_dt,
    pressure_value,
    statistics_map,
    tempo_value,
    to_int_or_none,
    total_from_current_minus,
    trend_from_values,
)


class UnderWindowStats(BaseModel):
    shots_last_5: Optional[int] = None
    shots_on_target_last_5: Optional[int] = None
    shots_last_10: Optional[int] = None
    shots_on_target_last_10: Optional[int] = None
    dangerous_attacks_last_5: Optional[int] = None
    dangerous_attacks_last_10: Optional[int] = None
    attacks_last_5: Optional[int] = None
    attacks_last_10: Optional[int] = None
    corners_last_5: Optional[int] = None
    corners_last_10: Optional[int] = None


class UnderTrendMetrics(BaseModel):
    pressure_trend_last_10: TrendState = TrendState.UNKNOWN
    shots_trend_last_10: TrendState = TrendState.UNKNOWN
    dangerous_attacks_trend_last_10: TrendState = TrendState.UNKNOWN
    tempo_change_last_10: TrendState = TrendState.UNKNOWN


class UnderRollingMetrics(BaseModel):
    match: UnderWindowStats
    totals: MatchWindowStats
    trend: UnderTrendMetrics
    source_fields_present: list[str]
    data_confidence_flag: bool


def build_goal_totals_under_rolling_metrics(detail_history: list[dict[str, Any]]) -> UnderRollingMetrics:
    ordered = sorted(
        [row for row in detail_history if isinstance(row, dict)],
        key=lambda row: parse_dt(str(row.get("saved_at", ""))) or parse_dt("1970-01-01T00:00:00+00:00"),
    )
    if not ordered:
        return empty_metrics()

    current = ordered[-1]
    current_elapsed = fixture_elapsed_from_detail(current)
    if current_elapsed is None:
        return empty_metrics()

    current_stats = statistics_map(current)
    baseline_5 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 5)
    baseline_10 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 10)
    baseline_prev5 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 5)
    baseline_prev10 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 10)

    current_totals = match_stat_totals(current_stats)
    base5_totals = match_stat_totals(statistics_map(baseline_5)) if baseline_5 else {}
    base10_totals = match_stat_totals(statistics_map(baseline_10)) if baseline_10 else {}

    last5 = diff_flat_stats(current_totals, base5_totals) if baseline_5 else {}
    last10 = diff_flat_stats(current_totals, base10_totals) if baseline_10 else {}

    prev5 = None
    prev5_totals = None
    if baseline_prev5 and baseline_prev10:
        prev5_totals = diff_match_totals(statistics_map(baseline_prev5), statistics_map(baseline_prev10))
        prev5 = diff_flat_stats(
            match_stat_totals(statistics_map(baseline_prev5)),
            match_stat_totals(statistics_map(baseline_prev10)),
        )

    event_flags = event_flags_for_current(current, current_elapsed)
    trend = UnderTrendMetrics(
        pressure_trend_last_10=trend_from_values(
            pressure_value(last5),
            pressure_value(prev5 or {}),
        ),
        shots_trend_last_10=trend_from_values(
            last5.get("shots"),
            (prev5 or {}).get("shots"),
        ),
        dangerous_attacks_trend_last_10=trend_from_values(
            last5.get("dangerous_attacks"),
            (prev5 or {}).get("dangerous_attacks"),
        ),
        tempo_change_last_10=trend_from_values(
            tempo_value(
                {
                    "shots": total_from_current_minus(current_stats, baseline_5, "shots"),
                    "dangerous_attacks": total_from_current_minus(current_stats, baseline_5, "dangerous_attacks"),
                    "corners": total_from_current_minus(current_stats, baseline_5, "corners"),
                }
            ),
            tempo_value(prev5_totals or {}),
        ),
    )

    match = UnderWindowStats(
        shots_last_5=to_int_or_none(last5.get("shots")),
        shots_on_target_last_5=to_int_or_none(last5.get("shots_on_target")),
        shots_last_10=to_int_or_none(last10.get("shots")),
        shots_on_target_last_10=to_int_or_none(last10.get("shots_on_target")),
        dangerous_attacks_last_5=to_int_or_none(last5.get("dangerous_attacks")),
        dangerous_attacks_last_10=to_int_or_none(last10.get("dangerous_attacks")),
        attacks_last_5=to_int_or_none(last5.get("attacks")),
        attacks_last_10=to_int_or_none(last10.get("attacks")),
        corners_last_5=to_int_or_none(last5.get("corners")),
        corners_last_10=to_int_or_none(last10.get("corners")),
    )
    fields_present = []
    for field in (
        "shots_last_10",
        "shots_on_target_last_10",
        "dangerous_attacks_last_10",
        "attacks_last_10",
        "corners_last_10",
    ):
        if getattr(match, field) is not None:
            fields_present.append(field)

    return UnderRollingMetrics(
        match=match,
        totals=MatchWindowStats(
            total_shots_both_last_10=to_int_or_none(last10.get("shots")),
            total_dangerous_attacks_both_last_10=to_int_or_none(last10.get("dangerous_attacks")),
            total_corners_both_last_10=to_int_or_none(last10.get("corners")),
            goal_in_last_3min=event_flags["goal_in_last_3min"],
            goal_in_last_5min=event_flags["goal_in_last_5min"],
            red_card_in_last_10min=event_flags["red_card_in_last_10min"],
            time_since_last_goal=event_flags["time_since_last_goal"],
        ),
        trend=trend,
        source_fields_present=fields_present,
        data_confidence_flag=len(fields_present) >= 5,
    )


def populate_goal_totals_under_input_with_metrics(
    base: GoalTotalsUnderInput,
    metrics: UnderRollingMetrics,
) -> GoalTotalsUnderInput:
    return base.model_copy(
        update={
            "shots_last_5": metrics.match.shots_last_5,
            "shots_on_target_last_5": metrics.match.shots_on_target_last_5,
            "shots_last_10": metrics.match.shots_last_10,
            "shots_on_target_last_10": metrics.match.shots_on_target_last_10,
            "dangerous_attacks_last_5": metrics.match.dangerous_attacks_last_5,
            "dangerous_attacks_last_10": metrics.match.dangerous_attacks_last_10,
            "attacks_last_5": metrics.match.attacks_last_5,
            "attacks_last_10": metrics.match.attacks_last_10,
            "corners_last_5": metrics.match.corners_last_5,
            "corners_last_10": metrics.match.corners_last_10,
            "total_shots_both_last_10": metrics.totals.total_shots_both_last_10,
            "total_dangerous_attacks_both_last_10": metrics.totals.total_dangerous_attacks_both_last_10,
            "total_corners_both_last_10": metrics.totals.total_corners_both_last_10,
            "goal_in_last_3min": metrics.totals.goal_in_last_3min,
            "goal_in_last_5min": metrics.totals.goal_in_last_5min,
            "red_card_in_last_10min": metrics.totals.red_card_in_last_10min,
            "time_since_last_goal": metrics.totals.time_since_last_goal,
            "pressure_trend_last_10": metrics.trend.pressure_trend_last_10.value,
            "shots_trend_last_10": metrics.trend.shots_trend_last_10.value,
            "dangerous_attacks_trend_last_10": metrics.trend.dangerous_attacks_trend_last_10.value,
            "tempo_change_last_10": metrics.trend.tempo_change_last_10.value,
            "source_fields_present": metrics.source_fields_present,
            "data_confidence_flag": metrics.data_confidence_flag,
        }
    )


def match_stat_totals(stats_by_team: dict[str, dict[str, int]]) -> dict[str, int]:
    return {
        "shots": sum(team.get("shots", 0) for team in stats_by_team.values()),
        "shots_on_target": sum(team.get("shots_on_target", 0) for team in stats_by_team.values()),
        "dangerous_attacks": sum(team.get("dangerous_attacks", 0) for team in stats_by_team.values()),
        "attacks": sum(team.get("attacks", 0) for team in stats_by_team.values()),
        "corners": sum(team.get("corners", 0) for team in stats_by_team.values()),
    }


def diff_flat_stats(current: dict[str, int], baseline: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in {"shots", "shots_on_target", "dangerous_attacks", "attacks", "corners"}:
        if key not in current:
            continue
        out[key] = max(current.get(key, 0) - baseline.get(key, 0), 0)
    return out


def empty_metrics() -> UnderRollingMetrics:
    return UnderRollingMetrics(
        match=UnderWindowStats(),
        totals=MatchWindowStats(),
        trend=UnderTrendMetrics(),
        source_fields_present=[],
        data_confidence_flag=False,
    )
