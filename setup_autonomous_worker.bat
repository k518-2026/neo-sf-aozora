@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ==================================================================
echo  Neo SF Aozora - Autonomous Worker Setup (Windows)
echo ==================================================================
echo.
echo [1/2] Pulling latest code from GitHub (discarding local task conflicts)...
git fetch origin main
git reset --hard origin/main

echo.
echo [2/2] Running PowerShell setup with ExecutionPolicy Bypass...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_autonomous_worker.ps1"
echo.
pause
