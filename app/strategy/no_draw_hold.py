from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.normalize.models import MarketObservation

WaitTier = tuple[float, float, float]


class NoDrawScoreHold:
    def __init__(
        self,
        path: Path,
        min_hold_seconds: float,
        max_elapsed_for_hold: float | None = None,
        wait_tiers: list[WaitTier] | None = None,
    ) -> None:
        self.path = path
        self.min_hold_seconds = min_hold_seconds
        self.max_elapsed_for_hold = max_elapsed_for_hold
        self.wait_tiers = wait_tiers or []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state: dict[str, dict[str, object]] = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding="utf-8") or "{}")

    def save(self) -> None:
        self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def check(self, obs: MarketObservation) -> tuple[bool, str]:
        if not is_no_draw_no(obs):
            return True, "no_draw_score_hold_not_applicable"
        score = _parse_score(obs.score)
        if score is None:
            return False, "no_draw_score_hold_missing_score"
        if abs(score[0] - score[1]) < 2:
            return False, "no_draw_score_hold_margin_too_small"
        if self.max_elapsed_for_hold is not None and obs.elapsed is not None and obs.elapsed > self.max_elapsed_for_hold:
            return True, "no_draw_score_hold_elapsed_above_max"

        now = datetime.now(timezone.utc)
        key = self.key(obs)
        existing = self.state.get(key)
        if not existing:
            wait_seconds = self.wait_seconds(obs.elapsed)
            if wait_seconds <= 0:
                return True, "no_draw_score_hold_no_wait_tier"
            self.state[key] = {
                "first_seen_at": now.isoformat(),
                "last_seen_at": now.isoformat(),
                "score": obs.score,
                "elapsed": obs.elapsed,
                "wait_seconds": wait_seconds,
            }
            return False, "waiting_no_draw_score_hold_first_seen"

        first_seen = datetime.fromisoformat(str(existing["first_seen_at"]))
        held_seconds = (now - first_seen).total_seconds()
        wait_seconds = float(existing.get("wait_seconds") or self.wait_seconds(obs.elapsed))
        if wait_seconds <= 0:
            return True, "no_draw_score_hold_no_wait_tier"
        existing["last_seen_at"] = now.isoformat()
        existing["elapsed"] = obs.elapsed
        self.state[key] = existing
        if held_seconds >= wait_seconds:
            return True, f"no_draw_score_held_{held_seconds:.1f}s"
        return False, f"waiting_no_draw_score_hold_{held_seconds:.1f}s"

    def wait_seconds(self, elapsed: float | None) -> float:
        if elapsed is None:
            return self.min_hold_seconds
        for min_elapsed, max_elapsed, wait_seconds in self.wait_tiers:
            if min_elapsed <= elapsed < max_elapsed:
                return wait_seconds
        return self.min_hold_seconds

    @staticmethod
    def key(obs: MarketObservation) -> str:
        return "|".join([obs.event_id, obs.market_id, obs.token_id, obs.side, obs.score or ""])


def parse_wait_tiers(raw: object) -> list[WaitTier]:
    if not isinstance(raw, list):
        return []
    tiers: list[WaitTier] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            min_elapsed = float(item["min_elapsed"])
            max_elapsed = float(item["max_elapsed"])
            wait_seconds = float(item["wait_seconds"])
        except (KeyError, TypeError, ValueError):
            continue
        tiers.append((min_elapsed, max_elapsed, wait_seconds))
    return tiers


def is_no_draw_no(obs: MarketObservation) -> bool:
    return str(obs.side or "").lower() == "no" and "draw" in str(obs.question or "").lower()


def _parse_score(score: str) -> tuple[int, int] | None:
    match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", score or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))
