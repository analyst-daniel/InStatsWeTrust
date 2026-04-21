from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.live_state.football_research import FootballResearchStore
from app.normalize.models import LiveState, MarketObservation, NormalizedMarket
from app.normalize.normalizer import market_type
from app.strategy.proof_of_winning_metrics import fixture_elapsed_from_detail, fixture_score, fixture_teams
from app.strategy.spread_confirmation import (
    SpreadEnterDecision,
    SpreadConfirmationInput,
    SpreadSideType,
    build_spread_input,
    spread_minus_enter_decision_pre_stability_v1,
    spread_minus_enter_decision_v1,
    spread_plus_enter_decision_pre_stability_v1,
    spread_plus_enter_decision_v1,
)
from app.strategy.spread_confirmation_metrics import build_spread_rolling_metrics, populate_spread_input_with_metrics


@dataclass(frozen=True)
class SpreadConfirmationEvaluation:
    applies: bool
    enter: bool
    reason: str
    payload: Optional[SpreadConfirmationInput] = None


class SpreadConfirmationRuntime:
    def __init__(self, settings: dict, research_store: FootballResearchStore) -> None:
        cfg = settings.get("spread_confirmation", {})
        self.enabled = bool(cfg.get("enabled", True))
        self.history_limit = int(cfg.get("history_limit", 16))
        self.research_store = research_store

    def evaluate(
        self,
        market: NormalizedMarket,
        observation: MarketObservation,
        live_state: LiveState | None,
    ) -> SpreadConfirmationEvaluation:
        if not self.enabled:
            return SpreadConfirmationEvaluation(False, False, observation.reason, None)
        if market_type(market.question) != "spread":
            return SpreadConfirmationEvaluation(False, False, observation.reason, None)
        if live_state is None:
            return SpreadConfirmationEvaluation(True, False, "spread_confirmation_missing_live_state", None)
        fixture_id = fixture_id_from_live_state(live_state)
        if not fixture_id:
            return SpreadConfirmationEvaluation(True, False, "spread_confirmation_missing_fixture_id", None)
        history = self.research_store.load_recent_fixture_details(fixture_id, limit=self.history_limit)
        if not history:
            return SpreadConfirmationEvaluation(True, False, "spread_confirmation_missing_detail_history", None)
        latest = history[-1]
        base = build_base_input(market, observation, latest)
        if base is None:
            return SpreadConfirmationEvaluation(True, False, "spread_confirmation_missing_score_context", None)
        metrics = build_spread_rolling_metrics(history)
        hydrated = populate_input_with_stability(base, history, metrics, market, observation)
        decision = final_decision(hydrated)
        return SpreadConfirmationEvaluation(True, decision.enter, decision.reason, hydrated)


def populate_input_with_stability(
    base: SpreadConfirmationInput,
    history: list[dict],
    metrics,
    market: NormalizedMarket,
    observation: MarketObservation,
) -> SpreadConfirmationInput:
    hydrated = populate_spread_input_with_metrics(base, metrics)
    stable = consecutive_pre_stability_ok(history, market, observation)
    return hydrated.model_copy(
        update={
            "stable_for_2_snapshots": stable >= 2,
            "stable_for_3_snapshots": stable >= 3,
        }
    )


def consecutive_pre_stability_ok(history: list[dict], market: NormalizedMarket, observation: MarketObservation) -> int:
    count = 0
    for index in range(len(history) - 1, -1, -1):
        sub = history[: index + 1]
        latest = sub[-1]
        base = build_base_input(market, observation, latest)
        if base is None:
            break
        metrics = build_spread_rolling_metrics(sub)
        hydrated = populate_spread_input_with_metrics(base, metrics)
        decision = pre_stability_decision(hydrated)
        if not decision.enter:
            break
        count += 1
    return count


def pre_stability_decision(data: SpreadConfirmationInput):
    if data.selected_side_type == SpreadSideType.PLUS:
        return spread_plus_enter_decision_pre_stability_v1(data)
    if data.selected_side_type == SpreadSideType.MINUS:
        return spread_minus_enter_decision_pre_stability_v1(data)
    return SpreadEnterDecision(False, "spread_confirmation_unknown_selected_side")


def final_decision(data: SpreadConfirmationInput):
    if data.selected_side_type == SpreadSideType.PLUS:
        return spread_plus_enter_decision_v1(data)
    if data.selected_side_type == SpreadSideType.MINUS:
        return spread_minus_enter_decision_v1(data)
    return SpreadEnterDecision(False, "spread_confirmation_unknown_selected_side")


def build_base_input(
    market: NormalizedMarket,
    observation: MarketObservation,
    detail: dict,
) -> Optional[SpreadConfirmationInput]:
    home_team, away_team = fixture_teams(detail)
    if not home_team or not away_team:
        if market.teams and len(market.teams) == 2:
            home_team, away_team = market.teams[0], market.teams[1]
        else:
            return None
    score_pair = fixture_score(detail)
    if score_pair[0] == score_pair[1]:
        score = f"{score_pair[0]}-{score_pair[1]}"
    else:
        score = f"{score_pair[0]}-{score_pair[1]}"
    minute = fixture_elapsed_from_detail(detail)
    if minute is None:
        minute = observation.elapsed
    leader_team = home_team if score_pair[0] > score_pair[1] else away_team
    trailing_team = away_team if score_pair[0] > score_pair[1] else home_team
    leader_red = team_red_cards(detail, leader_team) > 0
    trailing_red = team_red_cards(detail, trailing_team) > 0
    return build_spread_input(
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
        leader_red_card=leader_red,
        trailing_red_card=trailing_red,
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


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())
