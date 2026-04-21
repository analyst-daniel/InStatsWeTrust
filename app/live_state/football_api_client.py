from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


class FootballApiBudget:
    def __init__(self, path: Path, daily_limit: int) -> None:
        self.path = path
        self.daily_limit = daily_limit
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def can_spend(self) -> bool:
        return self.used_today() < self.daily_limit

    def spend(self) -> None:
        payload = self._load()
        day = today()
        payload.setdefault(day, 0)
        payload[day] += 1
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def used_today(self) -> int:
        return int(self._load().get(today(), 0))

    def _load(self) -> dict[str, int]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8") or "{}")


class FootballApiClient:
    def __init__(self, settings: dict[str, Any], budget_path: Path) -> None:
        cfg = settings.get("football_api", {})
        self.enabled = bool(cfg.get("enabled", False))
        self.base_url = str(cfg.get("base_url", "https://v3.football.api-sports.io")).rstrip("/")
        self.api_key_env = str(cfg.get("api_key_env", "APISPORTS_KEY"))
        self.timeout = int(settings["api"].get("timeout_seconds", 15))
        self.budget = FootballApiBudget(budget_path, int(cfg.get("daily_request_limit", 100)))

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "")

    def fixtures_live(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        payload = self._get("/fixtures", {"live": "all"})
        rows = payload.get("response", [])
        return rows if isinstance(rows, list) else []

    def fixture_statistics(self, fixture_id: int | str) -> list[dict[str, Any]]:
        payload = self._get("/fixtures/statistics", {"fixture": fixture_id})
        rows = payload.get("response", [])
        return rows if isinstance(rows, list) else []

    def fixture_events(self, fixture_id: int | str) -> list[dict[str, Any]]:
        payload = self._get("/fixtures/events", {"fixture": fixture_id})
        rows = payload.get("response", [])
        return rows if isinstance(rows, list) else []

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError(f"Missing API key env var {self.api_key_env}")
        if not self.budget.can_spend():
            raise RuntimeError("Football API daily request limit reached")
        self.budget.spend()
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}{endpoint}", params=params, headers={"x-apisports-key": self.api_key})
            response.raise_for_status()
            payload = response.json()
        return payload if isinstance(payload, dict) else {}


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
