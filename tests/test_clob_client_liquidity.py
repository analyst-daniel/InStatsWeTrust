from __future__ import annotations

from app.market_data.clob_client import ClobClient


def settings() -> dict:
    return {
        "api": {
            "clob_base_url": "https://example.test",
            "timeout_seconds": 1,
            "retries": 1,
            "retry_backoff_seconds": 0,
        }
    }


def test_max_sell_at_price_uses_bid_levels(monkeypatch) -> None:
    client = ClobClient(settings())

    monkeypatch.setattr(
        client,
        "get_book",
        lambda token_id: {
            "bids": [
                {"price": "0.72", "size": "10"},
                {"price": "0.72", "size": "2.5"},
                {"price": "0.71", "size": "100"},
            ],
            "asks": [{"price": "0.72", "size": "999"}],
        },
    )

    assert client.max_sell_at_price("token", 0.72) == {"shares": 12.5, "usd": 9.0}


def test_max_stake_at_price_uses_ask_levels(monkeypatch) -> None:
    client = ClobClient(settings())

    monkeypatch.setattr(
        client,
        "get_book",
        lambda token_id: {
            "bids": [{"price": "0.80", "size": "999"}],
            "asks": [
                {"price": "0.80", "size": "5"},
                {"price": "0.80", "size": "5"},
            ],
        },
    )

    assert client.max_stake_at_price("token", 0.80) == 8.0
