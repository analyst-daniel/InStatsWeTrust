from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SpreadSideType(str, Enum):
    PLUS = "plus"
    MINUS = "minus"
    UNKNOWN = "unknown"


class SpreadTimeBucket(str, Enum):
    MIN_75_80 = "75_80"
    MIN_81_85 = "81_85"
    MIN_86_88 = "86_88"
    OUTSIDE = "outside"


class ParsedSpreadMarket(BaseModel):
    valid: bool = False
    listed_team: str = ""
    line: Optional[float] = None
    side_type: SpreadSideType = SpreadSideType.UNKNOWN
    question: str = ""
    side: str = ""
    selected_team: str = ""
    selected_line: Optional[float] = None
    selected_side_type: SpreadSideType = SpreadSideType.UNKNOWN


class SpreadConfirmationInput(BaseModel):
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
    goal_difference: Optional[int] = None
    leader_team: str = ""
    trailing_team: str = ""
    spread_team: str = ""
    spread_line: Optional[float] = None
    spread_side_type: SpreadSideType = SpreadSideType.UNKNOWN
    selected_team: str = ""
    selected_line: Optional[float] = None
    selected_side_type: SpreadSideType = SpreadSideType.UNKNOWN
    data_confidence_flag: bool = False
    leader_red_card: bool = False
    trailing_red_card: bool = False
    leader_shots_last_5: Optional[int] = None
    leader_shots_on_target_last_5: Optional[int] = None
    leader_shots_last_10: Optional[int] = None
    leader_shots_on_target_last_10: Optional[int] = None
    leader_dangerous_attacks_last_5: Optional[int] = None
    leader_dangerous_attacks_last_10: Optional[int] = None
    leader_corners_last_5: Optional[int] = None
    leader_corners_last_10: Optional[int] = None
    underdog_shots_last_5: Optional[int] = None
    underdog_shots_on_target_last_5: Optional[int] = None
    underdog_shots_last_10: Optional[int] = None
    underdog_shots_on_target_last_10: Optional[int] = None
    underdog_dangerous_attacks_last_5: Optional[int] = None
    underdog_dangerous_attacks_last_10: Optional[int] = None
    underdog_corners_last_5: Optional[int] = None
    underdog_corners_last_10: Optional[int] = None
    total_shots_both_last_10: Optional[int] = None
    total_dangerous_attacks_both_last_10: Optional[int] = None
    total_corners_both_last_10: Optional[int] = None
    goal_in_last_3min: bool = False
    goal_in_last_5min: bool = False
    red_card_in_last_10min: bool = False
    leader_pressure_trend_last_10: str = "unknown"
    underdog_pressure_trend_last_10: str = "unknown"
    shots_trend_last_10: str = "unknown"
    dangerous_attacks_trend_last_10: str = "unknown"
    tempo_change_last_10: str = "unknown"
    time_since_last_goal: Optional[float] = None
    stable_for_2_snapshots: bool = False
    stable_for_3_snapshots: bool = False
    source_fields_present: list[str] = Field(default_factory=list)

    @property
    def time_bucket(self) -> SpreadTimeBucket:
        return classify_time_bucket(self.minute)

    @property
    def within_analysis_window(self) -> bool:
        return self.minute is not None and 75 <= self.minute < 89

    @property
    def parsed_spread_valid(self) -> bool:
        return self.spread_line is not None and self.spread_side_type != SpreadSideType.UNKNOWN and bool(self.spread_team)


def classify_time_bucket(minute: Optional[float]) -> SpreadTimeBucket:
    if minute is None:
        return SpreadTimeBucket.OUTSIDE
    if 75 <= minute <= 80:
        return SpreadTimeBucket.MIN_75_80
    if 81 <= minute <= 85:
        return SpreadTimeBucket.MIN_81_85
    if 86 <= minute < 89:
        return SpreadTimeBucket.MIN_86_88
    return SpreadTimeBucket.OUTSIDE


def parse_spread_market(question: str, side: str) -> ParsedSpreadMarket:
    match = re.search(r"Spread:\s*(.+?)\s*\(([+-]?\d+(?:\.\d+)?)\)", question or "", flags=re.IGNORECASE)
    if not match:
        return ParsedSpreadMarket(question=question or "", side=side or "")

    listed_team = match.group(1).strip()
    line = float(match.group(2))
    listed_side_type = SpreadSideType.MINUS if line < 0 else SpreadSideType.PLUS
    selected_team = (side or "").strip()

    if normalize_name(selected_team) == normalize_name(listed_team):
        selected_line = line
    else:
        selected_line = -line

    selected_side_type = SpreadSideType.UNKNOWN
    if selected_line is not None:
        if selected_line < 0:
            selected_side_type = SpreadSideType.MINUS
        elif selected_line > 0:
            selected_side_type = SpreadSideType.PLUS

    return ParsedSpreadMarket(
        valid=True,
        listed_team=listed_team,
        line=line,
        side_type=listed_side_type,
        question=question or "",
        side=side or "",
        selected_team=selected_team,
        selected_line=selected_line,
        selected_side_type=selected_side_type,
    )


def build_spread_input(
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
    leader_red_card: bool = False,
    trailing_red_card: bool = False,
) -> SpreadConfirmationInput:
    parsed = parse_spread_market(question, side)
    home_goals, away_goals = parse_score(score)
    leader_team = ""
    trailing_team = ""
    goal_difference = None
    if home_goals is not None and away_goals is not None:
        goal_difference = abs(home_goals - away_goals)
        if home_goals > away_goals:
            leader_team = home_team
            trailing_team = away_team
        elif away_goals > home_goals:
            leader_team = away_team
            trailing_team = home_team
    return SpreadConfirmationInput(
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
        goal_difference=goal_difference,
        leader_team=leader_team,
        trailing_team=trailing_team,
        spread_team=parsed.listed_team,
        spread_line=parsed.line,
        spread_side_type=parsed.side_type,
        selected_team=parsed.selected_team,
        selected_line=parsed.selected_line,
        selected_side_type=parsed.selected_side_type,
        data_confidence_flag=data_confidence_flag,
        leader_red_card=leader_red_card,
        trailing_red_card=trailing_red_card,
    )


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def parse_score(value: str) -> tuple[Optional[int], Optional[int]]:
    match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", value or "")
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


@dataclass(frozen=True)
class SpreadActivationDecision:
    active: bool
    reason: str


@dataclass(frozen=True)
class SpreadEnterDecision:
    enter: bool
    reason: str


def spread_plus_activation_decision(data: SpreadConfirmationInput) -> SpreadActivationDecision:
    if not data.within_analysis_window:
        return SpreadActivationDecision(False, "spread_plus_minute_outside_window")
    if not data.data_confidence_flag:
        return SpreadActivationDecision(False, "spread_plus_low_data_confidence")
    if not data.parsed_spread_valid:
        return SpreadActivationDecision(False, "spread_plus_invalid_spread_market")
    if data.selected_side_type != SpreadSideType.PLUS:
        return SpreadActivationDecision(False, "spread_plus_wrong_side_type")
    if data.selected_line not in {1.5, 2.5, 3.5, 4.5}:
        return SpreadActivationDecision(False, "spread_plus_unsupported_line")
    if selected_team_has_red_card(data):
        return SpreadActivationDecision(False, "spread_plus_selected_team_red_card")
    if selected_team_margin(data) is None:
        return SpreadActivationDecision(False, "spread_plus_missing_score_context")
    if not selected_team_within_plus_range(data):
        return SpreadActivationDecision(False, "spread_plus_score_outside_handicap_range")
    return SpreadActivationDecision(True, "spread_plus_activation_ok")


def spread_plus_enter_decision_v1(data: SpreadConfirmationInput) -> SpreadEnterDecision:
    pre = spread_plus_enter_decision_pre_stability_v1(data)
    if not pre.enter:
        return pre
    if not (data.stable_for_2_snapshots or data.stable_for_3_snapshots):
        return SpreadEnterDecision(False, "spread_plus_no_enter_not_stable")
    return SpreadEnterDecision(True, "spread_plus_enter")


def spread_plus_enter_decision_pre_stability_v1(data: SpreadConfirmationInput) -> SpreadEnterDecision:
    activation = spread_plus_activation_decision(data)
    if not activation.active:
        return SpreadEnterDecision(False, activation.reason)

    if not underdog_has_life(data):
        return SpreadEnterDecision(False, "spread_plus_no_enter_underdog_not_alive")
    if leader_is_dominating_too_much(data):
        return SpreadEnterDecision(False, "spread_plus_no_enter_favorite_dominating")
    if data.goal_in_last_3min:
        return SpreadEnterDecision(False, "spread_plus_no_enter_chaos_goal_last_3min")
    if data.red_card_in_last_10min:
        return SpreadEnterDecision(False, "spread_plus_no_enter_chaos_red_card_last_10min")
    if str(data.tempo_change_last_10).lower() == "up":
        return SpreadEnterDecision(False, "spread_plus_no_enter_chaos_tempo_up")
    return SpreadEnterDecision(True, "spread_plus_pre_stability_ok")


def selected_team_has_red_card(data: SpreadConfirmationInput) -> bool:
    if normalize_name(data.selected_team) == normalize_name(data.leader_team):
        return data.leader_red_card
    if normalize_name(data.selected_team) == normalize_name(data.trailing_team):
        return data.trailing_red_card
    return False


def selected_team_margin(data: SpreadConfirmationInput) -> Optional[int]:
    if data.home_goals is None or data.away_goals is None:
        return None
    if normalize_name(data.selected_team) == normalize_name(data.home_team):
        return data.home_goals - data.away_goals
    if normalize_name(data.selected_team) == normalize_name(data.away_team):
        return data.away_goals - data.home_goals
    return None


def selected_team_within_plus_range(data: SpreadConfirmationInput) -> bool:
    margin = selected_team_margin(data)
    if margin is None or data.selected_line is None or data.selected_line <= 0:
        return False
    return margin >= -int(data.selected_line)


def underdog_has_life(data: SpreadConfirmationInput) -> bool:
    shots = data.underdog_shots_last_10 or 0
    shots_on = data.underdog_shots_on_target_last_10 or 0
    dangerous = data.underdog_dangerous_attacks_last_10 or 0
    corners = data.underdog_corners_last_10 or 0
    return shots >= 1 or shots_on >= 1 or dangerous >= 2 or corners >= 1


def leader_is_dominating_too_much(data: SpreadConfirmationInput) -> bool:
    if (data.leader_shots_on_target_last_10 or 0) >= 2:
        return True
    if (data.leader_shots_last_10 or 0) >= 5:
        return True
    if (data.leader_corners_last_10 or 0) >= 3:
        return True
    if (data.leader_dangerous_attacks_last_10 or 0) >= 8:
        return True
    if str(data.leader_pressure_trend_last_10).lower() == "up":
        return True
    return False


def spread_minus_activation_decision(data: SpreadConfirmationInput) -> SpreadActivationDecision:
    if not data.within_analysis_window:
        return SpreadActivationDecision(False, "spread_minus_minute_outside_window")
    if not data.data_confidence_flag:
        return SpreadActivationDecision(False, "spread_minus_low_data_confidence")
    if not data.parsed_spread_valid:
        return SpreadActivationDecision(False, "spread_minus_invalid_spread_market")
    if data.selected_side_type != SpreadSideType.MINUS:
        return SpreadActivationDecision(False, "spread_minus_wrong_side_type")
    if data.selected_line not in {-1.5, -2.5, -3.5, -4.5}:
        return SpreadActivationDecision(False, "spread_minus_unsupported_line")
    if selected_team_has_red_card(data):
        return SpreadActivationDecision(False, "spread_minus_selected_team_red_card")
    margin = selected_team_margin(data)
    if margin is None:
        return SpreadActivationDecision(False, "spread_minus_missing_score_context")
    required_margin = required_margin_for_minus_line(data.selected_line)
    if required_margin is None:
        return SpreadActivationDecision(False, "spread_minus_unsupported_line")
    if margin < required_margin:
        return SpreadActivationDecision(False, "spread_minus_margin_too_small")
    return SpreadActivationDecision(True, "spread_minus_activation_ok")


def spread_minus_enter_decision_v1(data: SpreadConfirmationInput) -> SpreadEnterDecision:
    pre = spread_minus_enter_decision_pre_stability_v1(data)
    if not pre.enter:
        return pre
    if not (data.stable_for_2_snapshots or data.stable_for_3_snapshots):
        return SpreadEnterDecision(False, "spread_minus_no_enter_not_stable")
    return SpreadEnterDecision(True, "spread_minus_enter")


def spread_minus_enter_decision_pre_stability_v1(data: SpreadConfirmationInput) -> SpreadEnterDecision:
    activation = spread_minus_activation_decision(data)
    if not activation.active:
        return SpreadEnterDecision(False, activation.reason)

    if leader_not_in_control(data):
        return SpreadEnterDecision(False, "spread_minus_no_enter_leader_not_in_control")
    if underdog_is_pressing_too_much(data):
        return SpreadEnterDecision(False, "spread_minus_no_enter_pressure")
    if data.goal_in_last_3min:
        return SpreadEnterDecision(False, "spread_minus_no_enter_chaos_goal_last_3min")
    if data.red_card_in_last_10min:
        return SpreadEnterDecision(False, "spread_minus_no_enter_chaos_red_card_last_10min")
    if str(data.tempo_change_last_10).lower() == "up":
        return SpreadEnterDecision(False, "spread_minus_no_enter_chaos_tempo_up")
    return SpreadEnterDecision(True, "spread_minus_pre_stability_ok")


def required_margin_for_minus_line(line: Optional[float]) -> Optional[int]:
    if line == -1.5:
        return 2
    if line == -2.5:
        return 3
    if line == -3.5:
        return 4
    if line == -4.5:
        return 5
    return None


def leader_not_in_control(data: SpreadConfirmationInput) -> bool:
    leader_shots = data.leader_shots_last_10 or 0
    leader_on = data.leader_shots_on_target_last_10 or 0
    leader_dangerous = data.leader_dangerous_attacks_last_10 or 0
    leader_corners = data.leader_corners_last_10 or 0
    return not (leader_shots >= 1 or leader_on >= 1 or leader_dangerous >= 2 or leader_corners >= 1)


def underdog_is_pressing_too_much(data: SpreadConfirmationInput) -> bool:
    if (data.underdog_shots_on_target_last_10 or 0) >= 2:
        return True
    if (data.underdog_shots_last_10 or 0) >= 4:
        return True
    if (data.underdog_corners_last_10 or 0) >= 3:
        return True
    if (data.underdog_dangerous_attacks_last_10 or 0) >= 8:
        return True
    if str(data.underdog_pressure_trend_last_10).lower() == "up":
        return True
    return False
