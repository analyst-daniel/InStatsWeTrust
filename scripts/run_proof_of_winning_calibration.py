from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.strategy.proof_of_winning_reporting import write_calibration_report
from app.utils.config import load_settings, resolve_path


def main() -> None:
    settings = load_settings()
    csv_path, md_path = write_calibration_report(
        resolve_path(settings["storage"]["sqlite_path"]),
        resolve_path(settings["storage"]["daily_dir"]),
    )
    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
