from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DiscoveryCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        events = payload.get("events", [])
        return events if isinstance(events, list) else []

    def save(self, events: list[dict[str, Any]]) -> None:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "events": events,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
