from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.live_state.football_api_client import FootballApiClient


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
        history_name = f"detail_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}.json"
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
) -> int:
    cfg = settings.get("football_api", {})
    if not bool(cfg.get("detail_capture_enabled", True)):
        return 0
    minute_floor = int(cfg.get("detail_capture_minute_floor", 70))
    poll_interval = int(cfg.get("detail_capture_poll_interval_seconds", 30))
    captured = 0
    for row in fixtures:
        if not is_live_soccer_fixture(row):
            continue
        elapsed = fixture_elapsed(row)
        if elapsed is None or elapsed < minute_floor:
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
