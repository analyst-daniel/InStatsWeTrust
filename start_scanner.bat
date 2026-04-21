@echo off
cd /d "%~dp0"
echo Starting Polymarket Scanner...
echo Folder: %CD%
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: missing .venv\Scripts\python.exe
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\run_scanner.py
echo Scanner stopped. Press any key to close.
pause >nul
