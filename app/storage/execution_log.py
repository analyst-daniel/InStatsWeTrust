from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.execution.simulator import SimulatedExecution


class ExecutionLogStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def upsert(self, rows: list[SimulatedExecution]) -> None:
        if not rows:
            return
        new_rows = [execution_to_dict(row) for row in rows]
        merged: dict[str, dict[str, object]] = {}
        if self.path.exists():
            with self.path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    merged[str(row["execution_id"])] = row
        for row in new_rows:
            merged[str(row["execution_id"])] = row
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


def execution_to_dict(row: SimulatedExecution) -> dict[str, object]:
    payload = asdict(row)
    for key, value in list(payload.items()):
        if isinstance(value, datetime):
            payload[key] = value.isoformat()
        if value is None:
            payload[key] = ""
    return payload
