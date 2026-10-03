param(
    [int]$Count = 3,
    [string]$HostUrl = "http://192.168.128.59:11434",
    [string]$Model = "",
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$env:OLLAMA_HOST = $HostUrl

Write-Host "Checking Mac mini M4 Ollama server at $HostUrl ..." -ForegroundColor Cyan
try {
    $tags = Invoke-RestMethod -Uri "$HostUrl/api/tags" -TimeoutSec 5
    $modelNames = ($tags.models | ForEach-Object { $_.name }) -join ", "
    Write-Host "Connected to Mac mini M4 Ollama! Models: $modelNames" -ForegroundColor Green
} catch {
    Write-Host "Mac mini M4 Ollama server ($HostUrl) is not reachable. Skipping local batch generation." -ForegroundColor Yellow
    exit 0
}

$argsList = @("-m", "src.batch_stock", "--host", $HostUrl, "--count", "$Count")
if ($Model -ne "") {
    $argsList += @("--model", $Model)
}
if (-not $NoPush) {
    $argsList += "--push"
}

Write-Host "Running Local LLM Stock Generator via Mac mini M4: python $($argsList -join ' ')" -ForegroundColor Green
python @argsList


