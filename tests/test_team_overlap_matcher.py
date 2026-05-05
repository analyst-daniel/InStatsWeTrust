from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.live_state.cache import LiveStateCache
from app.live_state.matcher import LiveStateMatcher
from app.normalize.models import LiveState, NormalizedMarket


def test_az_matches_az_alkmaar(tmp_path: Path) -> None:
    cache = LiveStateCache(tmp_path / "live.json")
    cache._states["az-alkmaar-vs-shakhtar-donetsk"] = LiveState(
        slug="az-alkmaar-vs-shakhtar-donetsk",
        sport="soccer",
        live=True,
        elapsed=44,
        last_update=datetime.now(timezone.utc),
        raw={"teams": {"home": {"name": "AZ Alkmaar"}, "away": {"name": "Shakhtar Donetsk"}}},
    )
    market = NormalizedMarket(
        event_id="e1",
        event_slug="col-az-shd-2026-04-16-more-markets",
        event_title="AZ vs. FK Shakhtar Donetsk - More Markets",
        market_id="m1",
        question="Spread: AZ (-2.5)",
        sport="soccer",
        token_ids=["a", "b"],
        yes_token_id="a",
        no_token_id="b",
        outcomes=["AZ", "FK Shakhtar Donetsk"],
        timestamp_utc=datetime.now(timezone.utc),
    )
    state = LiveStateMatcher(cache).match(market)
    assert state is not None
    assert state.elapsed == 44


def test_single_shared_team_does_not_match_different_fixture(tmp_path: Path) -> None:
    cache = LiveStateCache(tmp_path / "live.json")
    cache._states["celta-vigo-vs-sc-freiburg"] = LiveState(
        slug="celta-vigo-vs-sc-freiburg",
        sport="soccer",
        live=True,
        elapsed=54,
        score="0-3",
        last_update=datetime.now(timezone.utc),
        raw={
            "fixture": {"date": "2026-04-16T16:45:00+00:00"},
            "teams": {"home": {"name": "Celta Vigo"}, "away": {"name": "SC Freiburg"}},
        },
    )
    market = NormalizedMarket(
        event_id="e1",
        event_slug="lal-bar-cel-2026-04-22-exact-score",
        event_title="FC Barcelona vs. RC Celta de Vigo - Exact Score",
        market_id="m1",
        question="Exact Score: FC Barcelona 2 - 1 RC Celta de Vigo?",
        sport="soccer",
        token_ids=["a", "b"],
        yes_token_id="a",
        no_token_id="b",
        outcomes=["Yes", "No"],
        start_time="2026-04-22T19:00:00+00:00",
        timestamp_utc=datetime.now(timezone.utc),
    )
    assert LiveStateMatcher(cache).match(market) is None


def test_single_shared_team_without_state_date_does_not_match_future_market(tmp_path: Path) -> None:
    cache = LiveStateCache(tmp_path / "live.json")
    cache._states["az-vs-fk-shakhtar-donetsk"] = LiveState(
        slug="az-vs-fk-shakhtar-donetsk",
        sport="soccer",
        live=True,
        elapsed=70,
        score="0-1",
        last_update=datetime.now(timezone.utc),
        raw={"teams": {"home": {"name": "AZ"}, "away": {"name": "FK Shakhtar Donetsk"}}},
    )
    market = NormalizedMarket(
        event_id="e1",
        event_slug="ukr1-zor-shd-2026-04-23-more-markets",
        event_title="FK Zorya Luhansk vs. FK Shakhtar Donetsk - More Markets",
        market_id="m1",
        question="Spread: FK Shakhtar Donetsk (-2.5)",
        sport="soccer",
        token_ids=["a", "b"],
        yes_token_id="a",
        no_token_id="b",
        outcomes=["FK Zorya Luhansk", "FK Shakhtar Donetsk"],
        start_time="2026-04-23T12:30:00+00:00",
        timestamp_utc=datetime.now(timezone.utc),
    )
    assert LiveStateMatcher(cache).match(market) is None


def test_real_prefix_does_not_match_different_real_fixture(tmp_path: Path) -> None:
    cache = LiveStateCache(tmp_path / "live.json")
    cache._states["real-oviedo-vs-elche-cf"] = LiveState(
        slug="real-oviedo-vs-elche-cf",
        sport="soccer",
        live=True,
        elapsed=75,
        score="2-0",
        last_update=datetime.now(timezone.utc),
        raw={
            "fixture": {"date": "2026-05-03T10:00:00+00:00"},
            "teams": {"home": {"name": "Real Oviedo"}, "away": {"name": "Elche CF"}},
        },
    )
    market = NormalizedMarket(
        event_id="e1",
        event_slug="lal-bet-ovi-2026-05-03",
        event_title="Real Betis Balompie vs. Real Oviedo",
        market_id="m1",
        question="Will Real Betis Balompie vs. Real Oviedo end in a draw?",
        sport="soccer",
        token_ids=["a", "b"],
        yes_token_id="a",
        no_token_id="b",
        outcomes=["Yes", "No"],
        start_time="2026-05-03T19:00:00+00:00",
        timestamp_utc=datetime.now(timezone.utc),
    )
    assert LiveStateMatcher(cache).match(market) is None
