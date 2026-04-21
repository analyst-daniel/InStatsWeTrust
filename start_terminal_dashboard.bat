@echo off
cd /d "%~dp0"
echo Starting Terminal Dashboard...
echo Folder: %CD%
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\run_terminal_dashboard.py --refresh 60
) else (
  python scripts\run_terminal_dashboard.py --refresh 60
)
echo Terminal dashboard stopped. Press any key to close.
pause >nul
