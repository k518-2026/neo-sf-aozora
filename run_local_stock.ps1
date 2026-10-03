param(
    [int]$Count = 3,
    [string]$Model = "",
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Ensure Ollama is in PATH if installed in default AppData location
$ollamaDefaultDir = "$env:LOCALAPPDATA\Programs\Ollama"
if ((Test-Path "$ollamaDefaultDir\ollama.exe") -and ($env:Path -notlike "*$ollamaDefaultDir*")) {
    $env:Path = "$ollamaDefaultDir;$env:Path"
}

# Start Ollama server in background if not already listening
try {
    $null = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3
} catch {
    Write-Host "Starting Ollama server in background..." -ForegroundColor Cyan
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 4
}

$argsList = @("-m", "src.batch_stock", "--count", "$Count")
if ($Model -ne "") {
    $argsList += @("--model", $Model)
}
if (-not $NoPush) {
    $argsList += "--push"
}

Write-Host "Running Local LLM Stock Generator: python $($argsList -join ' ')" -ForegroundColor Green
try {
    python @argsList
} finally {
    Write-Host "Stopping Ollama server to free memory..." -ForegroundColor Cyan
    Get-Process -Name "ollama", "ollama_llama_server", "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

