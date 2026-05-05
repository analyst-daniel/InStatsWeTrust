from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.live_state.football_research import FootballResearchStore
from app.normalize.models import LiveState, MarketObservation, NormalizedMarket
from app.normalize.normalizer import market_type
from app.strategy.goal_totals_under import (
    GoalTotalsUnderEnterDecision,
    GoalTotalsUnderInput,
    build_goal_totals_under_input,
    goal_totals_under_enter_decision_score_only_v1,
    goal_totals_under_enter_decision_score_only_v2,
    goal_totals_under_enter_decision_pre_stability_v1,
    goal_totals_under_enter_decision_v1,
)
from app.strategy.goal_totals_under_metrics import (
    build_goal_totals_under_rolling_metrics,
    populate_goal_totals_under_input_with_metrics,
)
from app.strategy.proof_of_winning_metrics import fixture_elapsed_from_detail, fixture_score, fixture_teams
from app.storage.tracked_matches import TrackedMatches


@dataclass(frozen=True)
class GoalTotalsUnderEvaluation:
    applies: bool
    enter: bool
    reason: str
    payload: Optional[GoalTotalsUnderInput] = None
    diagnostics: dict = field(default_factory=dict)


class GoalTotalsUnderRuntime:
    def __init__(self, settings: dict, research_store: FootballResearchStore, tracked_matches: TrackedMatches | None = None) -> None:
        cfg = settings.get("goal_totals_under", {})
        self.enabled = bool(cfg.get("enabled", True))
        self.history_limit = int(cfg.get("history_limit", 16))
        self.min_entry_price = float(cfg.get("min_entry_price", 0.60))
        self.allow_score_only_fallback = bool(cfg.get("allow_score_only_fallback", False))
        self.score_only_v2_enabled = bool(cfg.get("score_only_v2_enabled", True))
        self.max_clock_drift_minutes = float(cfg.get("max_clock_drift_minutes", 12))
        self.research_store = research_store
        self.tracked_matches = tracked_matches

    def evaluate(
        self,
        market: NormalizedMarket,
        observation: MarketObservation,
        live_state: LiveState | None,
    ) -> GoalTotalsUnderEvaluation:
        if not self.enabled:
            return GoalTotalsUnderEvaluation(False, False, observation.reason, None, {})
        if market_type(market.question) != "total":
            return GoalTotalsUnderEvaluation(False, False, observation.reason, None, {})
        if live_state is None:
            return GoalTotalsUnderEvaluation(True, False, "goal_totals_under_missing_live_state", None, {"confidence_reason": "missing_live_state"})
        if observation.side.strip().lower() == "under" and observation.price < self.min_entry_price:
            return GoalTotalsUnderEvaluation(
                True,
                False,
                "goal_totals_under_price_below_min",
                None,
                {"min_entry_price": self.min_entry_price, "price": observation.price},
            )
        clock_reason = implausible_market_clock_reason(
            market,
            observation,
            live_state,
            max_clock_drift_minutes=self.max_clock_drift_minutes,
        )
        if clock_reason:
            return GoalTotalsUnderEvaluation(
                True,
                False,
                clock_reason,
                None,
                {
                    "market_start_time": market.start_time,
                    "elapsed": live_state.elapsed,
                    "period": live_state.period,
                    "max_clock_drift_minutes": self.max_clock_drift_minutes,
                },
            )
        fixture_id = self.resolve_fixture_id(market, live_state)
        score_only = build_score_only_input(market, observation, live_state)
        if not fixture_id:
            return evaluate_score_only_or_fail(
                score_only,
                "goal_totals_under_missing_fixture_id",
                {"confidence_reason": "missing_fixture_id", "evaluation_path": "v1_fallback_no_fixture"},
                allow_enter=self.allow_score_only_fallback,
            )
        history = self.research_store.load_recent_fixture_details(fixture_id, limit=self.history_limit)
        if not history:
            diagnostics = base_diagnostics(fixture_id, history, confidence_reason="missing_detail_history")
            diagnostics["evaluation_path"] = "v1_fallback_missing_history"
            return evaluate_score_only_or_fail(score_only, "goal_totals_under_missing_detail_history", diagnostics, allow_enter=self.allow_score_only_fallback)
        latest = history[-1]
        base = build_base_input(market, observation, latest)
        if base is None:
            diagnostics = base_diagnostics(fixture_id, history, confidence_reason="missing_score_context")
            diagnostics["evaluation_path"] = "v1_fallback_missing_score_context"
            return evaluate_score_only_or_fail(score_only, "goal_totals_under_missing_score_context", diagnostics, allow_enter=self.allow_score_only_fallback)
        metrics = build_goal_totals_under_rolling_metrics(history)
        hydrated = populate_goal_totals_under_input_with_metrics(base, metrics)
        stable_score_only = consecutive_score_only_stability_ok(history, market, observation)
        stable = consecutive_pre_stability_ok(history, market, observation) if metrics.data_confidence_flag else 0
        hydrated = hydrated.model_copy(
            update={
                "stable_for_2_snapshots": stable_score_only >= 2,
                "stable_for_3_snapshots": stable_score_only >= 3,
            }
        )
        diagnostics = base_diagnostics(
            fixture_id,
            history,
            source_fields_present=list(metrics.source_fields_present),
            data_confidence_flag=bool(metrics.data_confidence_flag),
            last_5_ready=window_ready(history, 5),
            last_10_ready=window_ready(history, 10),
            stable_snapshot_count=stable_score_only,
            confidence_reason=confidence_reason_under(metrics),
        )
        if self.score_only_v2_enabled:
            decision_v2 = goal_totals_under_enter_decision_score_only_v2(hydrated)
            diagnostics["evaluation_path"] = "score_only_v2"
            diagnostics["live_stats_available"] = bool(metrics.data_confidence_flag)
            return GoalTotalsUnderEvaluation(True, decision_v2.enter, decision_v2.reason, hydrated, diagnostics)

        hydrated = hydrated.model_copy(
            update={
                "stable_for_2_snapshots": stable >= 2,
                "stable_for_3_snapshots": stable >= 3,
            }
        )
        decision = goal_totals_under_enter_decision_v1(hydrated)
        if decision.enter:
            diagnostics["evaluation_path"] = "v2_live_stats"
            return GoalTotalsUnderEvaluation(True, True, decision.reason, hydrated, diagnostics)

        if not metrics.data_confidence_flag and score_only is not None:
            fallback = goal_totals_under_enter_decision_score_only_v1(score_only)
            diagnostics["evaluation_path"] = "v1_fallback_low_confidence"
            if fallback.enter and self.allow_score_only_fallback:
                diagnostics["score_only_reason"] = fallback.reason
                return GoalTotalsUnderEvaluation(True, True, fallback.reason, score_only, diagnostics)
            diagnostics["score_only_reason"] = fallback.reason
            reason = fallback.reason if not fallback.enter else "goal_totals_under_score_only_fallback_disabled"
            return GoalTotalsUnderEvaluation(True, False, reason, score_only, diagnostics)

        diagnostics["evaluation_path"] = "v2_live_stats"
        return GoalTotalsUnderEvaluation(True, False, decision.reason, hydrated, diagnostics)

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


def consecutive_score_only_stability_ok(
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
        decision = goal_totals_under_enter_decision_score_only_v1(hydrated)
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


def build_score_only_input(
    market: NormalizedMarket,
    observation: MarketObservation,
    live_state: LiveState,
) -> GoalTotalsUnderInput | None:
    home_team = market.teams[0] if market.teams else ""
    away_team = market.teams[1] if market.teams and len(market.teams) == 2 else ""
    if not home_team or not away_team:
        return None
    return build_goal_totals_under_input(
        event_id=market.event_id,
        event_slug=market.event_slug,
        event_title=market.event_title,
        market_id=market.market_id,
        market_slug=market.market_slug,
        question=market.question,
        side=observation.side,
        minute=live_state.elapsed if live_state is not None else observation.elapsed,
        score=live_state.score if live_state is not None else observation.score,
        home_team=home_team,
        away_team=away_team,
        data_confidence_flag=True,
        red_card_flag=False,
    )


def fixture_id_from_live_state(live_state: LiveState) -> str:
    raw = live_state.raw if isinstance(live_state.raw, dict) else {}
    fixture = raw.get("fixture") if isinstance(raw.get("fixture"), dict) else {}
    value = fixture.get("id")
    return str(value) if value not in (None, "") else ""


def implausible_market_clock_reason(
    market: NormalizedMarket,
    observation: MarketObservation,
    live_state: LiveState,
    *,
    max_clock_drift_minutes: float,
) -> str:
    if live_state.elapsed is None:
        return ""
    start = parse_datetime_utc(market.start_time)
    if start is None:
        return ""
    observed_at = observation.timestamp_utc
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    observed_at = observed_at.astimezone(timezone.utc)
    earliest_plausible = start + timedelta(minutes=max(0.0, float(live_state.elapsed) - max_clock_drift_minutes))
    if observed_at < earliest_plausible:
        return "goal_totals_under_implausible_market_clock"
    return ""


def parse_datetime_utc(value: str) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S%z")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def confidence_reason_under(metrics) -> str:
    required = ["shots_last_10", "shots_on_target_last_10", "dangerous_attacks_last_10", "attacks_last_10", "corners_last_10"]
    present = set(metrics.source_fields_present or [])
    missing = [field for field in required if field not in present]
    if missing:
        return "missing_fields:" + ",".join(missing)
    if not metrics.data_confidence_flag:
        return "data_confidence_false"
    return "ok"


def evaluate_score_only_or_fail(
    score_only: GoalTotalsUnderInput | None,
    failure_reason: str,
    diagnostics: dict,
    *,
    allow_enter: bool = False,
) -> GoalTotalsUnderEvaluation:
    if score_only is not None:
        fallback = goal_totals_under_enter_decision_score_only_v1(score_only)
        diagnostics["score_only_reason"] = fallback.reason
        if fallback.enter and allow_enter:
            return GoalTotalsUnderEvaluation(True, True, fallback.reason, score_only, diagnostics)
        if fallback.enter:
            return GoalTotalsUnderEvaluation(True, False, failure_reason, score_only, diagnostics)
        return GoalTotalsUnderEvaluation(True, False, fallback.reason, score_only, diagnostics)
    return GoalTotalsUnderEvaluation(True, False, failure_reason, None, diagnostics)
