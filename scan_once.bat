@echo off
cd /d "%~dp0"
echo Running one scanner cycle...
echo Folder: %CD%
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\run_scanner.py --once
) else (
  python scripts\run_scanner.py --once
)
echo Done. Press any key to close.
pause >nul
