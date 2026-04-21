@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\live_state_status.py
) else (
  python scripts\live_state_status.py
)
pause
