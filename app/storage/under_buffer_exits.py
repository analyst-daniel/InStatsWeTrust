from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.paper_trader.exit_rules import UnderBufferExit


class UnderBufferExitStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def upsert_exits(self, exits: list[UnderBufferExit]) -> None:
        if not exits:
            return
        rows = [exit_row_to_dict(exit_row) for exit_row in exits]
        merged: dict[str, dict[str, object]] = {}
        if self.path.exists():
            with self.path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    merged[str(row["trade_id"])] = row
        for row in rows:
            merged[str(row["trade_id"])] = row
        values = list(merged.values())
        fieldnames: list[str] = []
        for row in values:
            for name in row.keys():
                if name not in fieldnames:
                    fieldnames.append(name)
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(values)


def exit_row_to_dict(exit_row: UnderBufferExit) -> dict[str, object]:
    row = asdict(exit_row)
    for key, value in list(row.items()):
        if isinstance(value, datetime):
            row[key] = value.isoformat()
        if value is None:
            row[key] = ""
    return row
