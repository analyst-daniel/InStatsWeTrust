from __future__ import annotations

import re
from dataclasses import dataclass, field
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
from app.storage.tracked_matches import TrackedMatches


@dataclass(frozen=True)
class ProofOfWinningEvaluation:
    applies: bool
    enter: bool
    reason: str
    payload: Optional[ProofOfWinningInput] = None
    diagnostics: dict = field(default_factory=dict)


class ProofOfWinningRuntime:
    def __init__(self, settings: dict, research_store: FootballResearchStore, tracked_matches: TrackedMatches | None = None) -> None:
        cfg = settings.get("proof_of_winning", {})
        self.enabled = bool(cfg.get("enabled", True))
        self.research_store = research_store
        self.history_limit = int(cfg.get("history_limit", 16))
        self.stats_lite_min_entry_price = float(cfg.get("stats_lite_min_entry_price", 0.85))
        self.score_events_enabled = bool(cfg.get("score_events_enabled", True))
        self.score_events_min_entry_price = float(cfg.get("score_events_min_entry_price", 0.90))
        self.score_events_min_elapsed = float(cfg.get("score_events_min_elapsed", 75))
        self.no_recent_goal_minutes = float(cfg.get("no_recent_goal_minutes", 5))
        self.tracked_matches = tracked_matches

    def evaluate(self, market: NormalizedMarket, observation: MarketObservation, live_state: LiveState | None) -> ProofOfWinningEvaluation:
        if not self.enabled:
            return ProofOfWinningEvaluation(False, False, observation.reason, None, {})
        if live_state is None:
            return ProofOfWinningEvaluation(False, False, observation.reason, None, {})
        context = market_context(market, observation, live_state)
        if context is None:
            return ProofOfWinningEvaluation(False, False, observation.reason, None, {})
        fixture_id = self.resolve_fixture_id(market, live_state)
        if not fixture_id:
            return ProofOfWinningEvaluation(True, False, "proof_of_winning_missing_fixture_id", None, {"confidence_reason": "missing_fixture_id"})
        history = self.research_store.load_recent_fixture_details(fixture_id, limit=self.history_limit)
        if not history:
            return ProofOfWinningEvaluation(
                True,
                False,
                "proof_of_winning_missing_detail_history",
                None,
                base_diagnostics(fixture_id, history, confidence_reason="missing_detail_history"),
            )
        latest = history[-1]
        base = build_base_input(market, observation, latest, context["leader_team"], context["trailing_team"])
        metrics = build_rolling_metrics(history)
        hydrated = populate_input_with_metrics(base, metrics)
        effective = effective_goal_difference_from_detail(latest)
        stable = consecutive_pre_stability_ok(history, market, observation)
        hydrated = populate_input_with_effective_goal_difference(hydrated, effective)
        hydrated = hydrated.model_copy(
            update={
                "stable_for_2_snapshots": stable >= 2,
                "stable_for_3_snapshots": stable >= 3,
            }
        )
        stable_score_events = consecutive_score_events_stability_ok(history, market, observation, self.no_recent_goal_minutes)
        decision = enter_decision_v1(hydrated)
        diagnostics = base_diagnostics(
            fixture_id,
            history,
            source_fields_present=list(metrics.source_fields_present),
            data_confidence_flag=bool(metrics.data_confidence_flag),
            last_5_ready=window_ready(history, 5),
            last_10_ready=window_ready(history, 10),
            stable_snapshot_count=stable,
            score_events_stable_snapshot_count=stable_score_events,
            confidence_reason=confidence_reason_proof(metrics),
        )
        diagnostics["evaluation_path"] = "stats_lite"
        if decision.enter and observation.price < self.stats_lite_min_entry_price:
            return ProofOfWinningEvaluation(
                True,
                False,
                "proof_of_winning_stats_lite_price_below_min",
                hydrated,
                diagnostics | {"min_entry_price": self.stats_lite_min_entry_price, "price": observation.price},
            )
        if not decision.enter and self.score_events_enabled:
            fallback = score_events_decision(
                hydrated,
                observation,
                stable_score_events=stable_score_events,
                min_entry_price=self.score_events_min_entry_price,
                min_elapsed=self.score_events_min_elapsed,
                no_recent_goal_minutes=self.no_recent_goal_minutes,
            )
            if fallback.enter:
                diagnostics["evaluation_path"] = "score_events"
                return ProofOfWinningEvaluation(True, True, fallback.reason, hydrated, diagnostics)
        return ProofOfWinningEvaluation(True, decision.enter, decision.reason, hydrated, diagnostics)

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


def consecutive_score_events_stability_ok(history: list[dict], market: NormalizedMarket, observation: MarketObservation, no_recent_goal_minutes: float) -> int:
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
        if not score_events_core_ok(hydrated, no_recent_goal_minutes=no_recent_goal_minutes):
            break
        count += 1
    return count


@dataclass(frozen=True)
class ScoreEventsDecision:
    enter: bool
    reason: str


def score_events_decision(
    data: ProofOfWinningInput,
    observation: MarketObservation,
    *,
    stable_score_events: int,
    min_entry_price: float,
    min_elapsed: float,
    no_recent_goal_minutes: float,
) -> ScoreEventsDecision:
    if observation.price < min_entry_price:
        return ScoreEventsDecision(False, "proof_of_winning_score_events_price_below_min")
    if data.minute is None or data.minute < min_elapsed or data.minute >= 89:
        return ScoreEventsDecision(False, "proof_of_winning_score_events_minute_outside_window")
    if not score_events_core_ok(data, no_recent_goal_minutes=no_recent_goal_minutes):
        return ScoreEventsDecision(False, "proof_of_winning_score_events_core_rejected")
    if stable_score_events < 2:
        return ScoreEventsDecision(False, "proof_of_winning_score_events_not_stable")
    return ScoreEventsDecision(True, "proof_of_winning_score_events_enter")


def score_events_core_ok(data: ProofOfWinningInput, *, no_recent_goal_minutes: float) -> bool:
    if data.goal_difference is None or data.goal_difference < 2:
        return False
    if data.leader_red_card:
        return False
    if data.red_card_in_last_10min:
        return False
    if data.goal_in_last_5min:
        return False
    if data.time_since_last_goal is not None and data.time_since_last_goal < no_recent_goal_minutes:
        return False
    return True


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


def window_ready(history: list[dict], minutes: float) -> bool:
    if not history:
        return False
    latest = history[-1]
    current_elapsed = detail_elapsed(latest)
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
    score_events_stable_snapshot_count: int = 0,
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
        "score_events_stable_snapshot_count": score_events_stable_snapshot_count,
        "confidence_reason": confidence_reason,
    }


def confidence_reason_proof(metrics) -> str:
    required = [
        "shots_last_5",
        "shots_last_10",
        "shots_on_target_last_10",
        "corners_last_10",
    ]
    present = set(metrics.source_fields_present or [])
    missing = [field for field in required if field not in present]
    if missing:
        return "missing_fields:" + ",".join(missing)
    if not metrics.data_confidence_flag:
        return "data_confidence_false"
    return "ok"
