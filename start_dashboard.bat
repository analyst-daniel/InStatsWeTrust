@echo off
cd /d "%~dp0"
echo Starting Polymarket Dashboard...
echo Folder: %CD%
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\run_dashboard.py
) else (
  python scripts\run_dashboard.py
)
echo Dashboard stopped. Press any key to close.
pause >nul
