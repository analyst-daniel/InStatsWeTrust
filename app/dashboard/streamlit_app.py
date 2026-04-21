from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.live_state.cache import LiveStateCache, slugify
from app.live_state.matcher import LiveStateMatcher
from app.normalize.normalizer import normalize_events
from app.utils.config import load_settings, resolve_path


st.set_page_config(page_title="Polymarket Self Hosted", layout="wide")
st.markdown("<meta http-equiv='refresh' content='60'>", unsafe_allow_html=True)
st.title("Polymarket Self Hosted")

settings = load_settings()
db_path = resolve_path(settings["storage"]["sqlite_path"])


@st.cache_data(ttl=10)
def read_table(name: str) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    with sqlite3.connect(db_path) as conn:
        try:
            return pd.read_sql_query(f"SELECT * FROM {name}", conn)
        except Exception:
            return pd.DataFrame()


@st.cache_data(ttl=10)
def load_discovery_events() -> list[dict[str, Any]]:
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


def build_match_overview(events: list[dict[str, Any]], snapshots: pd.DataFrame) -> pd.DataFrame:
    markets = normalize_events(events)
    market_rows = pd.DataFrame([m.model_dump(mode="json") for m in markets])
    cache = LiveStateCache(resolve_path(settings["storage"]["live_state_json"]))
    matcher = LiveStateMatcher(cache, max_age_seconds=int(settings.get("dashboard", {}).get("live_state_max_age_seconds", 300)))
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
            live_state = matcher.match(normalize_events([event])[0])
        if live_state is None:
            live_state = cache.get(event_slug) or cache.get(slugify(title))
        live_age = live_state_age_seconds(live_state.last_update) if live_state else None
        if live_state and live_age > int(settings.get("dashboard", {}).get("live_state_max_age_seconds", 900)):
            live_state = None
            live_age = None
        confirmed_live_state = live_state is not None

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
                "event_title": title,
                "event_slug": event_slug,
                "start_time_utc": start.isoformat() if start else "",
                "start_date_utc": start.strftime("%Y-%m-%d") if start else "",
                "minutes_to_start": round((start - now).total_seconds() / 60, 1) if start else "",
                "live": bool(live_state.live) if live_state else False,
                "ended": bool(live_state.ended) if live_state else False,
                "confirmed_by_sports_api": confirmed_live_state,
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


def live_state_age_seconds(value: datetime | str) -> float:
    if isinstance(value, str):
        parsed = parse_dt(value)
    else:
        parsed = value
    if parsed is None:
        return 999999.0
    return (datetime.now(timezone.utc) - parsed).total_seconds()


def display_minute(period: str, elapsed: float | None) -> float | None:
    if elapsed is not None:
        return elapsed
    if str(period).upper() in {"HT", "HALFTIME"}:
        return 45.0
    return None


def filter_snapshots(snapshots: pd.DataFrame) -> pd.DataFrame:
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


snapshots = filter_snapshots(read_table("snapshots"))
trades = read_table("trades")
events = load_discovery_events()
matches = build_match_overview(events, snapshots) if events else pd.DataFrame()
if not matches.empty:
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    matches = matches[(matches["start_date_utc"].eq("")) | (matches["start_date_utc"] >= today_utc)]
    if settings.get("dashboard", {}).get("require_fresh_live_state_for_live_sections", True):
        live_mask = matches["live"] == True
        matches = matches[(~live_mask) | (matches["confirmed_by_sports_api"] == True)]

open_trades = trades[trades["status"] == "open"].copy() if not trades.empty and "status" in trades else pd.DataFrame()
if not open_trades.empty and settings.get("dashboard", {}).get("show_only_today_open_trades", True):
    entry_ts = pd.to_datetime(open_trades["entry_timestamp"], utc=True, errors="coerce")
    open_trades = open_trades[entry_ts.dt.strftime("%Y-%m-%d") == datetime.now(timezone.utc).strftime("%Y-%m-%d")]
resolved_trades = trades[trades["status"] != "open"] if not trades.empty and "status" in trades else pd.DataFrame()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Polymarket Soccer Matches", len(matches))
col2.metric("Open Paper Trades", len(open_trades))
col3.metric("Live 75+", len(matches[(matches["live"] == True) & (pd.to_numeric(matches["match_minute"], errors="coerce") >= 75)]) if not matches.empty else 0)
col4.metric("Resolved", len(resolved_trades))

st.subheader("Open Paper Trades")
if open_trades.empty:
    st.info("No open paper trades.")
else:
    open_trades["bet_label"] = open_trades.apply(lambda row: build_bet_label(str(row["question"]), str(row["side"])), axis=1)
    st.dataframe(
        open_trades[
            [
                "entry_timestamp",
                "event_title",
                "question",
                "bet_label",
                "side",
                "entry_price",
                "stake_usd",
                "shares",
                "elapsed",
                "score",
                "period",
                "first_hit_99_at",
                "first_hit_999_at",
                "max_favorable_price",
                "status",
            ]
        ].sort_values("entry_timestamp", ascending=False),
        use_container_width=True,
    )

st.subheader("Live Matches 75+")
if matches.empty:
    st.info("No Polymarket soccer matches in discovery cache.")
else:
    live75 = matches[(matches["live"] == True) & (matches["ended"] == False) & (pd.to_numeric(matches["match_minute"], errors="coerce") >= 75)]
    live75 = live75.sort_values("match_minute", ascending=False)
    st.dataframe(live75, use_container_width=True)

st.subheader("Live Matches Started")
if matches.empty:
    st.info("No rows.")
else:
    started = matches[(matches["live"] == True) & (matches["ended"] == False) & (pd.to_numeric(matches["match_minute"], errors="coerce") < 75)]
    started = started.sort_values("match_minute", ascending=False)
    st.dataframe(started, use_container_width=True)

st.subheader("Pregame Watchlist: Polymarket Matches Starting In Next 30 Minutes")
if matches.empty:
    st.info("No rows.")
else:
    minutes = pd.to_numeric(matches["minutes_to_start"], errors="coerce")
    pregame = matches[(matches["live"] == False) & (minutes >= 0) & (minutes <= 30)]
    pregame = pregame.sort_values("minutes_to_start", ascending=True)
    st.dataframe(pregame, use_container_width=True)

st.subheader("Current Live Price Candidates 0.95-0.99")
if snapshots.empty:
    st.info("No live soccer price candidates.")
else:
    latest = snapshots.sort_values("timestamp_utc", ascending=False).drop_duplicates(subset=["event_id", "market_id", "token_id", "side"], keep="first").head(200)
    latest = latest.copy()
    latest["match_minute"] = pd.to_numeric(latest["elapsed"], errors="coerce").round(1)
    latest["bet_label"] = latest.apply(lambda row: build_bet_label(str(row["question"]), str(row["side"])), axis=1)
    st.dataframe(
        latest[
            [
                "timestamp_utc",
                "event_title",
                "question",
                "bet_label",
                "side",
                "price",
                "bid",
                "ask",
                "spread",
                "score",
                "period",
                "match_minute",
                "reason",
            ]
        ],
        use_container_width=True,
    )

st.subheader("Daily Reports")
daily_dir = resolve_path(settings["storage"].get("daily_dir", "data/daily"))
if daily_dir.exists():
    reports = sorted(daily_dir.glob("summary_*.md"), reverse=True)
    if reports:
        selected = st.selectbox("Summary file", [path.name for path in reports])
        st.markdown((daily_dir / selected).read_text(encoding="utf-8"))
    else:
        st.info("No daily summaries yet.")
else:
    st.info("Daily report folder does not exist yet.")
