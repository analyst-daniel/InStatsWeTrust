from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from app.strategy.proof_of_winning import ProofOfWinningInput


class GoalEvent(BaseModel):
    minute: float
    team: str
    detail: str = ""
    is_penalty: bool = False


class EffectiveGoalDifferenceResult(BaseModel):
    effective_goal_difference: Optional[float] = None
    leader_weight_sum: float = 0.0
    trailing_weight_sum: float = 0.0
    goal_events_used: int = 0
    data_confidence_flag: bool = False


def effective_goal_difference_from_detail(detail_payload: dict[str, Any]) -> EffectiveGoalDifferenceResult:
    score = fixture_score(detail_payload)
    teams = fixture_teams(detail_payload)
    leader_team, trailing_team = leader_and_trailing_team(teams, score)
    if not leader_team or not trailing_team:
        return EffectiveGoalDifferenceResult()
    events = extract_goal_events(detail_payload, teams)
    if not events:
        return EffectiveGoalDifferenceResult()
    leader_events = [event for event in events if normalize_team(event.team) == normalize_team(leader_team)]
    trailing_events = [event for event in events if normalize_team(event.team) == normalize_team(trailing_team)]
    if not leader_events and not trailing_events:
        return EffectiveGoalDifferenceResult()

    leader_weight_sum = weighted_goal_sum(leader_events)
    trailing_weight_sum = weighted_goal_sum(trailing_events)
    return EffectiveGoalDifferenceResult(
        effective_goal_difference=round(leader_weight_sum - trailing_weight_sum, 4),
        leader_weight_sum=round(leader_weight_sum, 4),
        trailing_weight_sum=round(trailing_weight_sum, 4),
        goal_events_used=len(leader_events) + len(trailing_events),
        data_confidence_flag=True,
    )


def populate_input_with_effective_goal_difference(
    base: ProofOfWinningInput, result: EffectiveGoalDifferenceResult
) -> ProofOfWinningInput:
    return base.model_copy(update={"effective_goal_difference": result.effective_goal_difference})


def weighted_goal_sum(events: list[GoalEvent]) -> float:
    ordered = sorted(events, key=lambda item: item.minute)
    total = 0.0
    previous_minute: Optional[float] = None
    for index, event in enumerate(ordered):
        weight = minute_weight(event.minute)
        weight *= penalty_weight(event.is_penalty)
        if previous_minute is not None and (event.minute - previous_minute) <= 5:
            if event.minute < 30:
                weight *= 0.6
            elif event.minute >= 75:
                weight *= 1.05
        total += weight
        previous_minute = event.minute
    return total


def minute_weight(minute: float) -> float:
    if minute <= 30:
        return 0.8
    if minute < 75:
        return 1.0
    return 1.15


def penalty_weight(is_penalty: bool) -> float:
    return 0.7 if is_penalty else 1.0


def extract_goal_events(detail_payload: dict[str, Any], teams: tuple[str, str]) -> list[GoalEvent]:
    rows = detail_payload.get("events") if isinstance(detail_payload.get("events"), list) else []
    home, away = teams
    out: list[GoalEvent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not is_goal_event(row):
            continue
        minute = event_minute(row)
        if minute is None:
            continue
        team_name = event_team_name(row, home, away)
        if not team_name:
            continue
        detail = str(row.get("detail") or "")
        out.append(
            GoalEvent(
                minute=minute,
                team=team_name,
                detail=detail,
                is_penalty=is_penalty_goal(row),
            )
        )
    return out


def fixture_teams(detail_payload: dict[str, Any]) -> tuple[str, str]:
    fixture = detail_payload.get("fixture") if isinstance(detail_payload.get("fixture"), dict) else {}
    teams = fixture.get("teams") if isinstance(fixture.get("teams"), dict) else {}
    home = ((teams.get("home") or {}).get("name") if isinstance(teams.get("home"), dict) else "") or ""
    away = ((teams.get("away") or {}).get("name") if isinstance(teams.get("away"), dict) else "") or ""
    return home, away


def fixture_score(detail_payload: dict[str, Any]) -> tuple[int, int]:
    fixture = detail_payload.get("fixture") if isinstance(detail_payload.get("fixture"), dict) else {}
    goals = fixture.get("goals") if isinstance(fixture.get("goals"), dict) else {}
    return parse_int(goals.get("home")) or 0, parse_int(goals.get("away")) or 0


def leader_and_trailing_team(teams: tuple[str, str], score: tuple[int, int]) -> tuple[str, str]:
    home, away = teams
    home_goals, away_goals = score
    if home_goals > away_goals:
        return home, away
    if away_goals > home_goals:
        return away, home
    return "", ""


def event_team_name(row: dict[str, Any], home: str, away: str) -> str:
    team = row.get("team") if isinstance(row.get("team"), dict) else {}
    team_name = str(team.get("name") or "")
    if team_name:
        return team_name
    comments = str(row.get("comments") or "")
    if comments and normalize_team(home) in normalize_team(comments):
        return home
    if comments and normalize_team(away) in normalize_team(comments):
        return away
    return ""


def is_goal_event(row: dict[str, Any]) -> bool:
    event_type = str(row.get("type") or "").lower()
    detail = str(row.get("detail") or "").lower()
    return "goal" in event_type or "goal" in detail


def is_penalty_goal(row: dict[str, Any]) -> bool:
    detail = str(row.get("detail") or "").lower()
    comments = str(row.get("comments") or "").lower()
    return "penalty" in detail or "penalty" in comments


def event_minute(row: dict[str, Any]) -> Optional[float]:
    time_row = row.get("time") if isinstance(row.get("time"), dict) else {}
    elapsed = parse_int(time_row.get("elapsed"))
    extra = parse_int(time_row.get("extra")) or 0
    if elapsed is None:
        return None
    return float(elapsed + extra)


def normalize_team(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "", value.lower())


def parse_int(value: Any) -> Optional[int]:
    try:
        if value in ("", None):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None
