param(
    [string]$Role = "auto"
)

$ErrorActionPreference = "Stop"
$repoDir = $PSScriptRoot
$workerScript = Join-Path $repoDir "run_worker.ps1"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " Neo SF Aozora - Autonomous Worker Setup (No Main PC Required)" -ForegroundColor Cyan
Write-Host " Hostname : $env:COMPUTERNAME" -ForegroundColor Cyan
Write-Host " Repo Dir : $repoDir" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Install Windows Startup shortcut (.cmd) so it runs automatically whenever this PC boots / logs on
$startupDir = [Environment]::GetFolderPath('Startup')
$startupCmdPath = Join-Path $startupDir "NeoSFAozora_AutonomousWorker.cmd"
$cmdLines = @(
    "@echo off",
    "cd /d `"$repoDir`"",
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$workerScript`" -Role $Role"
)
Set-Content -Path $startupCmdPath -Value ($cmdLines -join "`r`n") -Encoding ASCII
Write-Host "[OK] Registered Startup script (runs on PC boot/logon): $startupCmdPath" -ForegroundColor Green

# 2. Register Daily Scheduled Task (20:00 and 21:00) with StartWhenAvailable
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$workerScript`" -Role $Role" -WorkingDirectory $repoDir
$t1 = New-ScheduledTaskTrigger -Daily -At "20:00"
$t2 = New-ScheduledTaskTrigger -Daily -At "21:00"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "NeoSFAozora_AutonomousWorker" -Action $action -Trigger @($t1, $t2) -Settings $settings -Description "Autonomous GitHub-synced worker for Neo SF Aozora (runs even when MINISFORUM64GB is powered off)" -Force | Out-Null
Write-Host "[OK] Registered Scheduled Task 'NeoSFAozora_AutonomousWorker' (Daily 20:00 & 21:00 + StartWhenAvailable)" -ForegroundColor Green

Write-Host "`nSetup complete! This PC ($env:COMPUTERNAME) will now autonomously pull tasks from GitHub, execute its role, and push results even when MINISFORUM64GB is powered off." -ForegroundColor Cyan
