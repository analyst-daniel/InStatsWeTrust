@echo off
cd /d "%~dp0"
echo Restarting Polymarket system...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$current=$PID; $targets = Get-CimInstance Win32_Process | Where-Object { ($_.Name -match 'python' -and $_.CommandLine -like '*scripts*run_*') -or ($_.Name -match 'powershell' -and $_.ProcessId -ne $current -and $_.CommandLine -like '*polymarket_self_hosted*start_*bat*') }; foreach ($p in $targets) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 >nul
call "%~dp0start_all_windows.bat"
