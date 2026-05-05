from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TotalSideType(str, Enum):
    UNDER = "under"
    OVER = "over"
    UNKNOWN = "unknown"


class UnderTimeBucket(str, Enum):
    MIN_70_74 = "70_74"
    MIN_75_85 = "75_85"
    MIN_86_88 = "86_88"
    OUTSIDE = "outside"


class ParsedTotalsMarket(BaseModel):
    valid: bool = False
    line: Optional[float] = None
    selected_side_type: TotalSideType = TotalSideType.UNKNOWN
    question: str = ""
    side: str = ""


class GoalTotalsUnderInput(BaseModel):
    event_id: str
    event_slug: str = ""
    event_title: str
    market_id: str
    market_slug: str = ""
    question: str
    side: str
    minute: Optional[float] = None
    score: str = ""
    home_team: str = ""
    away_team: str = ""
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    total_goals: Optional[int] = None
    total_line: Optional[float] = None
    goal_buffer: Optional[float] = None
    selected_side_type: TotalSideType = TotalSideType.UNKNOWN
    data_confidence_flag: bool = False
    red_card_flag: bool = False
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
    total_shots_both_last_10: Optional[int] = None
    total_dangerous_attacks_both_last_10: Optional[int] = None
    total_corners_both_last_10: Optional[int] = None
    goal_in_last_3min: bool = False
    goal_in_last_5min: bool = False
    red_card_in_last_10min: bool = False
    pressure_trend_last_10: str = "unknown"
    shots_trend_last_10: str = "unknown"
    dangerous_attacks_trend_last_10: str = "unknown"
    tempo_change_last_10: str = "unknown"
    time_since_last_goal: Optional[float] = None
    stable_for_2_snapshots: bool = False
    stable_for_3_snapshots: bool = False
    source_fields_present: list[str] = Field(default_factory=list)

    @property
    def time_bucket(self) -> UnderTimeBucket:
        return classify_under_time_bucket(self.minute)

    @property
    def within_activation_window(self) -> bool:
        return self.minute is not None and 70 <= self.minute < 89

    @property
    def is_under_side(self) -> bool:
        return self.selected_side_type == TotalSideType.UNDER

    @property
    def parsed_totals_valid(self) -> bool:
        return self.total_line is not None and self.selected_side_type != TotalSideType.UNKNOWN


def classify_under_time_bucket(minute: Optional[float]) -> UnderTimeBucket:
    if minute is None:
        return UnderTimeBucket.OUTSIDE
    if 70 <= minute < 75:
        return UnderTimeBucket.MIN_70_74
    if 75 <= minute <= 85:
        return UnderTimeBucket.MIN_75_85
    if 86 <= minute < 89:
        return UnderTimeBucket.MIN_86_88
    return UnderTimeBucket.OUTSIDE


def parse_totals_market(question: str, side: str) -> ParsedTotalsMarket:
    match = re.search(r"O/U\s*(\d+(?:\.\d+)?)", question or "", flags=re.IGNORECASE)
    if not match:
        return ParsedTotalsMarket(question=question or "", side=side or "")
    line = float(match.group(1))
    normalized_side = str(side or "").strip().lower()
    selected_side_type = TotalSideType.UNKNOWN
    if normalized_side == "under":
        selected_side_type = TotalSideType.UNDER
    elif normalized_side == "over":
        selected_side_type = TotalSideType.OVER
    return ParsedTotalsMarket(
        valid=True,
        line=line,
        selected_side_type=selected_side_type,
        question=question or "",
        side=side or "",
    )


def build_goal_totals_under_input(
    *,
    event_id: str,
    event_slug: str,
    event_title: str,
    market_id: str,
    market_slug: str,
    question: str,
    side: str,
    minute: Optional[float],
    score: str,
    home_team: str,
    away_team: str,
    data_confidence_flag: bool,
    red_card_flag: bool = False,
) -> GoalTotalsUnderInput:
    parsed = parse_totals_market(question, side)
    home_goals, away_goals = parse_score(score)
    total_goals = None
    goal_buffer = None
    if home_goals is not None and away_goals is not None:
        total_goals = home_goals + away_goals
        if parsed.line is not None:
            goal_buffer = round(parsed.line - total_goals, 6)
    return GoalTotalsUnderInput(
        event_id=event_id,
        event_slug=event_slug,
        event_title=event_title,
        market_id=market_id,
        market_slug=market_slug,
        question=question,
        side=side,
        minute=minute,
        score=score,
        home_team=home_team,
        away_team=away_team,
        home_goals=home_goals,
        away_goals=away_goals,
        total_goals=total_goals,
        total_line=parsed.line,
        goal_buffer=goal_buffer,
        selected_side_type=parsed.selected_side_type,
        data_confidence_flag=data_confidence_flag,
        red_card_flag=red_card_flag,
    )


def parse_score(value: str) -> tuple[Optional[int], Optional[int]]:
    match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", value or "")
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


@dataclass(frozen=True)
class GoalTotalsUnderActivationDecision:
    active: bool
    reason: str


@dataclass(frozen=True)
class GoalTotalsUnderEnterDecision:
    enter: bool
    reason: str


def goal_totals_under_activation_decision(data: GoalTotalsUnderInput) -> GoalTotalsUnderActivationDecision:
    if not data.within_activation_window:
        return GoalTotalsUnderActivationDecision(False, "goal_totals_under_minute_outside_window")
    if not data.parsed_totals_valid:
        return GoalTotalsUnderActivationDecision(False, "goal_totals_under_invalid_totals_market")
    if not data.is_under_side:
        return GoalTotalsUnderActivationDecision(False, "goal_totals_under_wrong_side")
    if not data.data_confidence_flag:
        return GoalTotalsUnderActivationDecision(False, "goal_totals_under_low_data_confidence")
    if data.red_card_flag or data.red_card_in_last_10min:
        return GoalTotalsUnderActivationDecision(False, "goal_totals_under_red_card")
    if data.goal_buffer is None:
        return GoalTotalsUnderActivationDecision(False, "goal_totals_under_missing_goal_buffer")
    if data.goal_buffer < 1.0:
        return GoalTotalsUnderActivationDecision(False, "goal_totals_under_buffer_too_small")
    return GoalTotalsUnderActivationDecision(True, f"goal_totals_under_activation_ok_{data.time_bucket.value}")


def goal_totals_under_enter_decision_v1(data: GoalTotalsUnderInput) -> GoalTotalsUnderEnterDecision:
    pre = goal_totals_under_enter_decision_pre_stability_v1(data)
    if not pre.enter:
        return pre
    if not (data.stable_for_2_snapshots or data.stable_for_3_snapshots):
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_not_stable")
    return GoalTotalsUnderEnterDecision(True, "goal_totals_under_enter")


def goal_totals_under_enter_decision_pre_stability_v1(data: GoalTotalsUnderInput) -> GoalTotalsUnderEnterDecision:
    activation = goal_totals_under_activation_decision(data)
    if not activation.active:
        return GoalTotalsUnderEnterDecision(False, activation.reason)

    if data.goal_in_last_3min or data.goal_in_last_5min:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_recent_goal")

    if str(data.pressure_trend_last_10).lower() == "up":
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_pressure")
    if str(data.shots_trend_last_10).lower() == "up":
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_pressure")
    if str(data.dangerous_attacks_trend_last_10).lower() == "up":
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_pressure")
    if str(data.tempo_change_last_10).lower() == "up":
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_chaos")

    strict_mode = data.goal_buffer is not None and data.goal_buffer < 2.0

    shots_limit = 2 if strict_mode else 3
    shots_on_target_limit = 0 if strict_mode else 1
    corners_limit = 1 if strict_mode else 2
    dangerous_limit = 5 if strict_mode else 8
    total_shots_limit = 3 if strict_mode else 5
    total_dangerous_limit = 8 if strict_mode else 12
    total_corners_limit = 2 if strict_mode else 3

    if (data.shots_last_10 or 0) > shots_limit:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_pressure")
    if (data.shots_on_target_last_10 or 0) > shots_on_target_limit:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_pressure")
    if (data.corners_last_10 or 0) > corners_limit:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_chaos")
    if (data.dangerous_attacks_last_10 or 0) > dangerous_limit:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_pressure")
    if (data.total_shots_both_last_10 or 0) > total_shots_limit:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_chaos")
    if (data.total_dangerous_attacks_both_last_10 or 0) > total_dangerous_limit:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_chaos")
    if (data.total_corners_both_last_10 or 0) > total_corners_limit:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_no_enter_chaos")

    return GoalTotalsUnderEnterDecision(True, "goal_totals_under_pre_stability_ok")


def goal_totals_under_enter_decision_score_only_v1(data: GoalTotalsUnderInput) -> GoalTotalsUnderEnterDecision:
    if not data.within_activation_window:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_v1_minute_outside_window")
    if not data.parsed_totals_valid:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_v1_invalid_totals_market")
    if not data.is_under_side:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_v1_wrong_side")
    if data.red_card_flag or data.red_card_in_last_10min:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_v1_red_card")
    if data.goal_buffer is None:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_v1_missing_goal_buffer")
    if data.goal_in_last_3min or data.goal_in_last_5min:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_v1_recent_goal")

    minimum_buffer = required_score_only_buffer(data.time_bucket)
    if minimum_buffer is None:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_v1_minute_outside_window")
    if data.goal_buffer < minimum_buffer:
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_v1_buffer_too_small")

    return GoalTotalsUnderEnterDecision(True, "goal_totals_under_v1_enter")


def goal_totals_under_enter_decision_score_only_v2(data: GoalTotalsUnderInput) -> GoalTotalsUnderEnterDecision:
    decision = goal_totals_under_enter_decision_score_only_v1(data)
    if not decision.enter:
        return decision
    if not (data.stable_for_2_snapshots or data.stable_for_3_snapshots):
        return GoalTotalsUnderEnterDecision(False, "goal_totals_under_v2_not_stable")
    return GoalTotalsUnderEnterDecision(True, "goal_totals_under_v2_enter")


def required_score_only_buffer(bucket: UnderTimeBucket) -> float | None:
    if bucket == UnderTimeBucket.MIN_70_74:
        return 2.0
    if bucket == UnderTimeBucket.MIN_75_85:
        return 1.0
    if bucket == UnderTimeBucket.MIN_86_88:
        return 1.0
    return None
