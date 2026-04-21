from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from app.strategy.proof_of_winning import TrendState
from app.strategy.proof_of_winning_metrics import (
    MatchWindowStats,
    TeamWindowStats,
    diff_match_totals,
    diff_team_stats,
    event_flags_for_current,
    fixture_elapsed_from_detail,
    fixture_score,
    fixture_teams,
    nearest_snapshot_before_elapsed,
    parse_dt,
    pressure_value,
    statistics_map,
    tempo_value,
    to_int_or_none,
    total_from_current_minus,
    trend_from_values,
)
from app.strategy.spread_confirmation import SpreadConfirmationInput


class SpreadTrendMetrics(BaseModel):
    leader_pressure_trend_last_10: TrendState = TrendState.UNKNOWN
    underdog_pressure_trend_last_10: TrendState = TrendState.UNKNOWN
    shots_trend_last_10: TrendState = TrendState.UNKNOWN
    dangerous_attacks_trend_last_10: TrendState = TrendState.UNKNOWN
    tempo_change_last_10: TrendState = TrendState.UNKNOWN


class SpreadRollingMetrics(BaseModel):
    leader: TeamWindowStats
    underdog: TeamWindowStats
    match: MatchWindowStats
    trend: SpreadTrendMetrics
    source_fields_present: list[str]
    data_confidence_flag: bool


def build_spread_rolling_metrics(detail_history: list[dict[str, Any]]) -> SpreadRollingMetrics:
    ordered = sorted(
        [row for row in detail_history if isinstance(row, dict)],
        key=lambda row: parse_dt(str(row.get("saved_at") or "")) or parse_dt("1970-01-01T00:00:00+00:00"),
    )
    if not ordered:
        return empty_metrics()

    current = ordered[-1]
    current_elapsed = fixture_elapsed_from_detail(current)
    if current_elapsed is None:
        return empty_metrics()

    home_team, away_team = fixture_teams(current)
    home_goals, away_goals = fixture_score(current)
    if home_goals == away_goals:
        return empty_metrics()

    leader_team = home_team if home_goals > away_goals else away_team
    underdog_team = away_team if home_goals > away_goals else home_team

    current_stats = statistics_map(current)
    leader_now = current_stats.get(leader_team, {})
    underdog_now = current_stats.get(underdog_team, {})
    baseline_5 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 5)
    baseline_10 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 10)
    baseline_prev5 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 5)
    baseline_prev10 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 10)

    leader_5 = diff_team_stats(leader_now, statistics_map(baseline_5).get(leader_team, {})) if baseline_5 else {}
    leader_10 = diff_team_stats(leader_now, statistics_map(baseline_10).get(leader_team, {})) if baseline_10 else {}
    underdog_5 = diff_team_stats(underdog_now, statistics_map(baseline_5).get(underdog_team, {})) if baseline_5 else {}
    underdog_10 = diff_team_stats(underdog_now, statistics_map(baseline_10).get(underdog_team, {})) if baseline_10 else {}

    total_10 = diff_match_totals(current_stats, statistics_map(baseline_10)) if baseline_10 else {}
    prev5_totals = None
    if baseline_prev5 and baseline_prev10:
        prev5_totals = diff_match_totals(statistics_map(baseline_prev5), statistics_map(baseline_prev10))

    prev5_leader = None
    prev5_underdog = None
    if baseline_prev5 and baseline_prev10:
        prev5_leader = diff_team_stats(
            statistics_map(baseline_prev5).get(leader_team, {}),
            statistics_map(baseline_prev10).get(leader_team, {}),
        )
        prev5_underdog = diff_team_stats(
            statistics_map(baseline_prev5).get(underdog_team, {}),
            statistics_map(baseline_prev10).get(underdog_team, {}),
        )

    event_flags = event_flags_for_current(current, current_elapsed)
    trend = SpreadTrendMetrics(
        leader_pressure_trend_last_10=trend_from_values(
            pressure_value(leader_5),
            pressure_value(prev5_leader or {}),
        ),
        underdog_pressure_trend_last_10=trend_from_values(
            pressure_value(underdog_5),
            pressure_value(prev5_underdog or {}),
        ),
        shots_trend_last_10=trend_from_values(
            underdog_5.get("shots"),
            (prev5_underdog or {}).get("shots"),
        ),
        dangerous_attacks_trend_last_10=trend_from_values(
            underdog_5.get("dangerous_attacks"),
            (prev5_underdog or {}).get("dangerous_attacks"),
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

    leader_stats = team_stats_from_diffs(leader_5, leader_10)
    underdog_stats = team_stats_from_diffs(underdog_5, underdog_10)
    fields_present = []
    for prefix, stats in (("leader", leader_stats), ("underdog", underdog_stats)):
        for field in ("shots_last_10", "shots_on_target_last_10", "dangerous_attacks_last_10", "corners_last_10"):
            if getattr(stats, field) is not None:
                fields_present.append(f"{prefix}_{field}")

    return SpreadRollingMetrics(
        leader=leader_stats,
        underdog=underdog_stats,
        match=MatchWindowStats(
            total_shots_both_last_10=to_int_or_none(total_10.get("shots")),
            total_dangerous_attacks_both_last_10=to_int_or_none(total_10.get("dangerous_attacks")),
            total_corners_both_last_10=to_int_or_none(total_10.get("corners")),
            goal_in_last_3min=event_flags["goal_in_last_3min"],
            goal_in_last_5min=event_flags["goal_in_last_5min"],
            red_card_in_last_10min=event_flags["red_card_in_last_10min"],
            time_since_last_goal=event_flags["time_since_last_goal"],
        ),
        trend=trend,
        source_fields_present=fields_present,
        data_confidence_flag=len(fields_present) >= 8,
    )


def populate_spread_input_with_metrics(base: SpreadConfirmationInput, metrics: SpreadRollingMetrics) -> SpreadConfirmationInput:
    return base.model_copy(
        update={
            "leader_shots_last_5": metrics.leader.shots_last_5,
            "leader_shots_on_target_last_5": metrics.leader.shots_on_target_last_5,
            "leader_shots_last_10": metrics.leader.shots_last_10,
            "leader_shots_on_target_last_10": metrics.leader.shots_on_target_last_10,
            "leader_dangerous_attacks_last_5": metrics.leader.dangerous_attacks_last_5,
            "leader_dangerous_attacks_last_10": metrics.leader.dangerous_attacks_last_10,
            "leader_corners_last_5": metrics.leader.corners_last_5,
            "leader_corners_last_10": metrics.leader.corners_last_10,
            "underdog_shots_last_5": metrics.underdog.shots_last_5,
            "underdog_shots_on_target_last_5": metrics.underdog.shots_on_target_last_5,
            "underdog_shots_last_10": metrics.underdog.shots_last_10,
            "underdog_shots_on_target_last_10": metrics.underdog.shots_on_target_last_10,
            "underdog_dangerous_attacks_last_5": metrics.underdog.dangerous_attacks_last_5,
            "underdog_dangerous_attacks_last_10": metrics.underdog.dangerous_attacks_last_10,
            "underdog_corners_last_5": metrics.underdog.corners_last_5,
            "underdog_corners_last_10": metrics.underdog.corners_last_10,
            "total_shots_both_last_10": metrics.match.total_shots_both_last_10,
            "total_dangerous_attacks_both_last_10": metrics.match.total_dangerous_attacks_both_last_10,
            "total_corners_both_last_10": metrics.match.total_corners_both_last_10,
            "goal_in_last_3min": metrics.match.goal_in_last_3min,
            "goal_in_last_5min": metrics.match.goal_in_last_5min,
            "red_card_in_last_10min": metrics.match.red_card_in_last_10min,
            "time_since_last_goal": metrics.match.time_since_last_goal,
            "leader_pressure_trend_last_10": metrics.trend.leader_pressure_trend_last_10.value,
            "underdog_pressure_trend_last_10": metrics.trend.underdog_pressure_trend_last_10.value,
            "shots_trend_last_10": metrics.trend.shots_trend_last_10.value,
            "dangerous_attacks_trend_last_10": metrics.trend.dangerous_attacks_trend_last_10.value,
            "tempo_change_last_10": metrics.trend.tempo_change_last_10.value,
            "source_fields_present": metrics.source_fields_present,
            "data_confidence_flag": metrics.data_confidence_flag,
        }
    )


def team_stats_from_diffs(last_5: dict[str, int], last_10: dict[str, int]) -> TeamWindowStats:
    return TeamWindowStats(
        shots_last_5=to_int_or_none(last_5.get("shots")),
        shots_on_target_last_5=to_int_or_none(last_5.get("shots_on_target")),
        shots_last_10=to_int_or_none(last_10.get("shots")),
        shots_on_target_last_10=to_int_or_none(last_10.get("shots_on_target")),
        dangerous_attacks_last_5=to_int_or_none(last_5.get("dangerous_attacks")),
        dangerous_attacks_last_10=to_int_or_none(last_10.get("dangerous_attacks")),
        corners_last_5=to_int_or_none(last_5.get("corners")),
        corners_last_10=to_int_or_none(last_10.get("corners")),
    )


def empty_metrics() -> SpreadRollingMetrics:
    return SpreadRollingMetrics(
        leader=TeamWindowStats(),
        underdog=TeamWindowStats(),
        match=MatchWindowStats(),
        trend=SpreadTrendMetrics(),
        source_fields_present=[],
        data_confidence_flag=False,
    )
