from __future__ import annotations

from app.dashboard.common import is_soccer_event
from app.normalize.normalizer import classify_sport


def test_lol_event_is_not_soccer() -> None:
    event = {"title": "LoL: Shopify Rebellion vs Team Liquid", "slug": "lol-sr-tl-2026-04-16"}
    assert classify_sport(event) == "unknown"
    assert not is_soccer_event(event)


def test_fc_match_is_soccer() -> None:
    event = {"title": "Arsenal FC vs. Sporting CP", "slug": "ucl-ars-spo-2026-04-16"}
    assert classify_sport(event) == "soccer"
    assert is_soccer_event(event)
