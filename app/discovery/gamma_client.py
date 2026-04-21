from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


class GammaClient:
    def __init__(self, settings: dict[str, Any], raw_dir: Path) -> None:
        self.base_url = settings["api"]["gamma_base_url"].rstrip("/")
        self.timeout = settings["api"]["timeout_seconds"]
        self.retries = settings["api"]["retries"]
        self.backoff = settings["api"]["retry_backoff_seconds"]
        self.discovery = settings["discovery"]
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def fetch_events_page(self, *, tag_slug: str, offset: int, limit: int) -> list[dict[str, Any]]:
        params = {
            "active": "true",
            "closed": "false",
            "tag_slug": tag_slug,
            "related_tags": "true",
            "limit": limit,
            "offset": offset,
            "order": "updatedAt",
            "ascending": "false",
        }
        return self._get_list("/events", params)

    def fetch_all_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tag in self.discovery["event_tags"]:
            for page in range(int(self.discovery["max_pages_per_tag"])):
                offset = page * int(self.discovery["page_size"])
                page_events = self.fetch_events_page(tag_slug=tag, offset=offset, limit=int(self.discovery["page_size"]))
                self._persist_raw(f"events_{tag}_{page}", page_events)
                for event in page_events:
                    event_id = str(event.get("id") or event.get("slug") or "")
                    if event_id and event_id in seen:
                        continue
                    if event_id:
                        seen.add(event_id)
                    events.append(event)
        return events

    def fetch_markets_page(self, *, offset: int, limit: int) -> list[dict[str, Any]]:
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "offset": offset,
            "order": "updatedAt",
            "ascending": "false",
        }
        return self._get_list("/markets", params)

    def fetch_all_markets(self) -> list[dict[str, Any]]:
        markets: list[dict[str, Any]] = []
        seen: set[str] = set()
        for page in range(int(self.discovery["max_market_pages"])):
            offset = page * int(self.discovery["market_page_size"])
            page_markets = self.fetch_markets_page(offset=offset, limit=int(self.discovery["market_page_size"]))
            self._persist_raw(f"markets_{page}", page_markets)
            for market in page_markets:
                market_id = str(market.get("id") or market.get("conditionId") or market.get("slug") or "")
                if market_id and market_id in seen:
                    continue
                if market_id:
                    seen.add(market_id)
                markets.append(market)
        return markets

    def public_search(self, query: str) -> list[dict[str, Any]]:
        payload = self._request("/public-search", {"q": query})
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ["events", "markets", "results"]:
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        raise ValueError(f"Expected list/search object from /public-search, got {type(payload).__name__}")

    def fetch_events_by_slug(self, slug: str) -> list[dict[str, Any]]:
        return self._get_list("/events", {"slug": slug, "active": "true", "closed": "false"})

    def fetch_event_by_slug_path(self, slug: str) -> dict[str, Any] | None:
        try:
            return self._get_object(f"/events/slug/{slug}", {})
        except Exception:
            return None

    def fetch_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        try:
            return self._get_object(f"/events/{event_id}", {})
        except Exception:
            return None

    def fetch_markets_by_slug(self, slug: str) -> list[dict[str, Any]]:
        return self._get_list("/markets", {"slug": slug, "active": "true", "closed": "false"})

    def fetch_market(self, market_id: str) -> dict[str, Any]:
        return self._get_object(f"/markets/{market_id}", {})

    def _get_list(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        payload = self._request(path, params)
        if not isinstance(payload, list):
            raise ValueError(f"Expected list from {path}, got {type(payload).__name__}")
        return payload

    def _get_object(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = self._request(path, params)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected dict from {path}, got {type(payload).__name__}")
        return payload

    def _request(self, path: str, params: dict[str, Any]) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(f"{self.base_url}{path}", params=params)
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.backoff * attempt)
        raise RuntimeError(f"Gamma request failed {path}: {last_exc}")

    def _persist_raw(self, prefix: str, payload: Any) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = self.raw_dir / f"{stamp}_{prefix}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
