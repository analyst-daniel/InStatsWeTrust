from __future__ import annotations

import time
from typing import Any

import httpx


class ClobClient:
    def __init__(self, settings: dict[str, Any]) -> None:
        self.base_url = settings["api"]["clob_base_url"].rstrip("/")
        self.timeout = settings["api"]["timeout_seconds"]
        self.retries = settings["api"]["retries"]
        self.backoff = settings["api"]["retry_backoff_seconds"]

    def get_book(self, token_id: str) -> dict[str, Any]:
        return self._get("/book", {"token_id": token_id})

    def max_stake_at_price(self, token_id: str, price: float, *, tolerance: float = 1e-9) -> float | None:
        try:
            book = self.get_book(token_id)
        except Exception:
            return None
        asks = book.get("asks", []) if isinstance(book, dict) else []
        total_shares = 0.0
        for level in asks:
            if not isinstance(level, dict):
                continue
            level_price = to_float(level.get("price"))
            level_size = to_float(level.get("size"))
            if level_price is None or level_size is None:
                continue
            if abs(level_price - price) <= tolerance:
                total_shares += level_size
        if total_shares <= 0:
            return None
        return round(total_shares * price, 4)

    def get_price(self, token_id: str, side: str = "BUY") -> dict[str, Any]:
        return self._get("/price", {"token_id": token_id, "side": side})

    def post_prices(self, token_ids: list[str], side: str = "BUY") -> list[dict[str, Any]]:
        return self._post("/prices", [{"token_id": token_id, "side": side} for token_id in token_ids])

    def post_spreads(self, token_ids: list[str]) -> list[dict[str, Any]]:
        return self._post("/spreads", [{"token_id": token_id} for token_id in token_ids])

    def last_trades_prices(self, token_ids: list[str]) -> list[dict[str, Any]]:
        return self._post("/last-trades-prices", [{"token_id": token_id} for token_id in token_ids])

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def _post(self, path: str, payload: Any) -> Any:
        return self._request("POST", path, json=payload)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.request(method, f"{self.base_url}{path}", **kwargs)
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self.backoff * attempt)
        raise RuntimeError(f"CLOB request failed {path}: {last_exc}")


def to_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
