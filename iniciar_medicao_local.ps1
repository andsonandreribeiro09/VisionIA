$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

$envFile = Join-Path $projectDir ".env.local"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }

        $parts = $line.Split("=", 2)
        [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
    }
}

if (-not $env:DATABASE_URL) {
    Write-Host ""
    Write-Host "DATABASE_URL nao configurado."
    Write-Host "Crie o arquivo .env.local na pasta do projeto usando .env.local.example como modelo."
    Write-Host "Cole nele a URL completa do PostgreSQL do Render."
    Write-Host ""
    exit 1
}

$env:VISIONAI_APP = "medicao"
$env:VISIONAI_LOCAL_MODE = "1"
$env:VISIONAI_REQUIRE_DATABASE_URL = "1"
$env:FLASK_DEBUG = "0"
$env:PORT = if ($env:PORT) { $env:PORT } else { "5000" }

$env:VISIONAI_CAPTURE_MIN_SCORE = if ($env:VISIONAI_CAPTURE_MIN_SCORE) { $env:VISIONAI_CAPTURE_MIN_SCORE } else { "78" }
$env:VISIONAI_CAPTURE_RESET_SCORE = if ($env:VISIONAI_CAPTURE_RESET_SCORE) { $env:VISIONAI_CAPTURE_RESET_SCORE } else { "55" }
$env:VISIONAI_MIN_STABLE_FRAMES = if ($env:VISIONAI_MIN_STABLE_FRAMES) { $env:VISIONAI_MIN_STABLE_FRAMES } else { "5" }
$env:VISIONAI_MIN_STABLE_SECONDS = if ($env:VISIONAI_MIN_STABLE_SECONDS) { $env:VISIONAI_MIN_STABLE_SECONDS } else { "0.8" }
$env:VISIONAI_UI_CAPTURE_SCORE_MIN = if ($env:VISIONAI_UI_CAPTURE_SCORE_MIN) { $env:VISIONAI_UI_CAPTURE_SCORE_MIN } else { "78" }
$env:VISIONAI_UI_CAPTURE_RESET_SCORE = if ($env:VISIONAI_UI_CAPTURE_RESET_SCORE) { $env:VISIONAI_UI_CAPTURE_RESET_SCORE } else { "55" }
$env:VISIONAI_UI_CAPTURE_HOLD_MS = if ($env:VISIONAI_UI_CAPTURE_HOLD_MS) { $env:VISIONAI_UI_CAPTURE_HOLD_MS } else { "900" }
$env:VISIONAI_UI_TOTAL_CAPTURES = if ($env:VISIONAI_UI_TOTAL_CAPTURES) { $env:VISIONAI_UI_TOTAL_CAPTURES } else { "5" }

$localIp = Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Wi-Fi" -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "169.254.*" } |
    Select-Object -First 1 -ExpandProperty IPAddress

Write-Host "VisionAI medicao local"
Write-Host "URL local:   http://localhost:$($env:PORT)"
if ($localIp) {
    Write-Host "URL rede:    http://$localIp`:$($env:PORT)"
}
Write-Host "Banco:       PostgreSQL Render"
Write-Host "Captura:     score $($env:VISIONAI_UI_CAPTURE_SCORE_MIN), $($env:VISIONAI_UI_CAPTURE_HOLD_MS)ms, $($env:VISIONAI_UI_TOTAL_CAPTURES) capturas"
Write-Host ""

python app.py
