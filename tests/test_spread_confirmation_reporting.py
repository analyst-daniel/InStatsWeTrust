from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.live_state.cache import LiveStateCache
from app.live_state.football_research import FootballResearchStore
from app.live_state.matcher import LiveStateMatcher
from app.normalize.models import LiveState, NormalizedMarket
from app.strategy.spread_confirmation_reporting import build_spread_debug_rows
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


def write_detail(store: FootballResearchStore, elapsed: int, home_goals: int, away_goals: int) -> None:
    store.write_fixture_detail(
        "12345",
        event_title="Iwaki FC vs. AC Nagano Parceiro",
        fixture_payload=fixture_row(elapsed, home_goals, away_goals),
        statistics=[
            {"team": {"name": "Iwaki FC"}, "statistics": stats_payload({"shots": 10, "shots_on_target": 5, "corners": 4, "dangerous_attacks": 22})},
            {"team": {"name": "AC Nagano Parceiro"}, "statistics": stats_payload({"shots": 2, "shots_on_target": 0, "corners": 0, "dangerous_attacks": 5})},
        ],
        events=[],
    )


def test_build_spread_debug_rows_exposes_decision_context(tmp_path) -> None:
    store = FootballResearchStore(tmp_path / "manifest.json", tmp_path / "raw")
    write_detail(store, 71, 1, 0)
    write_detail(store, 76, 1, 0)
    write_detail(store, 81, 1, 0)
    live_cache = LiveStateCache(tmp_path / "live_state.json")
    live_state = LiveState(
        slug="iwaki-fc-vs-ac-nagano-parceiro",
        sport="soccer",
        live=True,
        ended=False,
        score="1-0",
        period="2H",
        elapsed=81.0,
        last_update=datetime.now(timezone.utc),
        raw=fixture_row(81, 1, 0),
    )
    live_cache._states[live_state.slug] = live_state
    live_cache.save()
    matcher = LiveStateMatcher(live_cache, max_age_seconds=90)
    runtime = SpreadConfirmationRuntime({"spread_confirmation": {"enabled": True, "history_limit": 16}}, store)
    market = NormalizedMarket(
        event_id="296790",
        event_slug="j2-iwa-nag-2026-04-19-more-markets",
        event_title="Iwaki FC vs. AC Nagano Parceiro - More Markets",
        market_id="1674823",
        market_slug="j2-iwa-nag-2026-04-19-spread-home-2pt5",
        question="Spread: Iwaki FC (-2.5)",
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
    latest = pd.DataFrame(
        [
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "event_id": "296790",
                "event_slug": "j2-iwa-nag-2026-04-19-more-markets",
                "event_title": "Iwaki FC vs. AC Nagano Parceiro - More Markets",
                "market_id": "1674823",
                "market_slug": "j2-iwa-nag-2026-04-19-spread-home-2pt5",
                "question": "Spread: Iwaki FC (-2.5)",
                "token_id": "yes-token",
                "side": "Iwaki FC",
                "price": 0.96,
                "bid": 0.95,
                "ask": 0.96,
                "spread": 0.01,
                "liquidity": 1000,
                "last_trade_price": 0.96,
                "sport": "soccer",
                "live": 1,
                "ended": 0,
                "score": "1-0",
                "period": "2H",
                "elapsed": 81.0,
                "market_type": "spread",
                "spread_listed_team": "Iwaki FC",
                "spread_listed_line": -2.5,
                "spread_listed_side_type": "minus",
                "spread_selected_team": "Iwaki FC",
                "spread_selected_line": -2.5,
                "spread_selected_side_type": "minus",
                "reason": "price_in_target_range",
            }
        ]
    )
    rows = build_spread_debug_rows(
        latest,
        {(market.event_id, market.market_id): market},
        matcher,
        runtime,
        parse_dt=lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
        to_float=float,
        to_optional_float=lambda value: None if value in ("", None) else float(value),
        to_bool=bool,
    )
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["final_decision"] == "NO ENTER"
    assert row["rejection_reason"] == "spread_minus_margin_too_small"
    assert row["spread_line"] == -2.5
    assert row["spread_side_type"] == "minus"
    assert row["selected_team_margin"] == 1
