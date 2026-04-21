from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import websockets

from app.live_state.cache import LiveStateCache


async def run_sports_ws(settings: dict[str, Any], cache_path: Path) -> None:
    cache = LiveStateCache(cache_path)
    url = settings["api"]["sports_ws_url"]
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as websocket:
                async for raw in websocket:
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    messages = payload if isinstance(payload, list) else [payload]
                    for message in messages:
                        if isinstance(message, dict):
                            cache.upsert_from_message(message)
                    cache.save()
        except Exception:
            await asyncio.sleep(5)

