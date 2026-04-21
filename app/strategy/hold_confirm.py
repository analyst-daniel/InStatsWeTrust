from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.normalize.models import MarketObservation


class HoldConfirmation:
    def __init__(self, path: Path, min_hold_seconds: float) -> None:
        self.path = path
        self.min_hold_seconds = min_hold_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state: dict[str, dict[str, object]] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding="utf-8") or "{}")

    def save(self) -> None:
        self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def check(self, obs: MarketObservation) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        key = self.key(obs)
        existing = self.state.get(key)
        if not existing:
            self.state[key] = {
                "first_seen_at": now.isoformat(),
                "last_seen_at": now.isoformat(),
                "first_price": obs.price,
                "last_price": obs.price,
            }
            return False, "waiting_price_hold_first_seen"

        first_seen = datetime.fromisoformat(str(existing["first_seen_at"]))
        held_seconds = (now - first_seen).total_seconds()
        existing["last_seen_at"] = now.isoformat()
        existing["last_price"] = obs.price
        self.state[key] = existing
        if held_seconds >= self.min_hold_seconds:
            return True, f"price_held_{held_seconds:.1f}s"
        return False, f"waiting_price_hold_{held_seconds:.1f}s"

    @staticmethod
    def key(obs: MarketObservation) -> str:
        return "|".join([obs.event_id, obs.market_id, obs.token_id, obs.side])
