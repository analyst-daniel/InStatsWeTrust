from __future__ import annotations

from app.discovery.expand import merge_event, should_expand_event, slug_variants
from app.live_state.cache import LiveStateCache


def test_slug_variants_include_more_markets() -> None:
    assert "ucl-bay1-rma1-2026-04-15-more-markets" in slug_variants("ucl-bay1-rma1-2026-04-15")


def test_merge_event_dedupes_markets() -> None:
    base = {"id": "1", "markets": [{"id": "m1", "question": "A"}]}
    detail = {"id": "1", "markets": [{"id": "m1", "question": "A2"}, {"id": "m2", "question": "B"}]}
    merged = merge_event(base, detail)
    assert [m["id"] for m in merged["markets"]] == ["m1", "m2"]


def test_should_expand_match_event_without_time(tmp_path) -> None:
    cache = LiveStateCache(tmp_path / "live.json")
    event = {"title": "Arsenal FC vs. Sporting CP", "slug": "ucl-ars-spo1-2026-04-15"}
    assert should_expand_event(event, cache, 360)
