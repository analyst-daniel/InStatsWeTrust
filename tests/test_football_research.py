from datetime import datetime, timedelta, timezone

from app.live_state.football_research import (
    FootballResearchStore,
    fixture_elapsed,
    fixture_id_from_row,
    fixture_title,
    is_live_soccer_fixture,
)


def fixture_row(short: str = "2H", elapsed: int = 78) -> dict:
    return {
        "fixture": {"id": 12345, "status": {"short": short, "elapsed": elapsed}},
        "teams": {"home": {"name": "Cerezo Osaka"}, "away": {"name": "Kyoto Sanga FC"}},
        "league": {"name": "J1 League", "sport": "Football"},
    }


def test_fixture_helpers_extract_expected_fields() -> None:
    row = fixture_row()
    assert fixture_id_from_row(row) == "12345"
    assert fixture_elapsed(row) == 78.0
    assert fixture_title(row) == "Cerezo Osaka vs. Kyoto Sanga FC"
    assert is_live_soccer_fixture(row) is True


def test_non_live_fixture_is_not_selected() -> None:
    row = fixture_row(short="FT", elapsed=90)
    assert is_live_soccer_fixture(row) is False


def test_research_store_refresh_guard(tmp_path) -> None:
    store = FootballResearchStore(
        manifest_path=tmp_path / "manifest.json",
        raw_dir=tmp_path / "raw",
    )
    assert store.should_refresh_fixture("12345", 30) is True
    store.write_fixture_detail(
        "12345",
        event_title="Cerezo Osaka vs. Kyoto Sanga FC",
        fixture_payload=fixture_row(),
        statistics=[],
        events=[],
    )
    assert store.should_refresh_fixture("12345", 30) is False
