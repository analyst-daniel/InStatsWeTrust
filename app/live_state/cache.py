from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.normalize.models import LiveState


class LiveStateCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._states: dict[str, LiveState] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        self._states = {slug: LiveState.model_validate(data) for slug, data in payload.items()}

    def save(self) -> None:
        payload = {slug: state.model_dump(mode="json") for slug, state in self._states.items()}
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def upsert_from_message(self, message: dict) -> None:
        event_state = message.get("eventState") if isinstance(message.get("eventState"), dict) else {}
        slug = str(message.get("slug") or message.get("eventSlug") or message.get("gameSlug") or event_state.get("slug") or "")
        if not slug:
            title = str(message.get("title") or message.get("eventTitle") or event_state.get("title") or "")
            if not title:
                home = str(message.get("homeTeam") or event_state.get("homeTeam") or "")
                away = str(message.get("awayTeam") or event_state.get("awayTeam") or "")
                if home and away:
                    title = f"{home} vs {away}"
            slug = slugify(title)
        if not slug:
            return
        period = str(event_state.get("period") or message.get("period") or message.get("phase") or "")
        elapsed = parse_elapsed(
            event_state.get("elapsed")
            or event_state.get("minute")
            or event_state.get("clock")
            or message.get("elapsed")
            or message.get("minute")
            or message.get("clock")
        )
        if elapsed is None and period.upper() in {"HT", "HALFTIME"}:
            elapsed = 45.0
        state = LiveState(
            slug=slug,
            sport=str(event_state.get("type") or message.get("sport") or message.get("type") or ""),
            live=bool(event_state.get("live") or message.get("live") or message.get("isLive") or message.get("status") in {"live", "inprogress"}),
            ended=bool(event_state.get("ended") or message.get("ended") or message.get("isEnded") or message.get("status") in {"final", "ended"}),
            score=str(event_state.get("score") or message.get("score") or message.get("homeScore", "")),
            period=period,
            elapsed=elapsed,
            last_update=datetime.now(timezone.utc),
            raw=message,
        )
        self._states[slug] = state

    def get(self, slug: str) -> LiveState | None:
        if slug in self._states:
            return self._states[slug]
        normalized = slugify(slug)
        return self._states.get(normalized)

    def all(self) -> list[LiveState]:
        return list(self._states.values())


def parse_elapsed(value) -> float | None:
    try:
        if value in ("", None):
            return None
        text = str(value).replace("'", "")
        return float(text)
    except (TypeError, ValueError):
        return None


def slugify(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
