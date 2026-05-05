from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from app.normalize.models import MarketObservation, PaperTrade


class Store:
    def __init__(self, sqlite_path: Path, snapshot_csv: Path, trade_csv: Path) -> None:
        self.sqlite_path = sqlite_path
        self.snapshot_csv = snapshot_csv
        self.trade_csv = trade_csv
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_csv.parent.mkdir(parents=True, exist_ok=True)
        self.trade_csv.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.sqlite_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    timestamp_utc TEXT, event_id TEXT, event_slug TEXT, event_title TEXT,
                    market_id TEXT, market_slug TEXT, question TEXT, token_id TEXT,
                    side TEXT, price REAL, bid REAL, ask REAL, spread REAL,
                    liquidity REAL, last_trade_price REAL, sport TEXT, live INTEGER,
                    ended INTEGER, score TEXT, period TEXT, elapsed REAL, market_type TEXT,
                    spread_listed_team TEXT, spread_listed_line REAL, spread_listed_side_type TEXT,
                    spread_selected_team TEXT, spread_selected_line REAL, spread_selected_side_type TEXT,
                    total_line REAL, total_selected_side_type TEXT, total_goals INTEGER, total_goal_buffer REAL,
                    reason TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY, entry_timestamp TEXT, event_slug TEXT,
                    event_title TEXT, market_id TEXT, market_slug TEXT, question TEXT,
                    token_id TEXT, side TEXT, entry_price REAL, stake_usd REAL, max_stake_usd_at_entry REAL,
                    shares REAL, elapsed REAL, score TEXT, period TEXT, entry_reason TEXT,
                    process_id TEXT, process_step INTEGER, process_balance_before REAL, process_target_balance REAL,
                    status TEXT,
                    first_hit_99_at TEXT, first_hit_999_at TEXT, max_favorable_price REAL,
                    resolved_at TEXT, result TEXT, pnl_usd REAL
                )
                """
            )
            self._ensure_column(conn, "trades", "entry_reason", "TEXT")
            self._ensure_column(conn, "trades", "max_stake_usd_at_entry", "REAL")
            self._ensure_column(conn, "trades", "process_id", "TEXT")
            self._ensure_column(conn, "trades", "process_step", "INTEGER")
            self._ensure_column(conn, "trades", "process_balance_before", "REAL")
            self._ensure_column(conn, "trades", "process_target_balance", "REAL")
            self._ensure_column(conn, "snapshots", "market_type", "TEXT")
            self._ensure_column(conn, "snapshots", "spread_listed_team", "TEXT")
            self._ensure_column(conn, "snapshots", "spread_listed_line", "REAL")
            self._ensure_column(conn, "snapshots", "spread_listed_side_type", "TEXT")
            self._ensure_column(conn, "snapshots", "spread_selected_team", "TEXT")
            self._ensure_column(conn, "snapshots", "spread_selected_line", "REAL")
            self._ensure_column(conn, "snapshots", "spread_selected_side_type", "TEXT")
            self._ensure_column(conn, "snapshots", "total_line", "REAL")
            self._ensure_column(conn, "snapshots", "total_selected_side_type", "TEXT")
            self._ensure_column(conn, "snapshots", "total_goals", "INTEGER")
            self._ensure_column(conn, "snapshots", "total_goal_buffer", "REAL")

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    def append_snapshots(self, observations: list[MarketObservation]) -> None:
        if not observations:
            return
        rows = [model_row(obs) for obs in observations]
        append_csv(self.snapshot_csv, rows)
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO snapshots (
                    timestamp_utc, event_id, event_slug, event_title, market_id, market_slug,
                    question, token_id, side, price, bid, ask, spread, liquidity,
                    last_trade_price, sport, live, ended, score, period, elapsed, market_type,
                    spread_listed_team, spread_listed_line, spread_listed_side_type,
                    spread_selected_team, spread_selected_line, spread_selected_side_type,
                    total_line, total_selected_side_type, total_goals, total_goal_buffer, reason
                ) VALUES (
                    :timestamp_utc,:event_id,:event_slug,:event_title,:market_id,:market_slug,
                    :question,:token_id,:side,:price,:bid,:ask,:spread,:liquidity,
                    :last_trade_price,:sport,:live,:ended,:score,:period,:elapsed,:market_type,
                    :spread_listed_team,:spread_listed_line,:spread_listed_side_type,
                    :spread_selected_team,:spread_selected_line,:spread_selected_side_type,
                    :total_line,:total_selected_side_type,:total_goals,:total_goal_buffer,:reason
                )
                """,
                rows,
            )

    def upsert_trades(self, trades: list[PaperTrade]) -> None:
        if not trades:
            return
        rows = [model_row(trade) for trade in trades]
        rewrite_csv(self.trade_csv, rows, append_existing=True, key="trade_id")
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO trades (
                    trade_id, entry_timestamp, event_slug, event_title, market_id, market_slug,
                    question, token_id, side, entry_price, stake_usd, max_stake_usd_at_entry, shares, elapsed,
                    score, period, entry_reason, process_id, process_step, process_balance_before, process_target_balance,
                    status, first_hit_99_at, first_hit_999_at,
                    max_favorable_price, resolved_at, result, pnl_usd
                ) VALUES (
                    :trade_id,:entry_timestamp,:event_slug,:event_title,:market_id,:market_slug,
                    :question,:token_id,:side,:entry_price,:stake_usd,:max_stake_usd_at_entry,:shares,:elapsed,
                    :score,:period,:entry_reason,:process_id,:process_step,:process_balance_before,:process_target_balance,
                    :status,:first_hit_99_at,:first_hit_999_at,
                    :max_favorable_price,:resolved_at,:result,:pnl_usd
                )
                """,
                rows,
            )

    def load_open_trades(self) -> list[dict[str, str]]:
        if not self.trade_csv.exists():
            return []
        with self.trade_csv.open(newline="", encoding="utf-8") as handle:
            return [row for row in csv.DictReader(handle) if row.get("status") == "open"]


def model_row(model: BaseModel) -> dict[str, object]:
    row = model.model_dump(mode="json")
    for key, value in list(row.items()):
        if isinstance(value, bool):
            row[key] = int(value)
        if value is None:
            row[key] = ""
    return row


def append_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def rewrite_csv(path: Path, rows: list[dict[str, object]], *, append_existing: bool, key: str) -> None:
    merged: dict[str, dict[str, object]] = {}
    if append_existing and path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                merged[str(row[key])] = row
    for row in rows:
        merged[str(row[key])] = row
    values = list(merged.values())
    if not values:
        return
    fieldnames: list[str] = []
    for row in values:
        for name in row.keys():
            if name not in fieldnames:
                fieldnames.append(name)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(values)
