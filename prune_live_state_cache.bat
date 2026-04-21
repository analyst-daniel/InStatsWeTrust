@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\prune_live_state_cache.py
) else (
  python scripts\prune_live_state_cache.py
)
pause
