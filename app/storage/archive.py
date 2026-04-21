from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path


def archive_day(data_dir: Path, files: list[Path]) -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_dir = data_dir / "archive" / day
    archive_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        if path.exists():
            shutil.copy2(path, archive_dir / path.name)
    return archive_dir
