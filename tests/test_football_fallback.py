from __future__ import annotations

from app.live_state.football_fallback import live_state_from_fixture


def test_live_state_from_api_football_fixture() -> None:
    row = {
        "fixture": {"status": {"short": "2H", "elapsed": 76}},
        "teams": {"home": {"name": "Liverpool"}, "away": {"name": "Paris Saint Germain"}},
        "goals": {"home": 1, "away": 0},
    }
    state = live_state_from_fixture(row)
    assert state is not None
    assert state.sport == "soccer"
    assert state.live is True
    assert state.period == "2H"
    assert state.elapsed == 76
    assert state.score == "1-0"
