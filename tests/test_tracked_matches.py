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
