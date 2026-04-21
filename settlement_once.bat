@echo off
cd /d "%~dp0"
echo Running one settlement cycle...
echo Folder: %CD%
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\run_settlement.py --once
) else (
  python scripts\run_settlement.py --once
)
echo Done. Press any key to close.
pause >nul
