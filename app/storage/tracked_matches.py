from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class TrackedMatches:
    def __init__(self, path: Path, *, pregame_minutes: int = 30, retain_hours_after_start: int = 4) -> None:
        self.path = path
        self.pregame_minutes = pregame_minutes
        self.retain_hours_after_start = retain_hours_after_start
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        events = payload.get("events", []) if isinstance(payload, dict) else []
        return [event for event in events if isinstance(event, dict)]

    def save(self, events: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps({"events": events}, ensure_ascii=False), encoding="utf-8")

    def update_from_discovery(self, events: list[dict[str, Any]], *, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        merged: dict[str, dict[str, Any]] = {event_key(event): event for event in self.load() if event_key(event)}
        for event in events:
            key = event_key(event)
            if not key:
                continue
            start = event_start(event)
            if start is None:
                continue
            minutes_to_start = (start - now).total_seconds() / 60
            if 0 <= minutes_to_start <= self.pregame_minutes:
                merged[key] = event
            elif key in merged:
                merged[key] = event
        retained = [
            event
            for event in merged.values()
            if should_retain(event, now=now, retain_hours_after_start=self.retain_hours_after_start)
        ]
        retained.sort(key=lambda event: event_start(event) or datetime.max.replace(tzinfo=timezone.utc))
        self.save(retained)
        return retained


def event_key(event: dict[str, Any]) -> str:
    return str(event.get("id") or event.get("slug") or "")


def event_start(event: dict[str, Any]) -> datetime | None:
    value = str(event.get("startTime") or event.get("startDate") or event.get("start_time") or "")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def should_retain(event: dict[str, Any], *, now: datetime, retain_hours_after_start: int) -> bool:
    start = event_start(event)
    if start is None:
        return True
    return now <= start + timedelta(hours=retain_hours_after_start)


def merge_tracked_events(events: list[dict[str, Any]], tracked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for event in tracked + events:
        key = event_key(event)
        if key:
            merged[key] = event
    return list(merged.values())
