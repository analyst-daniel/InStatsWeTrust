from __future__ import annotations

import re
from dataclasses import dataclass, field
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
    spread_minus_enter_decision_score_only_v2,
    spread_minus_enter_decision_pre_stability_v1,
    spread_minus_enter_decision_v1,
    spread_plus_enter_decision_score_only_v2,
    spread_plus_enter_decision_pre_stability_v1,
    spread_plus_enter_decision_v1,
)
from app.strategy.spread_confirmation_metrics import build_spread_rolling_metrics, populate_spread_input_with_metrics
from app.storage.tracked_matches import TrackedMatches


@dataclass(frozen=True)
class SpreadConfirmationEvaluation:
    applies: bool
    enter: bool
    reason: str
    payload: Optional[SpreadConfirmationInput] = None
    diagnostics: dict = field(default_factory=dict)


class SpreadConfirmationRuntime:
    def __init__(self, settings: dict, research_store: FootballResearchStore, tracked_matches: TrackedMatches | None = None) -> None:
        cfg = settings.get("spread_confirmation", {})
        self.enabled = bool(cfg.get("enabled", True))
        self.history_limit = int(cfg.get("history_limit", 16))
        self.score_only_v2_enabled = bool(cfg.get("score_only_v2_enabled", True))
        self.research_store = research_store
        self.tracked_matches = tracked_matches

    def evaluate(
        self,
        market: NormalizedMarket,
        observation: MarketObservation,
        live_state: LiveState | None,
    ) -> SpreadConfirmationEvaluation:
        if not self.enabled:
            return SpreadConfirmationEvaluation(False, False, observation.reason, None, {})
        if market_type(market.question) != "spread":
            return SpreadConfirmationEvaluation(False, False, observation.reason, None, {})
        if live_state is None:
            return SpreadConfirmationEvaluation(True, False, "spread_confirmation_missing_live_state", None, {"confidence_reason": "missing_live_state"})
        fixture_id = self.resolve_fixture_id(market, live_state)
        if not fixture_id:
            return SpreadConfirmationEvaluation(True, False, "spread_confirmation_missing_fixture_id", None, {"confidence_reason": "missing_fixture_id"})
        history = self.research_store.load_recent_fixture_details(fixture_id, limit=self.history_limit)
        if not history:
            return SpreadConfirmationEvaluation(
                True,
                False,
                "spread_confirmation_missing_detail_history",
                None,
                base_diagnostics(fixture_id, history, confidence_reason="missing_detail_history"),
            )
        latest = history[-1]
        base = build_base_input(market, observation, latest)
        if base is None:
            return SpreadConfirmationEvaluation(
                True,
                False,
                "spread_confirmation_missing_score_context",
                None,
                base_diagnostics(fixture_id, history, confidence_reason="missing_score_context"),
            )
        metrics = build_spread_rolling_metrics(history)
        stable_score_only = consecutive_score_only_stability_ok(history, market, observation)
        stable = consecutive_pre_stability_ok(history, market, observation) if metrics.data_confidence_flag else 0
        if self.score_only_v2_enabled:
            hydrated = populate_input_with_stability(base, stable_score_only, metrics)
            decision = score_only_v2_decision(hydrated)
            diagnostics = base_diagnostics(
                fixture_id,
                history,
                source_fields_present=list(metrics.source_fields_present),
                data_confidence_flag=bool(metrics.data_confidence_flag),
                last_5_ready=window_ready(history, 5),
                last_10_ready=window_ready(history, 10),
                stable_snapshot_count=stable_score_only,
                confidence_reason=confidence_reason_spread(metrics),
            )
            diagnostics["evaluation_path"] = "score_only_v2"
            diagnostics["live_stats_available"] = bool(metrics.data_confidence_flag)
            return SpreadConfirmationEvaluation(True, decision.enter, decision.reason, hydrated, diagnostics)

        hydrated = populate_input_with_stability(base, stable, metrics)
        decision = final_decision(hydrated)
        diagnostics = base_diagnostics(
            fixture_id,
            history,
            source_fields_present=list(metrics.source_fields_present),
            data_confidence_flag=bool(metrics.data_confidence_flag),
            last_5_ready=window_ready(history, 5),
            last_10_ready=window_ready(history, 10),
            stable_snapshot_count=stable,
            confidence_reason=confidence_reason_spread(metrics),
        )
        return SpreadConfirmationEvaluation(True, decision.enter, decision.reason, hydrated, diagnostics)

    def resolve_fixture_id(self, market: NormalizedMarket, live_state: LiveState) -> str:
        fixture_id = fixture_id_from_live_state(live_state)
        if fixture_id:
            if self.tracked_matches is not None:
                self.tracked_matches.attach_fixture_mapping(
                    event_id=market.event_id,
                    event_slug=market.event_slug,
                    event_title=market.event_title,
                    fixture_id=fixture_id,
                    live_slug=live_state.slug,
                )
            return fixture_id
        if self.tracked_matches is None:
            tracked_fixture = ""
        else:
            tracked_fixture = self.tracked_matches.resolve_fixture_id(
                event_id=market.event_id,
                event_slug=market.event_slug,
                event_title=market.event_title,
            )
        if tracked_fixture:
            return tracked_fixture
        fixture_id = self.research_store.resolve_fixture_id(event_title=market.event_title, teams=market.teams)
        if fixture_id and self.tracked_matches is not None:
            self.tracked_matches.attach_fixture_mapping(
                event_id=market.event_id,
                event_slug=market.event_slug,
                event_title=market.event_title,
                fixture_id=fixture_id,
                live_slug=live_state.slug,
                mapping_confidence="research_manifest",
            )
        return fixture_id


def populate_input_with_stability(
    base: SpreadConfirmationInput,
    stable: int,
    metrics,
) -> SpreadConfirmationInput:
    hydrated = populate_spread_input_with_metrics(base, metrics)
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


def consecutive_score_only_stability_ok(history: list[dict], market: NormalizedMarket, observation: MarketObservation) -> int:
    count = 0
    for index in range(len(history) - 1, -1, -1):
        sub = history[: index + 1]
        latest = sub[-1]
        base = build_base_input(market, observation, latest)
        if base is None:
            break
        metrics = build_spread_rolling_metrics(sub)
        hydrated = populate_input_with_stability(base, 2, metrics)
        decision = score_only_v2_core_decision(hydrated)
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


def score_only_v2_core_decision(data: SpreadConfirmationInput):
    stable_data = data.model_copy(update={"stable_for_2_snapshots": True, "stable_for_3_snapshots": True})
    return score_only_v2_decision(stable_data)


def score_only_v2_decision(data: SpreadConfirmationInput):
    if data.selected_side_type == SpreadSideType.PLUS:
        return spread_plus_enter_decision_score_only_v2(data)
    if data.selected_side_type == SpreadSideType.MINUS:
        return spread_minus_enter_decision_score_only_v2(data)
    return SpreadEnterDecision(False, "spread_confirmation_v2_unknown_selected_side")


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
    leader_red = team_red_cards(detail, leader_team) > 0 or team_red_card_events(detail, leader_team) > 0
    trailing_red = team_red_cards(detail, trailing_team) > 0 or team_red_card_events(detail, trailing_team) > 0
    any_red = any_red_card_event(detail)
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
        leader_red_card=leader_red or any_red,
        trailing_red_card=trailing_red or any_red,
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


def team_red_card_events(detail: dict, team_name: str) -> int:
    events = detail.get("events") if isinstance(detail.get("events"), list) else []
    count = 0
    for row in events:
        if not isinstance(row, dict):
            continue
        event_type = str(row.get("type") or "").lower()
        event_detail = str(row.get("detail") or "").lower()
        if "red card" not in event_type and "red card" not in event_detail:
            continue
        team = row.get("team") if isinstance(row.get("team"), dict) else {}
        if normalize_text(str(team.get("name") or "")) == normalize_text(team_name):
            count += 1
    return count


def any_red_card_event(detail: dict) -> bool:
    events = detail.get("events") if isinstance(detail.get("events"), list) else []
    for row in events:
        if not isinstance(row, dict):
            continue
        event_type = str(row.get("type") or "").lower()
        event_detail = str(row.get("detail") or "").lower()
        if "red card" in event_type or "red card" in event_detail:
            return True
    return False


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def window_ready(history: list[dict], minutes: float) -> bool:
    if not history:
        return False
    latest = history[-1]
    current_elapsed = fixture_elapsed_from_detail(latest)
    if current_elapsed is None:
        return False
    from app.strategy.proof_of_winning_metrics import nearest_snapshot_before_elapsed

    return nearest_snapshot_before_elapsed(history, current_elapsed - minutes) is not None


def base_diagnostics(
    fixture_id: str,
    history: list[dict],
    *,
    source_fields_present: list[str] | None = None,
    data_confidence_flag: bool | None = None,
    last_5_ready: bool = False,
    last_10_ready: bool = False,
    stable_snapshot_count: int = 0,
    confidence_reason: str = "",
) -> dict:
    latest = history[-1] if history else {}
    statistics = latest.get("statistics") if isinstance(latest, dict) else []
    events = latest.get("events") if isinstance(latest, dict) else []
    return {
        "fixture_id": fixture_id,
        "detail_history_count": len(history),
        "has_statistics": bool(isinstance(statistics, list) and len(statistics) > 0),
        "has_events": bool(isinstance(events, list) and len(events) > 0),
        "source_fields_present_count": len(source_fields_present or []),
        "source_fields_present": ", ".join(source_fields_present or []),
        "data_confidence_flag": data_confidence_flag if data_confidence_flag is not None else False,
        "last_5_ready": last_5_ready,
        "last_10_ready": last_10_ready,
        "stable_snapshot_count": stable_snapshot_count,
        "confidence_reason": confidence_reason,
    }


def confidence_reason_spread(metrics) -> str:
    required = [
        "leader_shots_last_10",
        "leader_shots_on_target_last_10",
        "leader_dangerous_attacks_last_10",
        "leader_corners_last_10",
        "underdog_shots_last_10",
        "underdog_shots_on_target_last_10",
        "underdog_dangerous_attacks_last_10",
        "underdog_corners_last_10",
    ]
    present = set(metrics.source_fields_present or [])
    missing = [field for field in required if field not in present]
    if missing:
        return "missing_fields:" + ",".join(missing)
    if not metrics.data_confidence_flag:
        return "data_confidence_false"
    return "ok"
