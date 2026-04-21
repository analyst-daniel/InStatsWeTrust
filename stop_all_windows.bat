@echo off
cd /d "%~dp0"
echo Stopping Polymarket scanner processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$current=$PID; $targets = Get-CimInstance Win32_Process | Where-Object { ($_.Name -match 'python' -and $_.CommandLine -like '*scripts*run_*') -or ($_.Name -match 'powershell' -and $_.ProcessId -ne $current -and $_.CommandLine -like '*polymarket_self_hosted*start_*bat*') }; foreach ($p in $targets) { Write-Host ('Stopping PID ' + $p.ProcessId + ' ' + $p.Name); Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Done.
pause
