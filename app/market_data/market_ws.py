from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable
from pathlib import Path

import websockets


async def run_market_ws(settings: dict, token_ids: Iterable[str], output_path: Path) -> None:
    """Subscribe to public CLOB market websocket and persist raw updates.

    This is optional for the first runtime. The scanner still reconciles with
    Gamma/CLOB REST every cycle.
    """
    url = settings["api"]["clob_market_ws_url"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    assets_ids = [str(v) for v in token_ids if v]
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps({"assets_ids": assets_ids, "type": "market"}))
                async for message in ws:
                    with output_path.open("a", encoding="utf-8") as handle:
                        handle.write(message)
                        handle.write("\n")
        except Exception:
            logging.exception("CLOB market websocket disconnected; reconnecting")
            await asyncio.sleep(5)
