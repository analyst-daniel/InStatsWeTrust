from datetime import datetime, timedelta, timezone

from app.live_state.football_research import (
    FootballResearchStore,
    capture_proof_of_winning_details,
    fixture_elapsed,
    fixture_id_from_row,
    fixture_title,
    is_live_soccer_fixture,
)
from app.storage.tracked_matches import TrackedMatches


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


def test_research_store_resolves_fixture_id_by_event_title_and_team_overlap(tmp_path) -> None:
    store = FootballResearchStore(
        manifest_path=tmp_path / "manifest.json",
        raw_dir=tmp_path / "raw",
    )
    store.write_fixture_detail(
        "99999",
        event_title="Granada CF vs. Almeria",
        fixture_payload={
            "fixture": {"id": 99999, "status": {"short": "2H", "elapsed": 78}},
            "teams": {"home": {"name": "Granada CF"}, "away": {"name": "Almeria"}},
            "league": {"name": "La Liga 2", "sport": "Football"},
        },
        statistics=[],
        events=[],
    )
    assert store.resolve_fixture_id(event_title="Granada CF vs. UD Almería - More Markets") == "99999"
    assert store.resolve_fixture_id(teams=["Granada CF", "UD Almería"]) == "99999"


def test_research_store_falls_back_to_live_snapshot_when_manifest_missing(tmp_path) -> None:
    store = FootballResearchStore(
        manifest_path=tmp_path / "manifest.json",
        raw_dir=tmp_path / "raw",
    )
    store.append_fixtures_live_snapshot(
        [
            {
                "fixture": {"id": 88888, "status": {"short": "2H", "elapsed": 81}},
                "teams": {"home": {"name": "VfB Stuttgart"}, "away": {"name": "Werder Bremen"}},
                "league": {"name": "Bundesliga", "sport": "Football"},
            }
        ]
    )
    assert store.resolve_fixture_id(event_title="VfB Stuttgart vs. SV Werder Bremen - More Markets") == "88888"
    assert store.resolve_fixture_id(teams=["VfB Stuttgart", "SV Werder Bremen"]) == "88888"


def test_research_store_does_not_false_match_generic_team_tokens(tmp_path) -> None:
    store = FootballResearchStore(
        manifest_path=tmp_path / "manifest.json",
        raw_dir=tmp_path / "raw",
    )
    store.append_fixtures_live_snapshot(
        [
            {
                "fixture": {"id": 1522096, "status": {"short": "1H", "elapsed": 26}},
                "teams": {"home": {"name": "North Geelong Warriors"}, "away": {"name": "Brunswick City"}},
                "league": {"name": "Victoria NPL 2", "sport": "Football"},
            }
        ]
    )
    assert store.resolve_fixture_id(
        event_title="North Carolina Courage vs. Kansas City Current - More Markets",
        teams=["North Carolina Courage", "Kansas City Current"],
    ) == ""


def test_capture_uses_priority_minute_floor_for_tracked_match(tmp_path) -> None:
    class FakeClient:
        def fixture_statistics(self, fixture_id):
            return []

        def fixture_events(self, fixture_id):
            return []

    store = FootballResearchStore(
        manifest_path=tmp_path / "manifest.json",
        raw_dir=tmp_path / "raw",
    )
    tracked = TrackedMatches(tmp_path / "tracked.json")
    tracked.save(
        [
            {
                "id": "1",
                "slug": "cerezo-kyoto",
                "title": "Cerezo Osaka vs. Kyoto Sanga FC - More Markets",
            }
        ]
    )
    settings = {
        "football_api": {
            "detail_capture_enabled": True,
            "detail_capture_minute_floor": 70,
            "detail_capture_priority_minute_floor": 60,
            "detail_capture_poll_interval_seconds": 30,
        }
    }
    captured = capture_proof_of_winning_details(
        settings,
        FakeClient(),
        store,
        [fixture_row(elapsed=64)],
        tracked_matches=tracked,
    )
    assert captured == 1


def test_capture_keeps_default_floor_for_untracked_match(tmp_path) -> None:
    class FakeClient:
        def fixture_statistics(self, fixture_id):
            return []

        def fixture_events(self, fixture_id):
            return []

    store = FootballResearchStore(
        manifest_path=tmp_path / "manifest.json",
        raw_dir=tmp_path / "raw",
    )
    settings = {
        "football_api": {
            "detail_capture_enabled": True,
            "detail_capture_minute_floor": 70,
            "detail_capture_priority_minute_floor": 60,
            "detail_capture_poll_interval_seconds": 30,
        }
    }
    captured = capture_proof_of_winning_details(
        settings,
        FakeClient(),
        store,
        [fixture_row(elapsed=64)],
    )
    assert captured == 0
