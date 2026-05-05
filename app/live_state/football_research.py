from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.live_state.football_api_client import FootballApiClient
from app.storage.tracked_matches import TrackedMatches


class FootballResearchStore:
    def __init__(self, manifest_path: Path, raw_dir: Path) -> None:
        self.manifest_path = manifest_path
        self.raw_dir = raw_dir / "football_api"
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def append_fixtures_live_snapshot(self, fixtures: list[dict[str, Any]]) -> Path:
        day_dir = self._day_dir()
        path = day_dir / "fixtures_live_latest.json"
        payload = {"saved_at": now_iso(), "count": len(fixtures), "fixtures": fixtures}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def should_refresh_fixture(self, fixture_id: str, poll_interval_seconds: int) -> bool:
        manifest = self._load_manifest()
        fixtures = manifest.setdefault("fixtures", {})
        row = fixtures.get(str(fixture_id), {})
        last = parse_dt(str(row.get("last_detail_fetch_at", "")))
        if last is None:
            return True
        return (now_utc() - last).total_seconds() >= poll_interval_seconds

    def write_fixture_detail(
        self,
        fixture_id: str,
        *,
        event_title: str,
        fixture_payload: dict[str, Any],
        statistics: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> Path:
        day_dir = self._day_dir()
        fixture_dir = day_dir / str(fixture_id)
        fixture_dir.mkdir(parents=True, exist_ok=True)
        saved_at = now_iso()
        payload = {
            "saved_at": saved_at,
            "fixture_id": str(fixture_id),
            "event_title": event_title,
            "fixture": fixture_payload,
            "statistics": statistics,
            "events": events,
        }
        path = fixture_dir / "latest.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        history_name = f"detail_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}_{uuid4().hex[:8]}.json"
        (fixture_dir / history_name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._update_manifest(fixture_id, event_title, fixture_payload, statistics, events)
        return path

    def load_recent_fixture_details(self, fixture_id: str, limit: int = 64) -> list[dict[str, Any]]:
        fixture_dir = self._day_dir() / str(fixture_id)
        if not fixture_dir.exists():
            return []
        files = sorted(fixture_dir.glob("detail_*.json"))[-limit:]
        rows: list[dict[str, Any]] = []
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8") or "{}")
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    def resolve_fixture_id(self, *, event_title: str = "", teams: list[str] | None = None) -> str:
        manifest = self._load_manifest()
        fixtures = manifest.get("fixtures", {}) if isinstance(manifest, dict) else {}
        wanted_title = normalize_event_title(event_title)
        wanted_teams = [str(team or "").strip() for team in (teams or []) if str(team or "").strip()]
        wanted_sides = [team_tokens(team) for team in wanted_teams]
        title_match = ""
        team_match = ""
        for fixture_id, row in fixtures.items():
            if not isinstance(row, dict):
                continue
            title = str(row.get("event_title") or "")
            normalized = normalize_event_title(title)
            if wanted_title and normalized == wanted_title:
                return str(fixture_id)
            if wanted_sides:
                parts_raw = re.split(r"\s+vs\.?\s+", title, flags=re.IGNORECASE)
                parts = [team_tokens(part) for part in parts_raw]
                if len(parts) == 2 and len(wanted_sides) >= 2:
                    if sides_match(wanted_sides, parts[0], parts[1], wanted_teams, parts_raw[0], parts_raw[1]):
                        team_match = str(fixture_id)
        return team_match or title_match or self.resolve_fixture_id_from_live_snapshot(event_title=event_title, teams=teams)

    def resolve_fixture_id_from_live_snapshot(self, *, event_title: str = "", teams: list[str] | None = None) -> str:
        snapshot_path = self._day_dir() / "fixtures_live_latest.json"
        if not snapshot_path.exists():
            return ""
        payload = json.loads(snapshot_path.read_text(encoding="utf-8") or "{}")
        rows = payload.get("fixtures", []) if isinstance(payload, dict) else []
        wanted_title = normalize_event_title(event_title)
        wanted_teams = [str(team or "").strip() for team in (teams or []) if str(team or "").strip()]
        wanted_sides = [team_tokens(team) for team in wanted_teams]
        if len(wanted_sides) < 2 and event_title:
            parts = re.split(r"\s+vs\.?\s+", re.sub(r"\s+-\s+.*$", "", event_title, flags=re.IGNORECASE), flags=re.IGNORECASE)
            if len(parts) == 2:
                wanted_teams = [parts[0], parts[1]]
                wanted_sides = [team_tokens(parts[0]), team_tokens(parts[1])]
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = fixture_title(row)
            fixture_id = fixture_id_from_row(row)
            if not fixture_id:
                continue
            if wanted_title and normalize_event_title(title) == wanted_title:
                return fixture_id
            if wanted_sides:
                home_name = ((row.get("teams") or {}).get("home") or {}).get("name") if isinstance((row.get("teams") or {}).get("home"), dict) else ""
                away_name = ((row.get("teams") or {}).get("away") or {}).get("name") if isinstance((row.get("teams") or {}).get("away"), dict) else ""
                home_tokens = team_tokens(home_name)
                away_tokens = team_tokens(away_name)
                if len(wanted_sides) >= 2 and sides_match(wanted_sides, home_tokens, away_tokens, wanted_teams, str(home_name or ""), str(away_name or "")):
                    return fixture_id
        return ""

    def _update_manifest(
        self,
        fixture_id: str,
        event_title: str,
        fixture_payload: dict[str, Any],
        statistics: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> None:
        manifest = self._load_manifest()
        fixtures = manifest.setdefault("fixtures", {})
        fixture = fixture_payload.get("fixture") if isinstance(fixture_payload.get("fixture"), dict) else {}
        status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
        row = fixtures.setdefault(str(fixture_id), {})
        row.update(
            {
                "fixture_id": str(fixture_id),
                "event_title": event_title,
                "last_detail_fetch_at": now_iso(),
                "elapsed": status.get("elapsed"),
                "period": status.get("short"),
                "statistics_rows": len(statistics),
                "event_rows": len(events),
            }
        )
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"fixtures": {}}
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8") or "{}")
        return payload if isinstance(payload, dict) else {"fixtures": {}}

    def _day_dir(self) -> Path:
        day = now_utc().strftime("%Y-%m-%d")
        path = self.raw_dir / day
        path.mkdir(parents=True, exist_ok=True)
        return path


def capture_proof_of_winning_details(
    settings: dict[str, Any],
    client: FootballApiClient,
    store: FootballResearchStore,
    fixtures: list[dict[str, Any]],
    tracked_matches: TrackedMatches | None = None,
) -> int:
    cfg = settings.get("football_api", {})
    if not bool(cfg.get("detail_capture_enabled", True)):
        return 0
    minute_floor = int(cfg.get("detail_capture_minute_floor", 70))
    priority_minute_floor = int(cfg.get("detail_capture_priority_minute_floor", 60))
    poll_interval = int(cfg.get("detail_capture_poll_interval_seconds", 30))
    tracked_index = build_tracked_index(tracked_matches.load()) if tracked_matches is not None else set()
    captured = 0
    for row in fixtures:
        if not is_live_soccer_fixture(row):
            continue
        elapsed = fixture_elapsed(row)
        min_required = priority_minute_floor if is_tracked_fixture(row, tracked_index) else minute_floor
        if elapsed is None or elapsed < min_required:
            continue
        fixture_id = fixture_id_from_row(row)
        if not fixture_id:
            continue
        if not store.should_refresh_fixture(fixture_id, poll_interval):
            continue
        statistics = client.fixture_statistics(fixture_id)
        events = client.fixture_events(fixture_id)
        store.write_fixture_detail(
            fixture_id,
            event_title=fixture_title(row),
            fixture_payload=row,
            statistics=statistics,
            events=events,
        )
        captured += 1
    return captured


def fixture_id_from_row(row: dict[str, Any]) -> str:
    fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
    value = fixture.get("id")
    return str(value) if value not in (None, "") else ""


def fixture_elapsed(row: dict[str, Any]) -> float | None:
    fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
    status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
    value = status.get("elapsed")
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fixture_title(row: dict[str, Any]) -> str:
    teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
    home = ((teams.get("home") or {}).get("name") if isinstance(teams.get("home"), dict) else "") or ""
    away = ((teams.get("away") or {}).get("name") if isinstance(teams.get("away"), dict) else "") or ""
    if home and away:
        return f"{home} vs. {away}"
    league = row.get("league") if isinstance(row.get("league"), dict) else {}
    return str(league.get("name") or "")


def is_live_soccer_fixture(row: dict[str, Any]) -> bool:
    league = row.get("league") if isinstance(row.get("league"), dict) else {}
    sport_name = str(league.get("sport") or row.get("sport") or "football").lower()
    fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
    status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
    short = str(status.get("short") or "").upper()
    return sport_name in {"football", "soccer"} and short in {"1H", "2H", "HT", "ET", "BT", "P", "LIVE"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def normalize_event_title(value: str) -> str:
    cleaned = re.sub(r"\s+-\s+(more markets|exact score|halftime result|player props).*$", "", str(value or ""), flags=re.IGNORECASE)
    cleaned = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"\b(fc|cf|sc|afc|wfc|club|de|la|the|women|ud|cd|fk|ol)\b", " ", cleaned.lower())
    return re.sub(r"[^a-z0-9]+", "", cleaned)


def normalize_team_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(
        r"\b(fc|cf|sc|afc|wfc|club|de|la|the|w|women|ud|cd|fk|ol)\b",
        " ",
        text.lower(),
    )
    return re.sub(r"[^a-z0-9]+", "", cleaned)


def team_tokens(value: str) -> set[str]:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(
        r"\b(fc|cf|sc|afc|wfc|club|de|la|the|w|women|ud|cd|fk|ol|city|united|town|county|athletic|atletico|sporting|current|warriors|rovers|wanderers|olympic)\b",
        " ",
        text.lower(),
    )
    return {token for token in re.findall(r"[a-z0-9]+", cleaned) if len(token) >= 2}


def sides_match(wanted_sides: list[set[str]], home_tokens: set[str], away_tokens: set[str], wanted_teams: list[str], home_name: str, away_name: str) -> bool:
    if len(wanted_sides) < 2:
        return False
    wanted_home_name = normalize_team_name(wanted_teams[0]) if len(wanted_teams) >= 1 else ""
    wanted_away_name = normalize_team_name(wanted_teams[1]) if len(wanted_teams) >= 2 else ""
    home_norm = normalize_team_name(home_name)
    away_norm = normalize_team_name(away_name)
    if wanted_home_name and wanted_away_name:
        if wanted_home_name == home_norm and wanted_away_name == away_norm:
            return True
        if wanted_home_name == away_norm and wanted_away_name == home_norm:
            return True
    overlap_a_home = len(wanted_sides[0] & home_tokens)
    overlap_a_away = len(wanted_sides[1] & away_tokens)
    overlap_b_home = len(wanted_sides[0] & away_tokens)
    overlap_b_away = len(wanted_sides[1] & home_tokens)
    if overlap_a_home >= 1 and overlap_a_away >= 1 and (overlap_a_home + overlap_a_away) >= 3:
        return True
    if overlap_b_home >= 1 and overlap_b_away >= 1 and (overlap_b_home + overlap_b_away) >= 3:
        return True
    return False


def build_tracked_index(events: list[dict[str, Any]]) -> set[str]:
    index: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        title = str(event.get("title") or "")
        if title:
            index.add(normalize_event_title(title))
    return index


def is_tracked_fixture(row: dict[str, Any], tracked_index: set[str]) -> bool:
    if not tracked_index:
        return False
    title = fixture_title(row)
    if not title:
        return False
    return normalize_event_title(title) in tracked_index
