from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.discovery.gamma_client import GammaClient
from app.live_state.cache import LiveStateCache


def fetch_related_live_events(client: GammaClient, cache: LiveStateCache, *, limit: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    queries = live_soccer_queries(cache)[:limit]
    for query in queries:
        try:
            results = client.public_search(query)
        except Exception:
            continue
        for item in results:
            event = extract_event(item)
            if not event:
                continue
            text = json.dumps(event, ensure_ascii=False).lower()
            title = str(event.get("title") or event.get("eventTitle") or event.get("question") or "")
            is_match_event = " vs" in title.lower() or " v " in title.lower() or "@" in title
            if not is_match_event and "more markets" not in text and not any(term in text for term in ["spread", "o/u", "over", "under"]):
                continue
            event_id = str(event.get("id") or event.get("slug") or "")
            if event_id and event_id in seen:
                continue
            if event_id:
                seen.add(event_id)
            events.append(event)
    return events


def live_soccer_queries(cache: LiveStateCache) -> list[str]:
    queries: list[str] = []
    fresh_states = [
        state
        for state in cache.all()
        if state.sport.lower() == "soccer"
        and state.live
        and not state.ended
        and (datetime.now(timezone.utc) - state.last_update).total_seconds() <= 180
    ]
    fresh_states.sort(key=lambda state: state.last_update, reverse=True)
    for state in fresh_states:
        title = title_from_state(state.raw)
        if title:
            for variant in title_variants(title):
                queries.append(f"{variant} More Markets")
                queries.append(variant)
    return queries


def title_variants(title: str) -> list[str]:
    variants = [title]
    aliases = {
        "West Brom": "West Bromwich Albion",
        "QPR": "Queens Park Rangers",
    }
    for short, full in aliases.items():
        if short in title:
            variants.append(title.replace(short, full))
    seen: set[str] = set()
    unique: list[str] = []
    for variant in variants:
        if variant not in seen:
            seen.add(variant)
            unique.append(variant)
    return unique


def title_from_state(raw: dict[str, Any]) -> str:
    home = str(raw.get("homeTeam") or "")
    away = str(raw.get("awayTeam") or "")
    teams = raw.get("teams")
    if isinstance(teams, dict):
        home_team = teams.get("home")
        away_team = teams.get("away")
        if isinstance(home_team, dict):
            home = home or str(home_team.get("name") or "")
        if isinstance(away_team, dict):
            away = away or str(away_team.get("name") or "")
    if home and away:
        return f"{home} vs {away}"
    return ""


def extract_event(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    if isinstance(item.get("event"), dict):
        return item["event"]
    if isinstance(item.get("events"), list) and item["events"]:
        first = item["events"][0]
        return first if isinstance(first, dict) else None
    if item.get("markets") or item.get("title") or item.get("slug"):
        return item
    return None
