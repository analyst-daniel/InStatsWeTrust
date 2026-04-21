from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.js_dashboard.server import run


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    url = f"http://{args.host}:{args.port}"
    if not args.no_open:
        webbrowser.open(url)
    run(args.host, args.port)


if __name__ == "__main__":
    main()
