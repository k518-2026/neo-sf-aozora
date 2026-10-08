param(
    [string]$Role = "auto"
)

$ErrorActionPreference = "Continue"
$repoDir = $PSScriptRoot
if (-not $repoDir) {
    $repoDir = (Get-Location).Path
}
$workerScript = Join-Path $repoDir "run_worker.ps1"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " Neo SF Aozora - Autonomous Worker Setup (No Main PC Required)" -ForegroundColor Cyan
Write-Host " Hostname : $env:COMPUTERNAME" -ForegroundColor Cyan
Write-Host " Repo Dir : $repoDir" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Install Windows Startup shortcut (.cmd) so it runs automatically whenever this PC boots / logs on (No Admin required)
try {
    $startupDir = [Environment]::GetFolderPath('Startup')
    $startupCmdPath = Join-Path $startupDir "NeoSFAozora_AutonomousWorker.cmd"
    $cmdLines = @(
        "@echo off",
        "cd /d `"$repoDir`"",
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$workerScript`" -Role $Role"
    )
    Set-Content -Path $startupCmdPath -Value ($cmdLines -join "`r`n") -Encoding ASCII -Force
    Write-Host "[OK] Registered Startup script (runs on PC boot/logon): $startupCmdPath" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Could not write Startup script: $_" -ForegroundColor Yellow
}

# 2. Register Daily Scheduled Task (20:00 and 21:00) with fallback to schtasks.exe (works without Admin elevation)
$taskRegistered = $false
try {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$workerScript`" -Role $Role" -WorkingDirectory $repoDir
    $t1 = New-ScheduledTaskTrigger -Daily -At "20:00"
    $t2 = New-ScheduledTaskTrigger -Daily -At "21:00"
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName "NeoSFAozora_AutonomousWorker" -Action $action -Trigger @($t1, $t2) -Settings $settings -Description "Autonomous GitHub-synced worker for Neo SF Aozora" -Force -ErrorAction Stop | Out-Null
    $taskRegistered = $true
    Write-Host "[OK] Registered Scheduled Task 'NeoSFAozora_AutonomousWorker' (Daily 20:00 & 21:00)" -ForegroundColor Green
} catch {
    Write-Host "[INFO] Register-ScheduledTask required elevation, falling back to user-level schtasks.exe..." -ForegroundColor Yellow
    $trCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$workerScript`" -Role $Role"
    schtasks /Create /TN "NeoSFAozora_AutonomousWorker" /TR $trCmd /SC DAILY /ST 20:00 /F | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $taskRegistered = $true
        Write-Host "[OK] Registered Scheduled Task via schtasks.exe (Daily 20:00)" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Scheduled Task registration skipped (Startup folder script is active and will run on every login)." -ForegroundColor Yellow
    }
}

Write-Host "`nSetup complete! Running an immediate check of the worker..." -ForegroundColor Cyan
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $workerScript -Role $Role
