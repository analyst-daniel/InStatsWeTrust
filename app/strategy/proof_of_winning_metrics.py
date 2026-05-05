from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel

from app.strategy.proof_of_winning import ProofOfWinningInput, TrendState


class TeamWindowStats(BaseModel):
    shots_last_5: Optional[int] = None
    shots_on_target_last_5: Optional[int] = None
    shots_last_10: Optional[int] = None
    shots_on_target_last_10: Optional[int] = None
    dangerous_attacks_last_5: Optional[int] = None
    dangerous_attacks_last_10: Optional[int] = None
    corners_last_5: Optional[int] = None
    corners_last_10: Optional[int] = None
    xg_last_10: Optional[float] = None
    shots_inside_box_last_10: Optional[int] = None
    blocked_shots_last_10: Optional[int] = None
    yellow_cards_last_10: Optional[int] = None
    possession: Optional[float] = None


class MatchWindowStats(BaseModel):
    total_shots_both_last_10: Optional[int] = None
    total_dangerous_attacks_both_last_10: Optional[int] = None
    total_corners_both_last_10: Optional[int] = None
    goal_in_last_3min: bool = False
    goal_in_last_5min: bool = False
    red_card_in_last_10min: bool = False
    time_since_last_goal: Optional[float] = None


class TrendMetrics(BaseModel):
    pressure_trend_last_10: TrendState = TrendState.UNKNOWN
    shots_trend_last_10: TrendState = TrendState.UNKNOWN
    dangerous_attacks_trend_last_10: TrendState = TrendState.UNKNOWN
    tempo_change_last_10: TrendState = TrendState.UNKNOWN


class RollingMetrics(BaseModel):
    trailing: TeamWindowStats
    match: MatchWindowStats
    trend: TrendMetrics
    source_fields_present: list[str]
    data_confidence_flag: bool


def build_rolling_metrics(detail_history: list[dict[str, Any]]) -> RollingMetrics:
    ordered = sorted(
        [row for row in detail_history if isinstance(row, dict)],
        key=lambda row: parse_dt(str(row.get("saved_at", ""))) or datetime.min.replace(tzinfo=timezone.utc),
    )
    if not ordered:
        return RollingMetrics(
            trailing=TeamWindowStats(),
            match=MatchWindowStats(),
            trend=TrendMetrics(),
            source_fields_present=[],
            data_confidence_flag=False,
        )

    current = ordered[-1]
    current_elapsed = fixture_elapsed_from_detail(current)
    if current_elapsed is None:
        return RollingMetrics(
            trailing=TeamWindowStats(),
            match=MatchWindowStats(),
            trend=TrendMetrics(),
            source_fields_present=[],
            data_confidence_flag=False,
        )

    teams = fixture_teams(current)
    score = fixture_score(current)
    trailing_team = trailing_team_name(teams, score)
    if not trailing_team:
        return RollingMetrics(
            trailing=TeamWindowStats(),
            match=MatchWindowStats(),
            trend=TrendMetrics(),
            source_fields_present=[],
            data_confidence_flag=False,
        )

    current_stats = statistics_map(current)
    trailing_now = current_stats.get(trailing_team, {})
    baseline_5 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 5)
    baseline_10 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 10)
    baseline_prev5 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 5)
    baseline_prev10 = nearest_snapshot_before_elapsed(ordered, current_elapsed - 10)

    trailing_5 = diff_team_stats(trailing_now, statistics_map(baseline_5).get(trailing_team, {})) if baseline_5 else {}
    trailing_10 = diff_team_stats(trailing_now, statistics_map(baseline_10).get(trailing_team, {})) if baseline_10 else {}

    total_10 = diff_match_totals(current_stats, statistics_map(baseline_10)) if baseline_10 else {}
    prev5_totals = None
    if baseline_prev5 and baseline_prev10:
        prev5_totals = diff_match_totals(statistics_map(baseline_prev5), statistics_map(baseline_prev10))

    prev5_trailing = None
    if baseline_prev5 and baseline_prev10:
        prev5_trailing = diff_team_stats(
            statistics_map(baseline_prev5).get(trailing_team, {}),
            statistics_map(baseline_prev10).get(trailing_team, {}),
        )

    event_flags = event_flags_for_current(current, current_elapsed)
    trend = TrendMetrics(
        pressure_trend_last_10=trend_from_values(
            pressure_value(trailing_5),
            pressure_value(prev5_trailing or {}),
        ),
        shots_trend_last_10=trend_from_values(
            trailing_5.get("shots"),
            (prev5_trailing or {}).get("shots"),
        ),
        dangerous_attacks_trend_last_10=trend_from_values(
            trailing_5.get("dangerous_attacks"),
            (prev5_trailing or {}).get("dangerous_attacks"),
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

    fields_present: list[str] = []
    trailing_stats = TeamWindowStats(
        shots_last_5=to_int_or_none(trailing_5.get("shots")),
        shots_on_target_last_5=to_int_or_none(trailing_5.get("shots_on_target")),
        shots_last_10=to_int_or_none(trailing_10.get("shots")),
        shots_on_target_last_10=to_int_or_none(trailing_10.get("shots_on_target")),
        dangerous_attacks_last_5=to_int_or_none(trailing_5.get("dangerous_attacks")),
        dangerous_attacks_last_10=to_int_or_none(trailing_10.get("dangerous_attacks")),
        corners_last_5=to_int_or_none(trailing_5.get("corners")),
        corners_last_10=to_int_or_none(trailing_10.get("corners")),
        xg_last_10=to_float_or_none(trailing_10.get("xg")),
        shots_inside_box_last_10=to_int_or_none(trailing_10.get("shots_inside_box")),
        blocked_shots_last_10=to_int_or_none(trailing_10.get("blocked_shots")),
        yellow_cards_last_10=to_int_or_none(trailing_10.get("yellow_cards")),
        possession=to_float_or_none(trailing_now.get("possession")),
    )
    for field in (
        "shots_last_5",
        "shots_last_10",
        "shots_on_target_last_10",
        "corners_last_10",
        "xg_last_10",
        "shots_inside_box_last_10",
        "blocked_shots_last_10",
        "yellow_cards_last_10",
        "possession",
    ):
        if getattr(trailing_stats, field) is not None:
            fields_present.append(field)

    required_fields = {"shots_last_5", "shots_last_10", "shots_on_target_last_10", "corners_last_10"}
    return RollingMetrics(
        trailing=trailing_stats,
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
        data_confidence_flag=required_fields.issubset(set(fields_present)),
    )


def populate_input_with_metrics(base: ProofOfWinningInput, metrics: RollingMetrics) -> ProofOfWinningInput:
    return base.model_copy(
        update={
            "shots_last_5": metrics.trailing.shots_last_5,
            "shots_on_target_last_5": metrics.trailing.shots_on_target_last_5,
            "shots_last_10": metrics.trailing.shots_last_10,
            "shots_on_target_last_10": metrics.trailing.shots_on_target_last_10,
            "dangerous_attacks_last_5": metrics.trailing.dangerous_attacks_last_5,
            "dangerous_attacks_last_10": metrics.trailing.dangerous_attacks_last_10,
            "corners_last_5": metrics.trailing.corners_last_5,
            "corners_last_10": metrics.trailing.corners_last_10,
            "xg_last_10": metrics.trailing.xg_last_10,
            "shots_inside_box_last_10": metrics.trailing.shots_inside_box_last_10,
            "blocked_shots_last_10": metrics.trailing.blocked_shots_last_10,
            "yellow_cards_last_10": metrics.trailing.yellow_cards_last_10,
            "trailing_possession": metrics.trailing.possession,
            "total_shots_both_last_10": metrics.match.total_shots_both_last_10,
            "total_dangerous_attacks_both_last_10": metrics.match.total_dangerous_attacks_both_last_10,
            "total_corners_both_last_10": metrics.match.total_corners_both_last_10,
            "goal_in_last_3min": metrics.match.goal_in_last_3min,
            "goal_in_last_5min": metrics.match.goal_in_last_5min,
            "red_card_in_last_10min": metrics.match.red_card_in_last_10min,
            "time_since_last_goal": metrics.match.time_since_last_goal,
            "pressure_trend_last_10": metrics.trend.pressure_trend_last_10,
            "shots_trend_last_10": metrics.trend.shots_trend_last_10,
            "dangerous_attacks_trend_last_10": metrics.trend.dangerous_attacks_trend_last_10,
            "tempo_change_last_10": metrics.trend.tempo_change_last_10,
            "source_fields_present": metrics.source_fields_present,
            "data_confidence_flag": metrics.data_confidence_flag,
        }
    )


def fixture_elapsed_from_detail(detail: dict[str, Any]) -> Optional[float]:
    fixture = detail.get("fixture") if isinstance(detail.get("fixture"), dict) else {}
    fixture_row = fixture.get("fixture") if isinstance(fixture.get("fixture"), dict) else fixture
    status = fixture_row.get("status") if isinstance(fixture_row.get("status"), dict) else {}
    value = status.get("elapsed")
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fixture_teams(detail: dict[str, Any]) -> tuple[str, str]:
    fixture = detail.get("fixture") if isinstance(detail.get("fixture"), dict) else {}
    teams = fixture.get("teams") if isinstance(fixture.get("teams"), dict) else {}
    home = ((teams.get("home") or {}).get("name") if isinstance(teams.get("home"), dict) else "") or ""
    away = ((teams.get("away") or {}).get("name") if isinstance(teams.get("away"), dict) else "") or ""
    return home, away


def fixture_score(detail: dict[str, Any]) -> tuple[int, int]:
    fixture = detail.get("fixture") if isinstance(detail.get("fixture"), dict) else {}
    goals = fixture.get("goals") if isinstance(fixture.get("goals"), dict) else {}
    return parse_int(goals.get("home")) or 0, parse_int(goals.get("away")) or 0


def trailing_team_name(teams: tuple[str, str], score: tuple[int, int]) -> str:
    home, away = teams
    home_goals, away_goals = score
    if home_goals > away_goals:
        return away
    if away_goals > home_goals:
        return home
    return ""


def statistics_map(detail: Optional[dict[str, Any]]) -> dict[str, dict[str, float]]:
    if not detail:
        return {}
    rows = detail.get("statistics")
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        team = row.get("team") if isinstance(row.get("team"), dict) else {}
        team_name = str(team.get("name") or "")
        stats = row.get("statistics") if isinstance(row.get("statistics"), list) else []
        metric_map: dict[str, float] = {}
        for item in stats:
            if not isinstance(item, dict):
                continue
            stat_type = normalize_stat_type(str(item.get("type") or ""))
            if not stat_type:
                continue
            value = parse_number(item.get("value"))
            if value is None:
                continue
            metric_map[stat_type] = value
        if team_name:
            out[team_name] = metric_map
    return out


def normalize_stat_type(value: str) -> str:
    key = value.strip().lower()
    mapping = {
        "total shots": "shots",
        "shots on goal": "shots_on_target",
        "shots off goal": "shots_off_target",
        "corner kicks": "corners",
        "dangerous attacks": "dangerous_attacks",
        "attacks": "attacks",
        "expected_goals": "xg",
        "expected goals": "xg",
        "shots insidebox": "shots_inside_box",
        "shots inside box": "shots_inside_box",
        "blocked shots": "blocked_shots",
        "yellow cards": "yellow_cards",
        "ball possession": "possession",
        "red cards": "red_cards",
    }
    return mapping.get(key, "")


def diff_team_stats(current: dict[str, int], baseline: dict[str, int]) -> dict[str, int | float]:
    keys = {"shots", "shots_on_target", "dangerous_attacks", "corners", "xg", "shots_inside_box", "blocked_shots", "yellow_cards"}
    out: dict[str, int | float] = {}
    for key in keys:
        if key not in current:
            continue
        out[key] = max(current.get(key, 0) - baseline.get(key, 0), 0)
    return out


def diff_match_totals(current: dict[str, dict[str, float]], baseline: dict[str, dict[str, float]]) -> dict[str, float]:
    return {
        "shots": max(sum(team.get("shots", 0) for team in current.values()) - sum(team.get("shots", 0) for team in baseline.values()), 0),
        "dangerous_attacks": max(
            sum(team.get("dangerous_attacks", 0) for team in current.values()) - sum(team.get("dangerous_attacks", 0) for team in baseline.values()),
            0,
        ),
        "corners": max(sum(team.get("corners", 0) for team in current.values()) - sum(team.get("corners", 0) for team in baseline.values()), 0),
    }


def total_from_current_minus(current: dict[str, dict[str, int]], baseline_detail: Optional[dict[str, Any]], field: str) -> Optional[int]:
    if baseline_detail is None:
        return None
    baseline = statistics_map(baseline_detail)
    return diff_match_totals(current, baseline).get(field)


def nearest_snapshot_before_elapsed(details: list[dict[str, Any]], target_elapsed: float) -> Optional[dict[str, Any]]:
    eligible: list[tuple[float, dict[str, Any]]] = []
    for row in details:
        elapsed = fixture_elapsed_from_detail(row)
        if elapsed is None:
            continue
        if elapsed <= target_elapsed:
            eligible.append((elapsed, row))
    if not eligible:
        return None
    eligible.sort(key=lambda item: item[0])
    return eligible[-1][1]


def event_flags_for_current(detail: dict[str, Any], current_elapsed: float) -> dict[str, Any]:
    events = detail.get("events") if isinstance(detail.get("events"), list) else []
    goal_minutes: list[float] = []
    red_minutes: list[float] = []
    for row in events:
        minute = event_minute(row)
        if minute is None:
            continue
        if is_goal_event(row):
            goal_minutes.append(minute)
        if is_red_card_event(row):
            red_minutes.append(minute)
    last_goal = max(goal_minutes) if goal_minutes else None
    return {
        "goal_in_last_3min": any(current_elapsed - minute <= 3 for minute in goal_minutes),
        "goal_in_last_5min": any(current_elapsed - minute <= 5 for minute in goal_minutes),
        "red_card_in_last_10min": any(current_elapsed - minute <= 10 for minute in red_minutes),
        "time_since_last_goal": round(current_elapsed - last_goal, 1) if last_goal is not None else None,
    }


def event_minute(row: dict[str, Any]) -> Optional[float]:
    time_row = row.get("time") if isinstance(row.get("time"), dict) else {}
    elapsed = parse_int(time_row.get("elapsed"))
    extra = parse_int(time_row.get("extra")) or 0
    if elapsed is None:
        return None
    return float(elapsed + extra)


def is_goal_event(row: dict[str, Any]) -> bool:
    event_type = str(row.get("type") or "").lower()
    detail = str(row.get("detail") or "").lower()
    return "goal" in event_type or "goal" in detail


def is_red_card_event(row: dict[str, Any]) -> bool:
    event_type = str(row.get("type") or "").lower()
    detail = str(row.get("detail") or "").lower()
    return "red card" in event_type or "red card" in detail


def trend_from_values(current: Optional[int], previous: Optional[int]) -> TrendState:
    if current is None or previous is None:
        return TrendState.UNKNOWN
    if current > previous:
        return TrendState.UP
    if current < previous:
        return TrendState.DOWN
    return TrendState.STABLE


def pressure_value(stats: dict[str, Any]) -> Optional[int]:
    if not stats:
        return None
    shots_on = parse_int(stats.get("shots_on_target")) or 0
    shots = parse_int(stats.get("shots")) or 0
    dangerous = parse_int(stats.get("dangerous_attacks")) or 0
    corners = parse_int(stats.get("corners")) or 0
    return int((shots_on * 10) + (shots * 4) + dangerous + (corners * 2))


def tempo_value(stats: dict[str, Any]) -> Optional[int]:
    if not stats:
        return None
    shots = parse_int(stats.get("shots")) or 0
    dangerous = parse_int(stats.get("dangerous_attacks")) or 0
    corners = parse_int(stats.get("corners")) or 0
    return shots + dangerous + corners


def parse_number(value: Any) -> Optional[float]:
    try:
        if value in ("", None):
            return None
        if isinstance(value, str) and "%" in value:
            value = value.replace("%", "")
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: Any) -> Optional[int]:
    parsed = parse_number(value)
    return int(parsed) if parsed is not None else None


def to_float_or_none(value: Any) -> Optional[float]:
    try:
        if value in ("", None):
            return None
        if isinstance(value, str) and "%" in value:
            value = value.replace("%", "")
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def to_int_or_none(value: Any) -> Optional[int]:
    return parse_int(value)
