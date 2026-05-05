from __future__ import annotations

from datetime import datetime, timezone

from app.normalize.normalizer import normalize_events, normalize_market


def test_second_outcome_ask_uses_one_minus_best_bid() -> None:
    event = {"id": "1", "slug": "team-a-team-b", "title": "Team A FC vs. Team B FC", "active": True}
    market = {
        "id": "m1",
        "slug": "m1",
        "question": "Will Team A FC win?",
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": '["yes-token", "no-token"]',
        "bestBid": "0.03",
        "bestAsk": "0.04",
        "active": True,
        "closed": False,
    }
    row = normalize_market(event, market, sport="soccer", timestamp=datetime.now(timezone.utc))
    assert row is not None
    assert row.best_ask_yes == 0.04
    assert row.best_bid_no == 0.96
    assert row.best_ask_no == 0.97


def test_normalize_events_deduplicates_same_market_by_latest_update() -> None:
    event = {
        "id": "1",
        "slug": "team-a-team-b",
        "title": "Team A FC vs. Team B FC",
        "active": True,
        "markets": [
            {
                "id": "m1",
                "slug": "m1",
                "question": "Will Team A FC vs. Team B FC end in a draw?",
                "outcomes": '["Yes", "No"]',
                "clobTokenIds": '["yes-token", "no-token"]',
                "bestBid": "0.21",
                "bestAsk": "0.22",
                "updatedAt": "2026-05-04T15:30:00Z",
                "active": True,
                "closed": False,
            },
            {
                "id": "m1",
                "slug": "m1",
                "question": "Will Team A FC vs. Team B FC end in a draw?",
                "outcomes": '["Yes", "No"]',
                "clobTokenIds": '["yes-token", "no-token"]',
                "bestBid": "0.02",
                "bestAsk": "0.021",
                "updatedAt": "2026-05-04T15:37:00Z",
                "active": True,
                "closed": False,
            },
        ],
    }

    rows = normalize_events([event])

    assert len(rows) == 1
    assert rows[0].best_ask_yes == 0.021
    assert rows[0].best_ask_no == 0.98
