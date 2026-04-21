from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.discovery.gamma_client import GammaClient
from app.normalize.normalizer import normalize_events
from app.utils.config import load_settings, resolve_path
from app.utils.logging import setup_logging


def main() -> None:
    settings = load_settings()
    logger = setup_logging(resolve_path(settings["storage"]["log_dir"]), name="discovery")
    client = GammaClient(settings, resolve_path(settings["storage"]["raw_dir"]))
    events = client.fetch_all_events()
    rows = normalize_events(events)
    logger.info("discovery events=%s normalized_markets=%s", len(events), len(rows))
    print(f"events={len(events)} normalized_markets={len(rows)}")


if __name__ == "__main__":
    main()
