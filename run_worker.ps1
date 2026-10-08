param(
    [string]$Role = "auto",
    [int]$Quota = 0,
    [switch]$NoPush
)

$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Syncing latest code & task queue from GitHub (git pull --rebase origin main)..." -ForegroundColor Cyan
git pull --rebase origin main | Out-Host

$argsList = @("-m", "src.task_worker", "--role", $Role)
if ($Quota -gt 0) {
    $argsList += @("--quota", "$Quota")
}
if ($NoPush) {
    $argsList += "--no-push"
}

Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Starting Distributed Local LLM Worker (Role: $Role) in $PSScriptRoot..." -ForegroundColor Cyan
python @argsList
