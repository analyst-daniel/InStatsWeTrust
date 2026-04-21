from __future__ import annotations

from datetime import datetime, timezone

from app.live_state.football_research import FootballResearchStore
from app.normalize.models import LiveState, MarketObservation, NormalizedMarket
from app.strategy.spread_confirmation_runtime import SpreadConfirmationRuntime


def fixture_row(elapsed: int, home_goals: int = 1, away_goals: int = 0) -> dict:
    return {
        "fixture": {"id": 12345, "status": {"short": "2H", "elapsed": elapsed}},
        "teams": {"home": {"name": "Iwaki FC"}, "away": {"name": "AC Nagano Parceiro"}},
        "goals": {"home": home_goals, "away": away_goals},
        "league": {"name": "J2/J3 League", "sport": "Football"},
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
    home_goals: int,
    away_goals: int,
    home_stats: dict,
    away_stats: dict,
    events: list[dict] | None = None,
) -> None:
    store.write_fixture_detail(
        "12345",
        event_title="Iwaki FC vs. AC Nagano Parceiro",
        fixture_payload=fixture_row(elapsed, home_goals, away_goals),
        statistics=[
            {"team": {"name": "Iwaki FC"}, "statistics": stats_payload(home_stats)},
            {"team": {"name": "AC Nagano Parceiro"}, "statistics": stats_payload(away_stats)},
        ],
        events=events or [],
    )


def make_market(question: str, market_slug: str = "j2-iwa-nag-2026-04-19-spread-home-2pt5") -> NormalizedMarket:
    return NormalizedMarket(
        event_id="296790",
        event_slug="j2-iwa-nag-2026-04-19-more-markets",
        event_title="Iwaki FC vs. AC Nagano Parceiro - More Markets",
        market_id="1674823",
        market_slug=market_slug,
        question=question,
        sport="soccer",
        category="sports",
        teams=["Iwaki FC", "AC Nagano Parceiro"],
        active=True,
        closed=False,
        token_ids=["yes-token", "no-token"],
        yes_token_id="yes-token",
        no_token_id="no-token",
        outcomes=["Iwaki FC", "AC Nagano Parceiro"],
        best_bid_yes=0.95,
        best_ask_yes=0.96,
        best_bid_no=0.98,
        best_ask_no=0.99,
        timestamp_utc=datetime.now(timezone.utc),
    )


def make_observation(question: str, side: str, price: float = 0.98) -> MarketObservation:
    return MarketObservation(
        timestamp_utc=datetime.now(timezone.utc),
        event_id="296790",
        event_slug="j2-iwa-nag-2026-04-19-more-markets",
        event_title="Iwaki FC vs. AC Nagano Parceiro - More Markets",
        market_id="1674823",
        market_slug="j2-iwa-nag-2026-04-19-spread-home-2pt5",
        question=question,
        token_id="yes-token" if side == "Iwaki FC" else "no-token",
        side=side,
        price=price,
        bid=max(price - 0.01, 0),
        ask=price,
        spread=0.01,
        sport="soccer",
        live=True,
        ended=False,
        score="1-0",
        period="2H",
        elapsed=81.0,
        market_type="spread",
        reason="trade_eligible",
    )


def make_live_state() -> LiveState:
    raw = fixture_row(81, 1, 0)
    return LiveState(
        slug="iwaki-fc-vs-ac-nagano-parceiro",
        sport="soccer",
        live=True,
        ended=False,
        score="1-0",
        period="2H",
        elapsed=81.0,
        last_update=datetime.now(timezone.utc),
        raw=raw,
    )


def test_runtime_blocks_minus_2_5_when_margin_is_only_one_goal(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    write_detail(
        store,
        elapsed=71,
        home_goals=1,
        away_goals=0,
        home_stats={"shots": 8, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 18},
        away_stats={"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 4},
    )
    write_detail(
        store,
        elapsed=76,
        home_goals=1,
        away_goals=0,
        home_stats={"shots": 9, "shots_on_target": 4, "corners": 3, "dangerous_attacks": 20},
        away_stats={"shots": 1, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 4},
    )
    write_detail(
        store,
        elapsed=81,
        home_goals=1,
        away_goals=0,
        home_stats={"shots": 10, "shots_on_target": 5, "corners": 4, "dangerous_attacks": 22},
        away_stats={"shots": 2, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 5},
    )
    runtime = SpreadConfirmationRuntime({"spread_confirmation": {"enabled": True, "history_limit": 16}}, store)
    result = runtime.evaluate(
        make_market("Spread: Iwaki FC (-2.5)"),
        make_observation("Spread: Iwaki FC (-2.5)", "Iwaki FC", 0.96),
        make_live_state(),
    )
    assert result.applies is True
    assert result.enter is False
    assert result.reason == "spread_minus_margin_too_small"


def test_runtime_allows_plus_1_5_when_underdog_is_alive_and_stable(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    write_detail(
        store,
        elapsed=66,
        home_goals=1,
        away_goals=0,
        home_stats={"shots": 6, "shots_on_target": 3, "corners": 2, "dangerous_attacks": 14},
        away_stats={"shots": 2, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 6},
    )
    write_detail(
        store,
        elapsed=71,
        home_goals=1,
        away_goals=0,
        home_stats={"shots": 7, "shots_on_target": 3, "corners": 2, "dangerous_attacks": 16},
        away_stats={"shots": 3, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 7},
    )
    write_detail(
        store,
        elapsed=76,
        home_goals=1,
        away_goals=0,
        home_stats={"shots": 8, "shots_on_target": 3, "corners": 2, "dangerous_attacks": 17},
        away_stats={"shots": 4, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 8},
    )
    write_detail(
        store,
        elapsed=81,
        home_goals=1,
        away_goals=0,
        home_stats={"shots": 9, "shots_on_target": 3, "corners": 2, "dangerous_attacks": 18},
        away_stats={"shots": 4, "shots_on_target": 0, "corners": 1, "dangerous_attacks": 9},
    )
    runtime = SpreadConfirmationRuntime({"spread_confirmation": {"enabled": True, "history_limit": 16}}, store)
    result = runtime.evaluate(
        make_market("Spread: Iwaki FC (-1.5)"),
        make_observation("Spread: Iwaki FC (-1.5)", "AC Nagano Parceiro", 0.98),
        make_live_state(),
    )
    assert result.applies is True
    assert result.enter is True
    assert result.reason == "spread_plus_enter"
    assert result.payload is not None
    assert result.payload.stable_for_2_snapshots is True
