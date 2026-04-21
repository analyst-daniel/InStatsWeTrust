from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.live_state.football_research import FootballResearchStore
from app.normalize.models import LiveState, MarketObservation, NormalizedMarket
from app.normalize.normalizer import market_type
from app.strategy.goal_totals_under import (
    GoalTotalsUnderEnterDecision,
    GoalTotalsUnderInput,
    build_goal_totals_under_input,
    goal_totals_under_enter_decision_pre_stability_v1,
    goal_totals_under_enter_decision_v1,
)
from app.strategy.goal_totals_under_metrics import (
    build_goal_totals_under_rolling_metrics,
    populate_goal_totals_under_input_with_metrics,
)
from app.strategy.proof_of_winning_metrics import fixture_elapsed_from_detail, fixture_score, fixture_teams


@dataclass(frozen=True)
class GoalTotalsUnderEvaluation:
    applies: bool
    enter: bool
    reason: str
    payload: Optional[GoalTotalsUnderInput] = None


class GoalTotalsUnderRuntime:
    def __init__(self, settings: dict, research_store: FootballResearchStore) -> None:
        cfg = settings.get("goal_totals_under", {})
        self.enabled = bool(cfg.get("enabled", True))
        self.history_limit = int(cfg.get("history_limit", 16))
        self.research_store = research_store

    def evaluate(
        self,
        market: NormalizedMarket,
        observation: MarketObservation,
        live_state: LiveState | None,
    ) -> GoalTotalsUnderEvaluation:
        if not self.enabled:
            return GoalTotalsUnderEvaluation(False, False, observation.reason, None)
        if market_type(market.question) != "total":
            return GoalTotalsUnderEvaluation(False, False, observation.reason, None)
        if live_state is None:
            return GoalTotalsUnderEvaluation(True, False, "goal_totals_under_missing_live_state", None)
        fixture_id = fixture_id_from_live_state(live_state)
        if not fixture_id:
            return GoalTotalsUnderEvaluation(True, False, "goal_totals_under_missing_fixture_id", None)
        history = self.research_store.load_recent_fixture_details(fixture_id, limit=self.history_limit)
        if not history:
            return GoalTotalsUnderEvaluation(True, False, "goal_totals_under_missing_detail_history", None)
        latest = history[-1]
        base = build_base_input(market, observation, latest)
        if base is None:
            return GoalTotalsUnderEvaluation(True, False, "goal_totals_under_missing_score_context", None)
        metrics = build_goal_totals_under_rolling_metrics(history)
        hydrated = populate_goal_totals_under_input_with_metrics(base, metrics)
        stable = consecutive_pre_stability_ok(history, market, observation)
        hydrated = hydrated.model_copy(
            update={
                "stable_for_2_snapshots": stable >= 2,
                "stable_for_3_snapshots": stable >= 3,
            }
        )
        decision = goal_totals_under_enter_decision_v1(hydrated)
        return GoalTotalsUnderEvaluation(True, decision.enter, decision.reason, hydrated)


def consecutive_pre_stability_ok(
    history: list[dict],
    market: NormalizedMarket,
    observation: MarketObservation,
) -> int:
    count = 0
    for index in range(len(history) - 1, -1, -1):
        sub = history[: index + 1]
        latest = sub[-1]
        base = build_base_input(market, observation, latest)
        if base is None:
            break
        metrics = build_goal_totals_under_rolling_metrics(sub)
        hydrated = populate_goal_totals_under_input_with_metrics(base, metrics)
        decision = goal_totals_under_enter_decision_pre_stability_v1(hydrated)
        if not decision.enter:
            break
        count += 1
    return count


def build_base_input(
    market: NormalizedMarket,
    observation: MarketObservation,
    detail: dict,
) -> GoalTotalsUnderInput | None:
    home_team, away_team = fixture_teams(detail)
    if not home_team or not away_team:
        if market.teams and len(market.teams) == 2:
            home_team, away_team = market.teams[0], market.teams[1]
        else:
            return None
    score_pair = fixture_score(detail)
    score = f"{score_pair[0]}-{score_pair[1]}"
    minute = fixture_elapsed_from_detail(detail)
    if minute is None:
        minute = observation.elapsed
    red_card_flag = team_red_cards(detail, home_team) > 0 or team_red_cards(detail, away_team) > 0
    return build_goal_totals_under_input(
        event_id=market.event_id,
        event_slug=market.event_slug,
        event_title=market.event_title,
        market_id=market.market_id,
        market_slug=market.market_slug,
        question=market.question,
        side=observation.side,
        minute=minute,
        score=score,
        home_team=home_team,
        away_team=away_team,
        data_confidence_flag=True,
        red_card_flag=red_card_flag,
    )


def fixture_id_from_live_state(live_state: LiveState) -> str:
    raw = live_state.raw if isinstance(live_state.raw, dict) else {}
    fixture = raw.get("fixture") if isinstance(raw.get("fixture"), dict) else {}
    value = fixture.get("id")
    return str(value) if value not in (None, "") else ""


def team_red_cards(detail: dict, team_name: str) -> int:
    rows = detail.get("statistics") if isinstance(detail.get("statistics"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        team = row.get("team") if isinstance(row.get("team"), dict) else {}
        if str(team.get("name") or "").strip().lower() != team_name.strip().lower():
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
