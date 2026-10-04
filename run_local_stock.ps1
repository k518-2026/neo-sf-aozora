param(
    [int]$Count = 3,
    [string]$HostUrl = "http://192.168.128.59:11434",
    [string]$DrawThingsHost = "http://192.168.128.59:7860",
    [string]$Model = "",
    [switch]$GenerateImages,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$env:OLLAMA_HOST = $HostUrl
$env:DRAW_THINGS_HOST = $DrawThingsHost

Write-Host "Checking Mac mini M4 Ollama server at $HostUrl ..." -ForegroundColor Cyan
try {
    $tags = Invoke-RestMethod -Uri "$HostUrl/api/tags" -TimeoutSec 5
    $modelNames = ($tags.models | ForEach-Object { $_.name }) -join ", "
    Write-Host "Connected to Mac mini M4 Ollama! Models: $modelNames" -ForegroundColor Green
} catch {
    Write-Host "Mac mini M4 Ollama server ($HostUrl) is not reachable. Skipping local batch generation." -ForegroundColor Yellow
    exit 0
}

$argsList = @("-m", "src.batch_stock", "--host", $HostUrl, "--draw-things-host", $DrawThingsHost, "--count", "$Count")
if ($Model -ne "") {
    $argsList += @("--model", $Model)
}
if ($GenerateImages) {
    $argsList += "--generate-images"
}
if (-not $NoPush) {
    $argsList += "--push"
}

Write-Host "Running Local LLM & FLUX.2 Stock Generator via Mac mini M4: python $($argsList -join ' ')" -ForegroundColor Green
python @argsList


