@echo off
cd /d "%~dp0"
echo Starting JS Dashboard...
echo URL: http://127.0.0.1:8765
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: missing .venv\Scripts\python.exe
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\run_js_dashboard.py
echo JS dashboard stopped. Press any key to close.
pause >nul
