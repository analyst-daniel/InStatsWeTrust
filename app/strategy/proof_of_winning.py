from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TimeBucket(str, Enum):
    MIN_70_74 = "70_74"
    MIN_75_80 = "75_80"
    MIN_81_85 = "81_85"
    MIN_86_88 = "86_88"
    OUTSIDE = "outside"


class TrendState(str, Enum):
    DOWN = "down"
    STABLE = "stable"
    UP = "up"
    UNKNOWN = "unknown"


class ProofOfWinningInput(BaseModel):
    event_id: str
    event_slug: str = ""
    event_title: str
    market_id: str
    market_slug: str = ""
    question: str
    side: str
    minute: Optional[float] = None
    score: str = ""
    goal_difference: Optional[int] = None
    effective_goal_difference: Optional[float] = None
    leader_team: str = ""
    trailing_team: str = ""
    leader_red_card: bool = False
    trailing_red_card: bool = False
    data_confidence_flag: bool = False
    shots_last_5: Optional[int] = None
    shots_on_target_last_5: Optional[int] = None
    shots_last_10: Optional[int] = None
    shots_on_target_last_10: Optional[int] = None
    dangerous_attacks_last_5: Optional[int] = None
    dangerous_attacks_last_10: Optional[int] = None
    corners_last_5: Optional[int] = None
    corners_last_10: Optional[int] = None
    total_shots_both_last_10: Optional[int] = None
    total_dangerous_attacks_both_last_10: Optional[int] = None
    total_corners_both_last_10: Optional[int] = None
    goal_in_last_3min: bool = False
    goal_in_last_5min: bool = False
    red_card_in_last_10min: bool = False
    pressure_trend_last_10: TrendState = TrendState.UNKNOWN
    shots_trend_last_10: TrendState = TrendState.UNKNOWN
    dangerous_attacks_trend_last_10: TrendState = TrendState.UNKNOWN
    tempo_change_last_10: TrendState = TrendState.UNKNOWN
    stable_for_2_snapshots: bool = False
    stable_for_3_snapshots: bool = False
    source_fields_present: list[str] = Field(default_factory=list)

    @property
    def time_bucket(self) -> TimeBucket:
        return classify_time_bucket(self.minute)

    @property
    def within_analysis_window(self) -> bool:
        return self.minute is not None and 70 <= self.minute < 89

    @property
    def has_minimum_required_fields(self) -> bool:
        required = {
            "shots_last_5",
            "shots_last_10",
            "shots_on_target_last_10",
            "dangerous_attacks_last_10",
            "corners_last_10",
        }
        present = set(self.source_fields_present)
        return required.issubset(present)


def classify_time_bucket(minute: Optional[float]) -> TimeBucket:
    if minute is None:
        return TimeBucket.OUTSIDE
    if 70 <= minute < 75:
        return TimeBucket.MIN_70_74
    if 75 <= minute <= 80:
        return TimeBucket.MIN_75_80
    if 81 <= minute <= 85:
        return TimeBucket.MIN_81_85
    if 86 <= minute < 89:
        return TimeBucket.MIN_86_88
    return TimeBucket.OUTSIDE


@dataclass(frozen=True)
class ActivationDecision:
    active: bool
    reason: str


@dataclass(frozen=True)
class EnterDecision:
    enter: bool
    reason: str


def activation_decision(data: ProofOfWinningInput) -> ActivationDecision:
    if not data.within_analysis_window:
        return ActivationDecision(False, "proof_of_winning_minute_outside_window")
    if data.goal_difference is None or data.goal_difference < 2:
        return ActivationDecision(False, "proof_of_winning_goal_difference_too_low")
    if data.leader_red_card:
        return ActivationDecision(False, "proof_of_winning_leader_red_card")
    if not data.data_confidence_flag:
        return ActivationDecision(False, "proof_of_winning_low_data_confidence")
    if not data.has_minimum_required_fields:
        return ActivationDecision(False, "proof_of_winning_missing_required_fields")
    return ActivationDecision(True, "proof_of_winning_activation_ok")


def enter_decision_pre_stability_v1(data: ProofOfWinningInput) -> EnterDecision:
    activation = activation_decision(data)
    if not activation.active:
        return EnterDecision(False, activation.reason)

    if data.shots_last_10 is not None and data.shots_last_10 >= 4:
        return EnterDecision(False, "proof_of_winning_no_enter_pressure_shots_last_10")
    if data.shots_on_target_last_10 is not None and data.shots_on_target_last_10 >= 2:
        return EnterDecision(False, "proof_of_winning_no_enter_pressure_shots_on_target_last_10")
    if data.corners_last_10 is not None and data.corners_last_10 >= 3:
        return EnterDecision(False, "proof_of_winning_no_enter_pressure_corners_last_10")
    if data.dangerous_attacks_last_10 is not None and data.dangerous_attacks_last_10 >= 8:
        return EnterDecision(False, "proof_of_winning_no_enter_pressure_dangerous_attacks_last_10")

    if data.pressure_trend_last_10 == TrendState.UP:
        return EnterDecision(False, "proof_of_winning_no_enter_trend_pressure_up")
    if data.shots_trend_last_10 == TrendState.UP:
        return EnterDecision(False, "proof_of_winning_no_enter_trend_shots_up")
    if data.dangerous_attacks_trend_last_10 == TrendState.UP:
        return EnterDecision(False, "proof_of_winning_no_enter_trend_dangerous_attacks_up")

    if data.goal_in_last_3min:
        return EnterDecision(False, "proof_of_winning_no_enter_chaos_goal_last_3min")
    if data.red_card_in_last_10min:
        return EnterDecision(False, "proof_of_winning_no_enter_chaos_red_card_last_10min")
    if data.tempo_change_last_10 == TrendState.UP:
        return EnterDecision(False, "proof_of_winning_no_enter_chaos_tempo_up")

    return EnterDecision(True, "proof_of_winning_pre_stability_ok")


def enter_decision_v1(data: ProofOfWinningInput) -> EnterDecision:
    pre = enter_decision_pre_stability_v1(data)
    if not pre.enter:
        return pre

    if not (data.stable_for_2_snapshots or data.stable_for_3_snapshots):
        return EnterDecision(False, "proof_of_winning_no_enter_not_stable")

    return EnterDecision(True, "proof_of_winning_enter")
