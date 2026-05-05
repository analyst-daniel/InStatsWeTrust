from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.live_state.cache import LiveStateCache, slugify
from app.live_state.football_api_client import FootballApiClient
from app.live_state.football_research import FootballResearchStore, capture_proof_of_winning_details
from app.normalize.models import LiveState
from app.storage.tracked_matches import TrackedMatches
from app.utils.config import resolve_path


def update_live_state_from_football_api(settings: dict[str, Any], cache: LiveStateCache, budget_path: Path) -> tuple[int, int, int]:
    client = FootballApiClient(settings, budget_path)
    fixtures = client.fixtures_live()
    raw_dir = resolve_path(settings["storage"]["raw_dir"])
    manifest_path = resolve_path(settings["storage"]["football_research_manifest_json"])
    tracked_matches = TrackedMatches(resolve_path(settings["storage"]["tracked_matches_json"]))
    research_store = FootballResearchStore(raw_dir=raw_dir, manifest_path=manifest_path)
    research_store.append_fixtures_live_snapshot(fixtures)
    updated = 0
    with_elapsed = 0
    for fixture in fixtures:
        state = live_state_from_fixture(fixture)
        if not state:
            continue
        cache._states[state.slug] = state
        updated += 1
        if state.elapsed is not None:
            with_elapsed += 1
    max_age = int(settings.get("dashboard", {}).get("live_state_max_age_seconds", 180))
    now = datetime.now(timezone.utc)
    cache._states = {
        slug: state
        for slug, state in cache._states.items()
        if (now - state.last_update).total_seconds() <= max_age
    }
    cache.save()
    captured = capture_proof_of_winning_details(settings, client, research_store, fixtures, tracked_matches=tracked_matches)
    return updated, with_elapsed, captured


def live_state_from_fixture(row: dict[str, Any]) -> LiveState | None:
    fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
    teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
    goals = row.get("goals") if isinstance(row.get("goals"), dict) else {}
    status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
    home = ((teams.get("home") or {}).get("name") if isinstance(teams.get("home"), dict) else "") or ""
    away = ((teams.get("away") or {}).get("name") if isinstance(teams.get("away"), dict) else "") or ""
    if not home or not away:
        return None
    elapsed = as_float(status.get("elapsed"))
    short = str(status.get("short") or "")
    long = str(status.get("long") or "")
    live = short in {"1H", "2H", "ET", "BT", "P", "LIVE", "HT"} or long.lower() in {"first half", "second half", "halftime"}
    ended = short in {"FT", "AET", "PEN"}
    if elapsed is None and short.upper() == "HT":
        elapsed = 45.0
    score = f"{goals.get('home', '')}-{goals.get('away', '')}"
    return LiveState(
        slug=slugify(f"{home} vs {away}"),
        sport="soccer",
        live=live,
        ended=ended,
        score=score,
        period=short,
        elapsed=elapsed,
        last_update=datetime.now(timezone.utc),
        raw=row,
    )


def as_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
