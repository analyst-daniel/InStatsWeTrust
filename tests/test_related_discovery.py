from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.discovery.related import live_soccer_queries
from app.live_state.cache import LiveStateCache
from app.normalize.models import LiveState


def test_live_soccer_queries_include_more_markets(tmp_path: Path) -> None:
    cache = LiveStateCache(tmp_path / "live.json")
    cache._states["arsenal-fc-vs-sporting-cp"] = LiveState(
        slug="arsenal-fc-vs-sporting-cp",
        sport="soccer",
        live=True,
        ended=False,
        elapsed=78,
        last_update=datetime.now(timezone.utc),
        raw={"homeTeam": "Arsenal FC", "awayTeam": "Sporting CP"},
    )
    queries = live_soccer_queries(cache)
    assert "Arsenal FC vs Sporting CP More Markets" in queries
