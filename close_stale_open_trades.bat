@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\close_stale_open_trades.py
) else (
  python scripts\close_stale_open_trades.py
)
pause
