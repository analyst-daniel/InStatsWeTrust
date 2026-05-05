from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from app.normalize.models import PaperTrade


class CapitalProcessManager:
    def __init__(self, settings: dict[str, Any], path: Path) -> None:
        cfg = settings.get("capital_processes", {})
        self.enabled = bool(cfg.get("enabled", False))
        self.start_balance = float(cfg.get("start_balance", 10.0))
        self.target_balance = float(cfg.get("target_balance", 21.0))
        self.max_active_processes = int(cfg.get("max_active_processes", 10))
        self.allow_open_new_when_all_funds_locked = bool(cfg.get("allow_open_new_when_all_funds_locked", True))
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        rows = payload.get("processes", []) if isinstance(payload, dict) else []
        return [row for row in rows if isinstance(row, dict)]

    def save(self, processes: list[dict[str, Any]]) -> None:
        payload = json.dumps({"processes": processes}, ensure_ascii=False, indent=2)
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(self.path.parent)) as handle:
                handle.write(payload)
                temp_path = Path(handle.name)
            temp_path.replace(self.path)
        finally:
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def assign_process(self, trades: list[PaperTrade]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        processes = self._sync_with_trades(self.load(), trades)
        ready = [row for row in processes if row.get("status") == "ready" and float(row.get("current_balance", 0.0) or 0.0) > 0]
        if ready:
            chosen = sorted(ready, key=lambda row: str(row.get("created_at") or ""))[0]
            self.save(processes)
            return chosen
        active = [row for row in processes if row.get("status") in {"ready", "in_trade"}]
        if len(active) >= self.max_active_processes:
            self.save(processes)
            return None
        if not self.allow_open_new_when_all_funds_locked and any(row.get("status") == "in_trade" for row in processes):
            self.save(processes)
            return None
        process = {
            "process_id": str(uuid4()),
            "created_at": now_iso(),
            "started_at": now_iso(),
            "closed_at": "",
            "status": "ready",
            "step_count": 0,
            "wins": 0,
            "losses": 0,
            "start_balance": round(self.start_balance, 4),
            "current_balance": round(self.start_balance, 4),
            "target_balance": round(self.target_balance, 4),
            "open_trade_id": "",
            "last_result": "",
            "last_trade_id": "",
        }
        processes.append(process)
        self.save(processes)
        return process

    def bind_trade_entry(self, trade: PaperTrade) -> None:
        if not self.enabled or not trade.process_id:
            return
        processes = self._sync_with_trades(self.load(), [trade])
        for row in processes:
            if str(row.get("process_id") or "") != trade.process_id:
                continue
            row["status"] = "in_trade"
            row["open_trade_id"] = trade.trade_id
            row["last_trade_id"] = trade.trade_id
            row["step_count"] = int(row.get("step_count") or 0) + 1
            break
        self.save(processes)

    def apply_trade_updates(self, trades: list[PaperTrade]) -> None:
        if not self.enabled:
            return
        if not any(trade.process_id for trade in trades):
            return
        processes = self._sync_with_trades(self.load(), trades)
        changed = False
        index = {str(row.get("process_id") or ""): row for row in processes}
        for trade in trades:
            process_id = str(trade.process_id or "")
            if not process_id or trade.status != "resolved":
                continue
            row = index.get(process_id)
            if not row:
                continue
            balance_after = 0.0
            if trade.pnl_usd is not None:
                balance_after = round(float(trade.stake_usd or 0.0) + float(trade.pnl_usd or 0.0), 4)
            row["current_balance"] = balance_after
            row["open_trade_id"] = ""
            row["last_trade_id"] = trade.trade_id
            row["last_result"] = trade.result
            if balance_after >= float(row.get("target_balance", self.target_balance)):
                row["status"] = "completed"
                row["closed_at"] = now_iso()
                row["wins"] = int(row.get("wins") or 0) + 1
            elif balance_after <= 0:
                row["status"] = "busted"
                row["closed_at"] = now_iso()
                row["losses"] = int(row.get("losses") or 0) + 1
            else:
                row["status"] = "ready"
                if trade.pnl_usd > 0:
                    row["wins"] = int(row.get("wins") or 0) + 1
                elif trade.pnl_usd < 0:
                    row["losses"] = int(row.get("losses") or 0) + 1
            changed = True
        if changed:
            self.save(processes)

    def summary(self, trades: list[PaperTrade]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not self.enabled:
            return {"enabled": False}, []
        processes = self._sync_with_trades(self.load(), trades)
        summary = {
            "enabled": True,
            "total": len(processes),
            "ready": sum(1 for row in processes if row.get("status") == "ready"),
            "in_trade": sum(1 for row in processes if row.get("status") == "in_trade"),
            "completed": sum(1 for row in processes if row.get("status") == "completed"),
            "busted": sum(1 for row in processes if row.get("status") == "busted"),
            "current_balance": round(sum(float(row.get("current_balance") or 0.0) for row in processes), 4),
            "deployed_capital": round(sum(float(row.get("start_balance") or 0.0) for row in processes), 4),
        }
        return summary, processes

    def _sync_with_trades(self, processes: list[dict[str, Any]], trades: list[PaperTrade]) -> list[dict[str, Any]]:
        open_by_trade_id = {trade.trade_id: trade for trade in trades if trade.status == "open"}
        for row in processes:
            open_trade_id = str(row.get("open_trade_id") or "")
            status = str(row.get("status") or "")
            if status == "in_trade" and open_trade_id and open_trade_id not in open_by_trade_id:
                if float(row.get("current_balance") or 0.0) > 0 and not row.get("closed_at"):
                    row["status"] = "ready"
                else:
                    row["status"] = "busted"
                row["open_trade_id"] = ""
        return processes


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
