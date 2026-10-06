param(
    [int]$Count = 1,
    [string]$HostUrl = "http://192.168.128.59:11434",
    [string]$DrawThingsHost = "http://192.168.128.59:7860",
    [string]$Model = "shosetsu",
    [switch]$GenerateImages,
    [switch]$DailyQuota,
    [switch]$WeeklyQuota,
    [switch]$NoPush
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if ($DailyQuota -and -not $GenerateImages) {
    $todayStr = (Get-Date).ToString("yyyy-MM-dd")
    $createdToday = 0
    if (Test-Path "content") {
        Get-ChildItem -Path "content" -Filter "${todayStr}_*.md" | ForEach-Object {
            $createdToday++
        }
    }
    if ($createdToday -ge $Count) {
        Write-Host "Daily quota already met ($createdToday / $Count work(s) generated on $todayStr). Skipping." -ForegroundColor Green
        exit 0
    }
    $Count = $Count - $createdToday
    Write-Host "Daily quota status ($todayStr): $createdToday generated so far, generating remaining $Count work(s)..." -ForegroundColor Cyan
}

if ($WeeklyQuota -and -not $GenerateImages) {
    # Calculate Monday of the current week (ISO week) to check stories created this week (especially Wed/Thu)
    $today = (Get-Date).Date
    $dayOfWeek = [int]$today.DayOfWeek
    if ($dayOfWeek -eq 0) { $dayOfWeek = 7 } # Sunday = 7
    $monday = $today.AddDays(1 - $dayOfWeek)
    $sunday = $monday.AddDays(6)

    $createdThisWeek = 0
    if (Test-Path "content") {
        Get-ChildItem -Path "content" -Filter "*.md" | ForEach-Object {
            if ($_.Name -match '^(\d{4}-\d{2}-\d{2})_') {
                $fileDate = [datetime]::ParseExact($Matches[1], "yyyy-MM-dd", $null)
                if ($fileDate -ge $monday -and $fileDate -le $sunday -and ($fileDate.DayOfWeek -eq 'Wednesday' -or $fileDate.DayOfWeek -eq 'Thursday')) {
                    $createdThisWeek++
                }
            }
        }
    }

    if ($createdThisWeek -ge $Count) {
        Write-Host "Weekly quota already met ($createdThisWeek / $Count works generated on Wed/Thu this week). Skipping." -ForegroundColor Green
        exit 0
    }
    $Count = $Count - $createdThisWeek
    Write-Host "Weekly Wed/Thu quota status: $createdThisWeek generated so far, generating remaining $Count work(s)..." -ForegroundColor Cyan
}

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



