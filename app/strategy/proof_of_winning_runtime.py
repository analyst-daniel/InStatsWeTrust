from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.live_state.football_research import FootballResearchStore
from app.normalize.models import LiveState, MarketObservation, NormalizedMarket
from app.normalize.normalizer import market_type
from app.strategy.proof_of_winning import (
    ProofOfWinningInput,
    enter_decision_pre_stability_v1,
    enter_decision_v1,
)
from app.strategy.proof_of_winning_effective_lead import effective_goal_difference_from_detail, populate_input_with_effective_goal_difference
from app.strategy.proof_of_winning_metrics import build_rolling_metrics, populate_input_with_metrics


@dataclass(frozen=True)
class ProofOfWinningEvaluation:
    applies: bool
    enter: bool
    reason: str
    payload: Optional[ProofOfWinningInput] = None


class ProofOfWinningRuntime:
    def __init__(self, settings: dict, research_store: FootballResearchStore) -> None:
        self.enabled = bool(settings.get("proof_of_winning", {}).get("enabled", True))
        self.research_store = research_store
        self.history_limit = int(settings.get("proof_of_winning", {}).get("history_limit", 16))

    def evaluate(self, market: NormalizedMarket, observation: MarketObservation, live_state: LiveState | None) -> ProofOfWinningEvaluation:
        if not self.enabled:
            return ProofOfWinningEvaluation(False, False, observation.reason, None)
        if live_state is None:
            return ProofOfWinningEvaluation(False, False, observation.reason, None)
        context = market_context(market, observation, live_state)
        if context is None:
            return ProofOfWinningEvaluation(False, False, observation.reason, None)
        fixture_id = fixture_id_from_live_state(live_state)
        if not fixture_id:
            return ProofOfWinningEvaluation(True, False, "proof_of_winning_missing_fixture_id", None)
        history = self.research_store.load_recent_fixture_details(fixture_id, limit=self.history_limit)
        if not history:
            return ProofOfWinningEvaluation(True, False, "proof_of_winning_missing_detail_history", None)
        latest = history[-1]
        base = build_base_input(market, observation, latest, context["leader_team"], context["trailing_team"])
        metrics = build_rolling_metrics(history)
        hydrated = populate_input_with_metrics(base, metrics)
        effective = effective_goal_difference_from_detail(latest)
        hydrated = populate_input_with_effective_goal_difference(hydrated, effective)
        hydrated = hydrated.model_copy(
            update={
                "stable_for_2_snapshots": consecutive_pre_stability_ok(history, market, observation) >= 2,
                "stable_for_3_snapshots": consecutive_pre_stability_ok(history, market, observation) >= 3,
            }
        )
        decision = enter_decision_v1(hydrated)
        return ProofOfWinningEvaluation(True, decision.enter, decision.reason, hydrated)


def market_context(market: NormalizedMarket, observation: MarketObservation, live_state: LiveState) -> Optional[dict[str, str]]:
    if market_type(market.question) != "match":
        return None
    if "draw" in market.question.lower():
        return None
    if not market.teams or len(market.teams) != 2:
        return None
    score = parse_score(live_state.score)
    if score is None:
        return None
    home_team, away_team = market.teams[0], market.teams[1]
    home_goals, away_goals = score
    if home_goals == away_goals:
        return None
    leader_team = home_team if home_goals > away_goals else away_team
    trailing_team = away_team if home_goals > away_goals else home_team
    question_team = question_team_name(market.question)
    if not question_team:
        return None
    side = observation.side.lower()
    if normalize_text(question_team) == normalize_text(leader_team) and side == "yes":
        return {"leader_team": leader_team, "trailing_team": trailing_team}
    if normalize_text(question_team) == normalize_text(trailing_team) and side == "no":
        return {"leader_team": leader_team, "trailing_team": trailing_team}
    return None


def build_base_input(
    market: NormalizedMarket,
    observation: MarketObservation,
    detail: dict,
    leader_team: str,
    trailing_team: str,
) -> ProofOfWinningInput:
    score = detail_score(detail)
    minute = detail_elapsed(detail)
    goal_difference = None
    if score is not None:
        goal_difference = abs(score[0] - score[1])
    leader_red = team_red_cards(detail, leader_team) > 0
    trailing_red = team_red_cards(detail, trailing_team) > 0
    return ProofOfWinningInput(
        event_id=market.event_id,
        event_slug=market.event_slug,
        event_title=market.event_title,
        market_id=market.market_id,
        market_slug=market.market_slug,
        question=market.question,
        side=observation.side,
        minute=minute,
        score=observation.score,
        goal_difference=goal_difference,
        leader_team=leader_team,
        trailing_team=trailing_team,
        leader_red_card=leader_red,
        trailing_red_card=trailing_red,
    )


def consecutive_pre_stability_ok(history: list[dict], market: NormalizedMarket, observation: MarketObservation) -> int:
    count = 0
    for index in range(len(history) - 1, -1, -1):
        sub = history[: index + 1]
        latest = sub[-1]
        context = context_from_detail(market, observation, latest)
        if context is None:
            break
        base = build_base_input(market, observation, latest, context["leader_team"], context["trailing_team"])
        metrics = build_rolling_metrics(sub)
        hydrated = populate_input_with_metrics(base, metrics)
        effective = effective_goal_difference_from_detail(latest)
        hydrated = populate_input_with_effective_goal_difference(hydrated, effective)
        decision = enter_decision_pre_stability_v1(hydrated)
        if not decision.enter:
            break
        count += 1
    return count


def context_from_detail(market: NormalizedMarket, observation: MarketObservation, detail: dict) -> Optional[dict[str, str]]:
    score = detail_score(detail)
    if score is None or not market.teams or len(market.teams) != 2:
        return None
    home_team, away_team = market.teams[0], market.teams[1]
    home_goals, away_goals = score
    if home_goals == away_goals:
        return None
    leader_team = home_team if home_goals > away_goals else away_team
    trailing_team = away_team if home_goals > away_goals else home_team
    question_team = question_team_name(market.question)
    if not question_team:
        return None
    side = observation.side.lower()
    if normalize_text(question_team) == normalize_text(leader_team) and side == "yes":
        return {"leader_team": leader_team, "trailing_team": trailing_team}
    if normalize_text(question_team) == normalize_text(trailing_team) and side == "no":
        return {"leader_team": leader_team, "trailing_team": trailing_team}
    return None


def fixture_id_from_live_state(live_state: LiveState) -> str:
    raw = live_state.raw if isinstance(live_state.raw, dict) else {}
    fixture = raw.get("fixture") if isinstance(raw.get("fixture"), dict) else {}
    value = fixture.get("id")
    return str(value) if value not in (None, "") else ""


def detail_elapsed(detail: dict) -> Optional[float]:
    fixture = detail.get("fixture") if isinstance(detail.get("fixture"), dict) else {}
    fixture_row = fixture.get("fixture") if isinstance(fixture.get("fixture"), dict) else {}
    status = fixture_row.get("status") if isinstance(fixture_row.get("status"), dict) else {}
    try:
        value = status.get("elapsed")
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def detail_score(detail: dict) -> Optional[tuple[int, int]]:
    fixture = detail.get("fixture") if isinstance(detail.get("fixture"), dict) else {}
    goals = fixture.get("goals") if isinstance(fixture.get("goals"), dict) else {}
    try:
        home = int(float(goals.get("home")))
        away = int(float(goals.get("away")))
        return home, away
    except (TypeError, ValueError):
        return None


def team_red_cards(detail: dict, team_name: str) -> int:
    rows = detail.get("statistics") if isinstance(detail.get("statistics"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        team = row.get("team") if isinstance(row.get("team"), dict) else {}
        if normalize_text(str(team.get("name") or "")) != normalize_text(team_name):
            continue
        stats = row.get("statistics") if isinstance(row.get("statistics"), list) else []
        for item in stats:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip().lower() == "red cards":
                try:
                    value = item.get("value")
                    if value in ("", None):
                        return 0
                    return int(float(value))
                except (TypeError, ValueError):
                    return 0
    return 0


def parse_score(value: str) -> Optional[tuple[int, int]]:
    match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", value or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def question_team_name(question: str) -> str:
    match = re.search(r"Will\s+(.+?)\s+win\b", question, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip()


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())
