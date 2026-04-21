@echo off
set "ROOT=%~dp0"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('APISPORTS_KEY','User')"`) do set "APISPORTS_KEY=%%A"

start "Polymarket Live State" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%'; if (Test-Path '.venv\Scripts\Activate.ps1') { . '.\.venv\Scripts\Activate.ps1' }; .\start_live_state.bat"
start "Football API Fallback" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%'; if (Test-Path '.venv\Scripts\Activate.ps1') { . '.\.venv\Scripts\Activate.ps1' }; .\start_football_fallback.bat"
start "Polymarket Scanner" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%'; if (Test-Path '.venv\Scripts\Activate.ps1') { . '.\.venv\Scripts\Activate.ps1' }; .\start_scanner.bat"
start "Polymarket Settlement" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%'; if (Test-Path '.venv\Scripts\Activate.ps1') { . '.\.venv\Scripts\Activate.ps1' }; .\start_settlement.bat"
start "Polymarket JS Dashboard" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%'; if (Test-Path '.venv\Scripts\Activate.ps1') { . '.\.venv\Scripts\Activate.ps1' }; .\start_js_dashboard.bat"
