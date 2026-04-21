@echo off
cd /d "%~dp0"
echo Writing daily report...
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\run_daily_report.py
) else (
  python scripts\run_daily_report.py
)
pause
