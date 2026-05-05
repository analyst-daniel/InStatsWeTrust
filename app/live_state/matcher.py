from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

from app.live_state.cache import LiveStateCache, slugify
from app.normalize.models import LiveState, NormalizedMarket


GENERIC_TEAM_TOKENS = {
    "cf",
    "club",
    "de",
    "fc",
    "la",
    "real",
    "sc",
    "the",
}


class LiveStateMatcher:
    def __init__(self, cache: LiveStateCache, max_age_seconds: int = 300) -> None:
        self.cache = cache
        self.max_age_seconds = max_age_seconds

    def match(self, market: NormalizedMarket) -> LiveState | None:
        candidates = [market.event_slug, market.market_slug, slugify(market.event_title)]
        for candidate in candidates:
            if not candidate:
                continue
            state = self.cache.get(candidate)
            if self._fresh(state) and self._date_compatible(market, state):
                return state
            state = self._slug_prefix_match(candidate)
            if self._fresh(state) and self._date_compatible(market, state):
                return state
        title_match = None if team_sides(market.event_title) else self._title_fallback(market.event_title)
        if title_match and self._date_compatible(market, title_match):
            return title_match
        team_match = self._team_overlap_fallback(market.event_title)
        return team_match if self._date_compatible(market, team_match, strict_when_market_has_date=True) else None

    def _slug_prefix_match(self, slug: str) -> LiveState | None:
        cleaned = re.sub(r"-(more-markets|spread|total|btts|exact-score).*$", "", slug)
        if cleaned != slug:
            state = self.cache.get(cleaned)
            if self._fresh(state):
                return state
        for state in self.cache.all():
            if self._fresh(state) and state.slug and (state.slug.startswith(cleaned) or cleaned.startswith(state.slug)):
                return state
        return None

    def _title_fallback(self, title: str) -> LiveState | None:
        wanted = slugify(title.replace("- More Markets", ""))
        best: tuple[float, LiveState | None] = (0.0, None)
        for state in self.cache.all():
            if not self._fresh(state):
                continue
            ratio = SequenceMatcher(None, wanted, state.slug).ratio()
            if ratio > best[0]:
                best = (ratio, state)
        return best[1] if best[0] >= 0.82 else None

    def _team_overlap_fallback(self, title: str) -> LiveState | None:
        wanted_sides = team_sides(title)
        if len(wanted_sides) != 2:
            return None
        best: tuple[int, LiveState | None] = (0, None)
        for state in self.cache.all():
            if not self._fresh(state):
                continue
            candidate_sides = state_team_sides(state)
            if len(candidate_sides) != 2:
                continue
            overlap_a = len(wanted_sides[0] & candidate_sides[0]) + len(wanted_sides[1] & candidate_sides[1])
            overlap_b = len(wanted_sides[0] & candidate_sides[1]) + len(wanted_sides[1] & candidate_sides[0])
            overlap = max(overlap_a, overlap_b)
            if min(max(len(wanted_sides[0] & candidate_sides[0]), len(wanted_sides[0] & candidate_sides[1])), max(len(wanted_sides[1] & candidate_sides[0]), len(wanted_sides[1] & candidate_sides[1]))) == 0:
                continue
            if overlap > best[0]:
                best = (overlap, state)
        return best[1] if best[0] >= 2 else None

    def _fresh(self, state: LiveState | None) -> bool:
        if state is None:
            return False
        return (datetime.now(timezone.utc) - state.last_update).total_seconds() <= self.max_age_seconds

    def _date_compatible(self, market: NormalizedMarket, state: LiveState | None, strict_when_market_has_date: bool = False) -> bool:
        if state is None:
            return False
        market_date = parse_date(market.start_time)
        state_date = state_start_date(state)
        if strict_when_market_has_date and market_date is not None and state_date is None:
            return False
        if market_date is None or state_date is None:
            return True
        return market_date == state_date


def team_tokens(value: str) -> set[str]:
    cleaned = re.sub(r"\b(exact|score|spread|total|more|markets|vs|v)\b", " ", value.lower())
    return {
        token
        for token in re.findall(r"[a-z0-9]+", cleaned)
        if len(token) >= 2 and token not in GENERIC_TEAM_TOKENS
    }


def team_sides(title: str) -> list[set[str]]:
    cleaned = re.sub(r"\s+-\s+(more markets|exact score).*$", "", title, flags=re.IGNORECASE)
    parts = re.split(r"\s+(?:vs\.?|v|@)\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return []
    return [team_tokens(parts[0]), team_tokens(parts[1])]


def state_team_sides(state: LiveState) -> list[set[str]]:
    if isinstance(state.raw, dict):
        teams = state.raw.get("teams")
        if isinstance(teams, dict):
            sides: list[set[str]] = []
            for side in ["home", "away"]:
                team = teams.get(side)
                if isinstance(team, dict):
                    sides.append(team_tokens(str(team.get("name") or "")))
            if len(sides) == 2 and all(sides):
                return sides
        home = str(state.raw.get("homeTeam") or "")
        away = str(state.raw.get("awayTeam") or "")
        if home and away:
            return [team_tokens(home), team_tokens(away)]
    return team_sides(state.slug.replace("-", " "))


def parse_date(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d")


def state_start_date(state: LiveState) -> str | None:
    if not isinstance(state.raw, dict):
        return None
    fixture = state.raw.get("fixture")
    if isinstance(fixture, dict):
        return parse_date(str(fixture.get("date") or ""))
    return None
