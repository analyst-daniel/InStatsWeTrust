from __future__ import annotations

from datetime import datetime, timezone

from app.live_state.football_research import FootballResearchStore
from app.normalize.models import LiveState, MarketObservation, NormalizedMarket
from app.strategy.goal_totals_under_runtime import GoalTotalsUnderRuntime


def fixture_row(elapsed: int, home_goals: int = 1, away_goals: int = 0) -> dict:
    return {
        "fixture": {"id": 12345, "status": {"short": "2H", "elapsed": elapsed}},
        "teams": {"home": {"name": "Cerezo Osaka"}, "away": {"name": "Kyoto Sanga FC"}},
        "goals": {"home": home_goals, "away": away_goals},
        "league": {"name": "J1 League", "sport": "Football"},
    }


def stats_payload(values: dict) -> list[dict]:
    return [
        {"type": "Total Shots", "value": values.get("shots", 0)},
        {"type": "Shots on Goal", "value": values.get("shots_on_target", 0)},
        {"type": "Shots off Goal", "value": values.get("shots_off_target", 0)},
        {"type": "Corner Kicks", "value": values.get("corners", 0)},
        {"type": "Dangerous Attacks", "value": values.get("dangerous_attacks", 0)},
        {"type": "Attacks", "value": values.get("attacks", 0)},
        {"type": "Red Cards", "value": values.get("red_cards", 0)},
    ]


def write_detail(
    store: FootballResearchStore,
    *,
    elapsed: int,
    home_stats: dict,
    away_stats: dict,
    events: list[dict] | None = None,
) -> None:
    store.write_fixture_detail(
        "12345",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC",
        fixture_payload=fixture_row(elapsed),
        statistics=[
            {"team": {"name": "Cerezo Osaka"}, "statistics": stats_payload(home_stats)},
            {"team": {"name": "Kyoto Sanga FC"}, "statistics": stats_payload(away_stats)},
        ],
        events=events or [],
    )


def make_market(question: str = "Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5") -> NormalizedMarket:
    return NormalizedMarket(
        event_id="296790",
        event_slug="j1100-cer-kyo-2026-04-18-more-markets",
        event_title="Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        market_id="1674823",
        market_slug="j1100-cer-kyo-2026-04-18-ou-3pt5",
        question=question,
        sport="soccer",
        category="sports",
        teams=["Cerezo Osaka", "Kyoto Sanga FC"],
        active=True,
        closed=False,
        token_ids=["over-token", "under-token"],
        yes_token_id="over-token",
        no_token_id="under-token",
        outcomes=["Over", "Under"],
        best_bid_yes=0.02,
        best_ask_yes=0.03,
        best_bid_no=0.96,
        best_ask_no=0.97,
        timestamp_utc=datetime.now(timezone.utc),
    )


def make_observation(side: str = "Under") -> MarketObservation:
    token_id = "under-token" if side == "Under" else "over-token"
    return MarketObservation(
        timestamp_utc=datetime.now(timezone.utc),
        event_id="296790",
        event_slug="j1100-cer-kyo-2026-04-18-more-markets",
        event_title="Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        market_id="1674823",
        market_slug="j1100-cer-kyo-2026-04-18-ou-3pt5",
        question="Cerezo Osaka vs Kyoto Sanga FC: O/U 3.5",
        token_id=token_id,
        side=side,
        price=0.97 if side == "Under" else 0.03,
        bid=0.96 if side == "Under" else 0.02,
        ask=0.97 if side == "Under" else 0.03,
        spread=0.01,
        sport="soccer",
        live=True,
        ended=False,
        score="1-0",
        period="2H",
        elapsed=78.0,
        market_type="total",
        total_line=3.5,
        total_selected_side_type="under" if side == "Under" else "over",
        total_goals=1,
        total_goal_buffer=2.5,
        reason="trade_eligible_price_held",
    )


def make_live_state() -> LiveState:
    raw = fixture_row(78)
    return LiveState(
        slug="cerezo-osaka-vs-kyoto-sanga-fc",
        sport="soccer",
        live=True,
        ended=False,
        score="1-0",
        period="2H",
        elapsed=78.0,
        last_update=datetime.now(timezone.utc),
        raw=raw,
    )


def test_runtime_enters_for_stable_low_pressure_under_market(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    common_events = [
        {"time": {"elapsed": 12, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}}
    ]
    write_detail(
        store,
        elapsed=58,
        home_stats={"shots": 1, "shots_on_target": 1, "corners": 0, "dangerous_attacks": 6, "attacks": 12},
        away_stats={"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 2, "attacks": 6},
        events=common_events,
    )
    write_detail(
        store,
        elapsed=63,
        home_stats={"shots": 2, "shots_on_target": 1, "corners": 0, "dangerous_attacks": 8, "attacks": 14},
        away_stats={"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 3, "attacks": 8},
        events=common_events,
    )
    write_detail(
        store,
        elapsed=68,
        home_stats={"shots": 3, "shots_on_target": 1, "corners": 0, "dangerous_attacks": 10, "attacks": 18},
        away_stats={"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 4, "attacks": 10},
        events=common_events,
    )
    write_detail(
        store,
        elapsed=73,
        home_stats={"shots": 4, "shots_on_target": 1, "corners": 0, "dangerous_attacks": 12, "attacks": 20},
        away_stats={"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 5, "attacks": 12},
        events=common_events,
    )
    write_detail(
        store,
        elapsed=78,
        home_stats={"shots": 5, "shots_on_target": 1, "corners": 0, "dangerous_attacks": 14, "attacks": 24},
        away_stats={"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 6, "attacks": 14},
        events=common_events,
    )

    runtime = GoalTotalsUnderRuntime({"goal_totals_under": {"enabled": True, "history_limit": 16}}, store)
    result = runtime.evaluate(make_market(), make_observation("Under"), make_live_state())
    assert result.applies is True
    assert result.enter is True
    assert result.reason == "goal_totals_under_enter"
    assert result.payload is not None
    assert result.payload.stable_for_2_snapshots is True
    assert result.payload.minute == 78.0
    assert result.payload.goal_buffer == 2.5


def test_runtime_rejects_over_side_with_reason(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    write_detail(
        store,
        elapsed=78,
        home_stats={"shots": 4, "shots_on_target": 1, "corners": 1, "dangerous_attacks": 12, "attacks": 24},
        away_stats={"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 6, "attacks": 14},
        events=[{"time": {"elapsed": 12, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}}],
    )

    runtime = GoalTotalsUnderRuntime({"goal_totals_under": {"enabled": True, "history_limit": 16}}, store)
    result = runtime.evaluate(make_market(), make_observation("Over"), make_live_state())
    assert result.applies is True
    assert result.enter is False
    assert result.reason == "goal_totals_under_wrong_side"


def test_runtime_blocks_when_detail_history_missing(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    runtime = GoalTotalsUnderRuntime({"goal_totals_under": {"enabled": True, "history_limit": 16}}, store)
    result = runtime.evaluate(make_market(), make_observation("Under"), make_live_state())
    assert result.applies is True
    assert result.enter is False
    assert result.reason == "goal_totals_under_missing_detail_history"


def test_runtime_skips_non_totals_market(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    runtime = GoalTotalsUnderRuntime({"goal_totals_under": {"enabled": True, "history_limit": 16}}, store)
    market = make_market("Will Cerezo Osaka win on 2026-04-18?")
    result = runtime.evaluate(market, make_observation("Under"), make_live_state())
    assert result.applies is False
    assert result.enter is False
