from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.live_state.cache import LiveStateCache, slugify
from app.live_state.matcher import LiveStateMatcher
from app.normalize.normalizer import normalize_events
from app.utils.config import resolve_path


def load_discovery_events(settings: dict) -> list[dict[str, Any]]:
    path = resolve_path(settings["storage"]["discovery_cache_json"])
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    events = payload.get("events", [])
    return events if isinstance(events, list) else []


def build_bet_label(question: str, side: str) -> str:
    spread = re.search(r"Spread:\s*(.+?)\s*\(([+-]?\d+(?:\.\d+)?)\)", question, re.IGNORECASE)
    if spread:
        listed_team = spread.group(1).strip()
        line = float(spread.group(2))
        signed = line if normalize_name(side) == normalize_name(listed_team) else -line
        return f"{side} {signed:+g}"

    total = re.search(r"O/U\s*(\d+(?:\.\d+)?)", question, re.IGNORECASE)
    if total and side.lower() in {"over", "under"}:
        return f"{side} {total.group(1)}"
    return side


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def is_soccer_event(event: dict[str, Any]) -> bool:
    text = " ".join(str(v).lower() for v in [event.get("title"), event.get("name"), event.get("slug"), event.get("category"), event.get("tags")])
    if any(term in text for term in ["tennis", "nba", "nfl", "nhl", "mlb", "cricket", "dota", "lol", "league of legends", "esports", "e-sports", "counter-strike", "valorant"]):
        return False
    title = str(event.get("title") or event.get("name") or "")
    return any(term in text for term in ["soccer", "football", " fc", "cf ", "uefa", "fifa", "liga"]) or bool(re.search(r"\b[a-z .'-]+fc\b.+\bvs\.?\b.+\b[a-z .'-]+fc\b", title.lower()))


def event_title(event: dict[str, Any]) -> str:
    return str(event.get("title") or event.get("name") or event.get("slug") or "")


def market_type_counts(markets: pd.DataFrame) -> dict[str, int]:
    if markets.empty:
        return {"market_count": 0, "spread": 0, "total": 0, "match": 0}
    questions = markets["question"].astype(str).str.lower()
    return {
        "market_count": len(markets),
        "spread": int(questions.str.contains("spread|handicap", regex=True).sum()),
        "total": int(questions.str.contains("o/u|over|under", regex=True).sum()),
        "match": int(questions.str.contains("will .* win|draw", regex=True).sum()),
    }


LEAGUE_BY_SLUG_PREFIX = {
    "ucl": "UEFA Champions League",
    "uel": "UEFA Europa League",
    "col": "UEFA Conference League",
    "epl": "English Premier League",
    "elc": "English Championship",
    "el1": "English League One",
    "el2": "English League Two",
    "lal": "La Liga",
    "sea": "Serie A",
    "bun": "Bundesliga",
    "lig1": "Ligue 1",
    "por": "Portugal",
    "spl": "Saudi Pro League",
    "sud": "Copa Sudamericana",
    "bra": "Brazil",
}


def league_from_event(event: dict[str, Any], live_state: Any | None) -> tuple[str, str]:
    if live_state is not None and isinstance(live_state.raw, dict):
        league = live_state.raw.get("league")
        if isinstance(league, dict):
            name = str(league.get("name") or "")
            country = str(league.get("country") or "")
            if name and country:
                return f"{name} ({country})", "sports_api"
            if name:
                return name, "sports_api"

    slug = str(event.get("slug") or "")
    prefix = slug.split("-", 1)[0].lower()
    if prefix in LEAGUE_BY_SLUG_PREFIX:
        return LEAGUE_BY_SLUG_PREFIX[prefix], "polymarket_slug"

    category = str(event.get("category") or "")
    if category:
        return category, "polymarket_category"

    return "", ""


def build_match_overview(settings: dict, events: list[dict[str, Any]], snapshots: pd.DataFrame) -> pd.DataFrame:
    markets = normalize_events(events)
    market_rows = pd.DataFrame([m.model_dump(mode="json") for m in markets])
    first_market_by_event: dict[str, Any] = {}
    for market in markets:
        first_market_by_event.setdefault(str(market.event_id), market)
    cache = LiveStateCache(resolve_path(settings["storage"]["live_state_json"]))
    matcher = LiveStateMatcher(cache, max_age_seconds=int(settings.get("dashboard", {}).get("live_state_max_age_seconds", 900)))
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []

    for event in events:
        if not is_soccer_event(event):
            continue
        title = event_title(event)
        event_id = str(event.get("id") or event.get("slug") or "")
        event_slug = str(event.get("slug") or "")
        event_markets = market_rows[market_rows["event_id"].astype(str) == event_id] if not market_rows.empty else pd.DataFrame()
        live_state = None
        if not event_markets.empty:
            first_market = first_market_by_event.get(event_id)
            live_state = matcher.match(first_market) if first_market else None
        if live_state is None:
            live_state = cache.get(event_slug) or cache.get(slugify(title))
        live_age = live_state_age_seconds(live_state.last_update) if live_state else None
        if live_state and live_age > int(settings.get("dashboard", {}).get("live_state_max_age_seconds", 900)):
            live_state = None
            live_age = None

        league, league_source = league_from_event(event, live_state)
        start = parse_dt(str(event.get("startTime") or event.get("startDate") or event.get("start_time") or ""))
        counts = market_type_counts(event_markets)
        event_snaps = snapshots[snapshots["event_id"].astype(str) == event_id] if not snapshots.empty and "event_id" in snapshots else pd.DataFrame()
        latest_candidate = ""
        candidate_count = 0
        if not event_snaps.empty:
            latest = event_snaps.sort_values("timestamp_utc", ascending=False).iloc[0]
            latest_candidate = f"{latest.get('side', '')} @ {latest.get('price', '')} | {latest.get('question', '')}"
            candidate_count = len(event_snaps.drop_duplicates(subset=["market_id", "token_id", "side"]))

        rows.append(
            {
                "event_id": event_id,
                "event_title": title,
                "league": league,
                "league_source": league_source,
                "event_slug": event_slug,
                "start_time_utc": start.isoformat() if start else "",
                "start_date_utc": start.strftime("%Y-%m-%d") if start else "",
                "minutes_to_start": round((start - now).total_seconds() / 60, 1) if start else "",
                "live": bool(live_state.live) if live_state else False,
                "ended": bool(live_state.ended) if live_state else False,
                "confirmed_by_sports_api": live_state is not None,
                "score": live_state.score if live_state else "",
                "period": live_state.period if live_state else "",
                "match_minute": display_minute(live_state.period, live_state.elapsed) if live_state else None,
                "live_update_age_sec": round(live_age, 0) if live_age is not None else "",
                "market_count": counts["market_count"],
                "spread_markets": counts["spread"],
                "total_markets": counts["total"],
                "match_markets": counts["match"],
                "candidate_count_95_99": candidate_count,
                "latest_candidate": latest_candidate,
            }
        )
    return pd.DataFrame(rows)


def filter_snapshots(settings: dict, snapshots: pd.DataFrame) -> pd.DataFrame:
    if snapshots.empty:
        return snapshots
    out = snapshots.copy()
    if "live" in out:
        out = out[(out["live"] == 1) | (out["live"] == True)]
    if "ended" in out:
        out = out[(out["ended"] == 0) | (out["ended"] == False)]
    if "sport" in out:
        out = out[out["sport"].astype(str).str.lower() == "soccer"]
    if "reason" in out:
        out = out[~out["reason"].astype(str).str.contains("wrong_sport", case=False, na=False)]
    today_utc = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if "timestamp_utc" in out:
        ts = pd.to_datetime(out["timestamp_utc"], utc=True, errors="coerce")
        now = pd.Timestamp.utcnow()
        max_age = int(settings.get("dashboard", {}).get("snapshot_max_age_seconds", 300))
        out = out[(ts.dt.strftime("%Y-%m-%d") == today_utc) & ((now - ts).dt.total_seconds() <= max_age)]
    date_text = out.get("event_title", "").astype(str) + " " + out.get("question", "").astype(str)
    extracted_dates = date_text.str.findall(r"20\d{2}-\d{2}-\d{2}")
    return out[extracted_dates.map(lambda values: not values or max(values) >= today_utc)]


def live_state_age_seconds(value: datetime | str) -> float:
    parsed = parse_dt(value) if isinstance(value, str) else value
    if parsed is None:
        return 999999.0
    return (datetime.now(timezone.utc) - parsed).total_seconds()


def display_minute(period: str, elapsed: float | None) -> float | None:
    if elapsed is not None:
        return elapsed
    if str(period).upper() in {"HT", "HALFTIME"}:
        return 45.0
    return None
