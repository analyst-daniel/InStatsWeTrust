@echo off
cd /d "%~dp0"
echo Starting Polymarket Live State...
echo Folder: %CD%
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: missing .venv\Scripts\python.exe
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\run_live_state.py
echo Live State stopped. Press any key to close.
pause >nul
