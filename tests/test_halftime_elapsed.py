from __future__ import annotations

from app.live_state.football_fallback import live_state_from_fixture


def test_halftime_without_elapsed_is_45() -> None:
    row = {
        "fixture": {"status": {"short": "HT", "elapsed": None}},
        "teams": {"home": {"name": "AZ Alkmaar"}, "away": {"name": "Shakhtar Donetsk"}},
        "goals": {"home": 0, "away": 0},
    }
    state = live_state_from_fixture(row)
    assert state is not None
    assert state.period == "HT"
    assert state.elapsed == 45.0
