from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
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
        raw = self.path.read_text(encoding="utf-8", errors="replace")
        payload = decode_tracked_payload(raw)
        events = payload.get("events", []) if isinstance(payload, dict) else []
        return [event for event in events if isinstance(event, dict)]

    def save(self, events: list[dict[str, Any]]) -> None:
        payload = json.dumps({"events": events}, ensure_ascii=False)
        last_error: Exception | None = None
        for _ in range(4):
            temp_path = None
            try:
                with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(self.path.parent)) as handle:
                    handle.write(payload)
                    temp_path = Path(handle.name)
                temp_path.replace(self.path)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.1)
            finally:
                if temp_path is not None and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
        if last_error is not None:
            raise last_error

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

    def resolve_fixture_id(self, *, event_id: str = "", event_slug: str = "", event_title: str = "") -> str:
        wanted_id = str(event_id or "")
        wanted_slug = str(event_slug or "")
        wanted_title = normalize_event_title(event_title)
        slug_match = ""
        title_match = ""
        for event in self.load():
            if wanted_id and str(event.get("id") or "") == wanted_id:
                fixture_id = str(event.get("fixture_id") or "")
                if fixture_id:
                    return fixture_id
            if wanted_slug and str(event.get("slug") or "") == wanted_slug:
                fixture_id = str(event.get("fixture_id") or "")
                if fixture_id and not slug_match:
                    slug_match = fixture_id
            if wanted_title and normalize_event_title(str(event.get("title") or "")) == wanted_title:
                fixture_id = str(event.get("fixture_id") or "")
                if fixture_id and not title_match:
                    title_match = fixture_id
        return slug_match or title_match or ""

    def attach_fixture_mapping(
        self,
        *,
        event_id: str = "",
        event_slug: str = "",
        event_title: str = "",
        fixture_id: str = "",
        live_slug: str = "",
        mapping_confidence: str = "live_state",
        mapped_at: datetime | None = None,
    ) -> bool:
        fixture_id = str(fixture_id or "")
        if not fixture_id:
            return False
        mapped_at = mapped_at or datetime.now(timezone.utc)
        wanted_id = str(event_id or "")
        wanted_slug = str(event_slug or "")
        wanted_title = normalize_event_title(event_title)
        events = self.load()
        changed = False
        matched = False
        for event in events:
            if wanted_id and str(event.get("id") or "") == wanted_id:
                matched = True
                changed = update_mapping_row(event, fixture_id, live_slug, mapping_confidence, mapped_at) or changed
                continue
            if wanted_slug and str(event.get("slug") or "") == wanted_slug:
                matched = True
                changed = update_mapping_row(event, fixture_id, live_slug, mapping_confidence, mapped_at) or changed
                continue
            if wanted_title and normalize_event_title(str(event.get("title") or "")) == wanted_title:
                matched = True
                changed = update_mapping_row(event, fixture_id, live_slug, mapping_confidence, mapped_at) or changed
        if not matched:
            new_event = {
                "id": wanted_id,
                "slug": wanted_slug,
                "title": event_title,
            }
            update_mapping_row(new_event, fixture_id, live_slug, mapping_confidence, mapped_at)
            events.append(new_event)
            changed = True
        if changed:
            try:
                self.save(events)
            except PermissionError:
                return False
        return changed


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


def update_mapping_row(
    event: dict[str, Any],
    fixture_id: str,
    live_slug: str,
    mapping_confidence: str,
    mapped_at: datetime,
) -> bool:
    before = (
        str(event.get("fixture_id") or ""),
        str(event.get("live_slug") or ""),
        str(event.get("mapping_confidence") or ""),
    )
    event["fixture_id"] = fixture_id
    if live_slug:
        event["live_slug"] = live_slug
    event["mapping_confidence"] = mapping_confidence
    event["mapped_at"] = mapped_at.isoformat()
    after = (
        str(event.get("fixture_id") or ""),
        str(event.get("live_slug") or ""),
        str(event.get("mapping_confidence") or ""),
    )
    return before != after


def normalize_event_title(value: str) -> str:
    cleaned = re.sub(r"\s+-\s+(more markets|exact score|halftime result).*$", "", str(value or ""), flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "", cleaned.lower())


def decode_tracked_payload(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        try:
            payload, _ = decoder.raw_decode(text)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}
