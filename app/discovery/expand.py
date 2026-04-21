from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from app.discovery.gamma_client import GammaClient
from app.live_state.cache import LiveStateCache


def expand_events_to_all_markets(
    client: GammaClient,
    events: list[dict[str, Any]],
    live_cache: LiveStateCache,
    *,
    limit: int,
    pregame_window_minutes: int,
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    seen_events: set[str] = set()
    detail_count = 0

    for event in sorted(events, key=event_sort_key):
        merged = deepcopy(event)
        if should_expand_event(event, live_cache, pregame_window_minutes) and detail_count < limit:
            detail_count += 1
            merged = merge_event_details(client, merged)
        key = event_key(merged)
        if key not in seen_events:
            expanded.append(merged)
            seen_events.add(key)

    return expanded


def merge_event_details(client: GammaClient, event: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(event)
    for detail in fetch_detail_variants(client, event):
        merged = merge_event(merged, detail)
    return merged


def fetch_detail_variants(client: GammaClient, event: dict[str, Any]) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    event_id = str(event.get("id") or "")
    slug = str(event.get("slug") or "")
    slugs = slug_variants(slug)

    if event_id:
        detail = client.fetch_event_by_id(event_id)
        if detail:
            variants.append(detail)

    for candidate_slug in slugs:
        variants.extend(client.fetch_events_by_slug(candidate_slug))
        path_detail = client.fetch_event_by_slug_path(candidate_slug)
        if path_detail:
            variants.append(path_detail)

        # Some Gamma deployments expose more-market slugs only through markets.
        # Wrap standalone markets back into an event-shaped object.
        markets = client.fetch_markets_by_slug(candidate_slug)
        if markets:
            variants.append({**event, "slug": candidate_slug, "markets": markets})

    return variants


def merge_event(base: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    if not detail:
        return base
    merged = {**base, **{k: v for k, v in detail.items() if v not in (None, "", [])}}
    markets = []
    seen: set[str] = set()
    for source in [base.get("markets"), detail.get("markets")]:
        if not isinstance(source, list):
            continue
        for market in source:
            if not isinstance(market, dict):
                continue
            key = str(market.get("id") or market.get("conditionId") or market.get("slug") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            markets.append(market)
    merged["markets"] = markets
    return merged


def should_expand_event(event: dict[str, Any], live_cache: LiveStateCache, pregame_window_minutes: int) -> bool:
    if not is_soccerish(event):
        return False
    slug = str(event.get("slug") or "")
    title = str(event.get("title") or event.get("name") or "")
    if live_cache.get(slug) or live_cache.get(slugify(title)):
        return True

    start = parse_datetime(str(event.get("startTime") or event.get("startDate") or event.get("start_time") or ""))
    if start is None:
        return " vs" in title.lower() or "@" in title
    now = datetime.now(timezone.utc)
    return now - timedelta(minutes=15) <= start <= now + timedelta(minutes=pregame_window_minutes)


def slug_variants(slug: str) -> list[str]:
    if not slug:
        return []
    variants = [slug]
    if not slug.endswith("-more-markets"):
        variants.append(f"{slug}-more-markets")
    simplified = re.sub(r"-202\d-\d\d-\d\d.*$", "", slug)
    if simplified and simplified != slug:
        variants.append(f"{simplified}-more-markets")
    return list(dict.fromkeys(variants))


def is_soccerish(event: dict[str, Any]) -> bool:
    text = " ".join(str(v).lower() for v in [event.get("title"), event.get("name"), event.get("slug"), event.get("category"), event.get("tags")])
    bad = ["tennis", "nba", "nfl", "nhl", "mlb", "cricket", "dota", "league of legends"]
    if any(term in text for term in bad):
        return False
    return any(term in text for term in ["soccer", "football", " fc", "cf ", "uefa", "fifa", "liga", " vs"])


def event_sort_key(event: dict[str, Any]) -> tuple[str, str]:
    return (str(event.get("startTime") or event.get("startDate") or event.get("endDate") or ""), str(event.get("title") or event.get("slug") or ""))


def event_key(event: dict[str, Any]) -> str:
    return str(event.get("id") or event.get("slug") or event.get("title") or "")


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
