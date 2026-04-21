@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\live_matches_status.py
) else (
  python scripts\live_matches_status.py
)
pause
