param(
    [int]$Count = 1,
    [string]$HostUrl = "http://rtx5060lp:11434,http://sff7020:1234",
    [string]$DrawThingsHost = "http://kenomac-mini:7860",
    [string]$Model = "shosetsu",
    [string]$Role = "lan-dispatch",
    [switch]$GenerateImages,
    [switch]$DailyQuota,
    [switch]$WeeklyQuota,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$env:OLLAMA_HOST = $HostUrl
$env:LM_STUDIO_HOST = "http://sff7020:1234"
$env:DRAW_THINGS_HOST = $DrawThingsHost

Write-Host "1. Pulling latest task queue (data/tasks.json & data/TASKS.md) from GitHub..." -ForegroundColor Cyan
try {
    git pull --rebase origin main | Out-Host
} catch {
    Write-Host "git pull warning: $_" -ForegroundColor Yellow
}

if ($GenerateImages) {
    $imgArgs = @("-m", "src.task_worker", "--role", "illustrator", "--quota", "5")
    if ($NoPush) { $imgArgs += "--no-push" }
    Write-Host "Running Illustrator Worker: python $($imgArgs -join ' ')" -ForegroundColor Green
    python @imgArgs
    exit 0
}

$workerArgs = @("-m", "src.task_worker", "--role", $Role, "--quota", "$Count")
if ($NoPush) {
    $workerArgs += "--no-push"
}

Write-Host "2. Executing queued tasks from GitHub (Alternating Primary http://rtx5060lp:11434 <-> Secondary http://sff7020:1234): python $($workerArgs -join ' ')" -ForegroundColor Green
python @workerArgs



