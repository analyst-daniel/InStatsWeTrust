from __future__ import annotations

from datetime import datetime, timezone

from app.live_state.football_research import FootballResearchStore
from app.normalize.models import LiveState, MarketObservation, NormalizedMarket
from app.strategy.proof_of_winning_runtime import ProofOfWinningRuntime


def fixture_row(elapsed: int, home_goals: int = 2, away_goals: int = 0) -> dict:
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
        {"type": "Corner Kicks", "value": values.get("corners", 0)},
        {"type": "Dangerous Attacks", "value": values.get("dangerous_attacks", 0)},
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


def make_market(question: str = "Will Cerezo Osaka win on 2026-04-18?") -> NormalizedMarket:
    return NormalizedMarket(
        event_id="296790",
        event_slug="j1100-cer-kyo-2026-04-18-more-markets",
        event_title="Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        market_id="1674823",
        market_slug="j1100-cer-kyo-2026-04-18-cerezo-win",
        question=question,
        sport="soccer",
        category="sports",
        teams=["Cerezo Osaka", "Kyoto Sanga FC"],
        active=True,
        closed=False,
        token_ids=["yes-token", "no-token"],
        yes_token_id="yes-token",
        no_token_id="no-token",
        outcomes=["Yes", "No"],
        best_bid_yes=0.96,
        best_ask_yes=0.97,
        best_bid_no=0.03,
        best_ask_no=0.04,
        timestamp_utc=datetime.now(timezone.utc),
    )


def make_observation(side: str = "Yes") -> MarketObservation:
    return MarketObservation(
        timestamp_utc=datetime.now(timezone.utc),
        event_id="296790",
        event_slug="j1100-cer-kyo-2026-04-18-more-markets",
        event_title="Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        market_id="1674823",
        market_slug="j1100-cer-kyo-2026-04-18-cerezo-win",
        question="Will Cerezo Osaka win on 2026-04-18?",
        token_id="yes-token" if side == "Yes" else "no-token",
        side=side,
        price=0.97,
        bid=0.96,
        ask=0.97,
        spread=0.01,
        sport="soccer",
        live=True,
        ended=False,
        score="2-0",
        period="2H",
        elapsed=78.0,
        reason="trade_eligible_price_held",
    )


def make_live_state() -> LiveState:
    raw = fixture_row(78)
    return LiveState(
        slug="cerezo-osaka-vs-kyoto-sanga-fc",
        sport="soccer",
        live=True,
        ended=False,
        score="2-0",
        period="2H",
        elapsed=78.0,
        last_update=datetime.now(timezone.utc),
        raw=raw,
    )


def test_runtime_enters_for_stable_low_pressure_winner_market(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    write_detail(
        store,
        elapsed=65,
        home_stats={"shots": 8, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 22},
        away_stats={"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 5},
        events=[
            {"time": {"elapsed": 31, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
            {"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
        ],
    )
    write_detail(
        store,
        elapsed=70,
        home_stats={"shots": 9, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 24},
        away_stats={"shots": 2, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 7},
        events=[
            {"time": {"elapsed": 31, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
            {"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
        ],
    )
    write_detail(
        store,
        elapsed=75,
        home_stats={"shots": 9, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 25},
        away_stats={"shots": 3, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 8},
        events=[
            {"time": {"elapsed": 31, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
            {"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
        ],
    )
    write_detail(
        store,
        elapsed=76,
        home_stats={"shots": 9, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 25},
        away_stats={"shots": 3, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 8},
        events=[
            {"time": {"elapsed": 31, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
            {"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
        ],
    )
    write_detail(
        store,
        elapsed=78,
        home_stats={"shots": 10, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 26},
        away_stats={"shots": 3, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 8},
        events=[
            {"time": {"elapsed": 31, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
            {"time": {"elapsed": 60, "extra": None}, "type": "Goal", "detail": "Normal Goal", "team": {"name": "Cerezo Osaka"}},
        ],
    )
    runtime = ProofOfWinningRuntime({"proof_of_winning": {"enabled": True, "history_limit": 16}}, store)
    result = runtime.evaluate(make_market(), make_observation("Yes"), make_live_state())
    assert result.applies is True
    assert result.enter is True
    assert result.reason == "proof_of_winning_enter"
    assert result.payload is not None
    assert result.payload.stable_for_2_snapshots is True
    assert result.payload.minute == 78.0
    assert result.payload.goal_difference == 2


def test_runtime_blocks_when_detail_history_missing(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    runtime = ProofOfWinningRuntime({"proof_of_winning": {"enabled": True, "history_limit": 16}}, store)
    result = runtime.evaluate(make_market(), make_observation("Yes"), make_live_state())
    assert result.applies is True
    assert result.enter is False
    assert result.reason == "proof_of_winning_missing_detail_history"


def test_runtime_skips_non_match_market(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    runtime = ProofOfWinningRuntime({"proof_of_winning": {"enabled": True, "history_limit": 16}}, store)
    market = make_market("Cerezo Osaka vs Kyoto Sanga FC: O/U 4.5")
    result = runtime.evaluate(market, make_observation("Under"), make_live_state())
    assert result.applies is False
    assert result.enter is False
