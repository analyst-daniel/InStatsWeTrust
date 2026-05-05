from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.storage.tracked_matches import TrackedMatches, merge_tracked_events


def event(event_id: str, start: datetime) -> dict:
    return {
        "id": event_id,
        "slug": f"event-{event_id}",
        "title": f"Team {event_id} FC vs. Other FC",
        "startDate": start.isoformat(),
        "markets": [],
    }


def test_tracks_polymarket_event_inside_30_minute_window(tmp_path) -> None:
    now = datetime(2026, 4, 21, 18, 0, tzinfo=timezone.utc)
    tracker = TrackedMatches(tmp_path / "tracked.json", pregame_minutes=30)

    tracked = tracker.update_from_discovery(
        [
            event("too_late", now + timedelta(minutes=45)),
            event("watch", now + timedelta(minutes=20)),
        ],
        now=now,
    )

    assert [row["id"] for row in tracked] == ["watch"]


def test_keeps_tracked_event_after_kickoff(tmp_path) -> None:
    now = datetime(2026, 4, 21, 18, 0, tzinfo=timezone.utc)
    tracker = TrackedMatches(tmp_path / "tracked.json", pregame_minutes=30)
    tracker.update_from_discovery([event("watch", now + timedelta(minutes=10))], now=now)

    retained = tracker.update_from_discovery([], now=now + timedelta(minutes=75))

    assert [row["id"] for row in retained] == ["watch"]


def test_merge_tracked_events_prefers_fresh_discovery_payload() -> None:
    tracked = [{"id": "1", "title": "Old", "markets": []}]
    fresh = [{"id": "1", "title": "Fresh", "markets": [{"id": "m1"}]}]

    merged = merge_tracked_events(fresh, tracked)

    assert len(merged) == 1
    assert merged[0]["title"] == "Fresh"


def test_attach_fixture_mapping_updates_existing_tracked_event(tmp_path) -> None:
    now = datetime(2026, 4, 21, 18, 0, tzinfo=timezone.utc)
    tracker = TrackedMatches(tmp_path / "tracked.json", pregame_minutes=30)
    tracker.update_from_discovery([event("watch", now + timedelta(minutes=10))], now=now)

    changed = tracker.attach_fixture_mapping(
        event_id="watch",
        event_slug="event-watch",
        event_title="Team watch FC vs. Other FC",
        fixture_id="12345",
        live_slug="team-watch-fc-vs-other-fc",
    )

    assert changed is True
    assert tracker.resolve_fixture_id(event_id="watch") == "12345"
    payload = tracker.load()[0]
    assert payload["live_slug"] == "team-watch-fc-vs-other-fc"


def test_attach_fixture_mapping_creates_minimal_row_when_event_not_tracked(tmp_path) -> None:
    tracker = TrackedMatches(tmp_path / "tracked.json", pregame_minutes=30)

    changed = tracker.attach_fixture_mapping(
        event_id="296790",
        event_slug="j1100-cer-kyo-2026-04-18-more-markets",
        event_title="Cerezo Osaka vs Kyoto Sanga FC - More Markets",
        fixture_id="12345",
        live_slug="cerezo-osaka-vs-kyoto-sanga-fc",
    )

    assert changed is True
    assert tracker.resolve_fixture_id(event_id="296790") == "12345"
    payload = tracker.load()[0]
    assert payload["slug"] == "j1100-cer-kyo-2026-04-18-more-markets"
    assert payload["fixture_id"] == "12345"


def test_load_recovers_first_json_object_when_file_has_extra_data(tmp_path) -> None:
    tracker = TrackedMatches(tmp_path / "tracked.json", pregame_minutes=30)
    tracker.path.write_text(
        '{"events":[{"id":"1","slug":"event-1","title":"One"}]}{"events":[{"id":"2"}]}',
        encoding="utf-8",
    )

    rows = tracker.load()

    assert len(rows) == 1
    assert rows[0]["id"] == "1"
