@echo off
cd /d "%~dp0"
echo Starting Football API fallback...
echo Folder: %CD%
if "%APISPORTS_KEY%"=="" (
  for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('APISPORTS_KEY','User')"`) do set "APISPORTS_KEY=%%K"
)
if "%APISPORTS_KEY%"=="" (
  echo ERROR: APISPORTS_KEY is missing. Football API comparison will not work.
  echo Set it with: setx APISPORTS_KEY "YOUR_REAL_API_KEY"
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: missing .venv\Scripts\python.exe
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\run_football_fallback.py
echo Football fallback stopped. Press any key to close.
pause >nul
