$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

$envFile = if ($env:VISIONAI_ENV_FILE) { $env:VISIONAI_ENV_FILE } else { Join-Path $projectDir ".env.local" }
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

$env:VISIONAI_APP = "medicao"
$env:VISIONAI_LOCAL_MODE = "1"
$env:FLASK_DEBUG = "0"
$env:PORT = if ($env:VISIONAI_MEDICAO_PORT) { $env:VISIONAI_MEDICAO_PORT } else { "5000" }

$usarPostgresRender = ($env:VISIONAI_USE_RENDER_DB -eq "1") -or ($env:VISIONAI_DB_MODE -eq "render")
if ($usarPostgresRender) {
    if (-not $env:DATABASE_URL) {
        Write-Host ""
        Write-Host "DATABASE_URL nao configurado."
        Write-Host "Crie o arquivo .env.local na pasta do projeto usando .env.local.example como modelo."
        Write-Host "Cole nele a URL completa do PostgreSQL do Render."
        Write-Host ""
        exit 1
    }
    $env:VISIONAI_REQUIRE_DATABASE_URL = "1"
} else {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    $env:VISIONAI_REQUIRE_DATABASE_URL = "0"
    $env:VISIONAI_DB_PATH = if ($env:VISIONAI_LOCAL_DB_PATH) { $env:VISIONAI_LOCAL_DB_PATH } else { Join-Path $projectDir "data\visionai_teste_local.db" }
    $env:VISIONAI_DATA_DIR = if ($env:VISIONAI_LOCAL_DATA_DIR) { $env:VISIONAI_LOCAL_DATA_DIR } else { Join-Path $projectDir "data" }
    $dbDir = Split-Path -Parent $env:VISIONAI_DB_PATH
    if ($dbDir) {
        New-Item -ItemType Directory -Path $dbDir -Force | Out-Null
    }
    New-Item -ItemType Directory -Path $env:VISIONAI_DATA_DIR -Force | Out-Null
    $csvAntigo = Join-Path $projectDir "pacientes_medicoes.csv"
    $csvLocal = Join-Path $env:VISIONAI_DATA_DIR "pacientes_medicoes.csv"
    if ((Test-Path $csvAntigo) -and -not (Test-Path $csvLocal)) {
        Copy-Item -LiteralPath $csvAntigo -Destination $csvLocal
    }
}

$env:VISIONAI_CAPTURE_MIN_SCORE = if ($env:VISIONAI_CAPTURE_MIN_SCORE) { $env:VISIONAI_CAPTURE_MIN_SCORE } else { "82" }
$env:VISIONAI_CAPTURE_RESET_SCORE = if ($env:VISIONAI_CAPTURE_RESET_SCORE) { $env:VISIONAI_CAPTURE_RESET_SCORE } else { "60" }
$env:VISIONAI_MIN_STABLE_FRAMES = if ($env:VISIONAI_MIN_STABLE_FRAMES) { $env:VISIONAI_MIN_STABLE_FRAMES } else { "3" }
$env:VISIONAI_MIN_STABLE_SECONDS = if ($env:VISIONAI_MIN_STABLE_SECONDS) { $env:VISIONAI_MIN_STABLE_SECONDS } else { "0.30" }
$env:VISIONAI_CAPTURED_RESET_SECONDS = if ($env:VISIONAI_CAPTURED_RESET_SECONDS) { $env:VISIONAI_CAPTURED_RESET_SECONDS } else { "12" }
$env:VISIONAI_UI_CAPTURE_SCORE_MIN = if ($env:VISIONAI_UI_CAPTURE_SCORE_MIN) { $env:VISIONAI_UI_CAPTURE_SCORE_MIN } else { "82" }
$env:VISIONAI_UI_CAPTURE_RESET_SCORE = if ($env:VISIONAI_UI_CAPTURE_RESET_SCORE) { $env:VISIONAI_UI_CAPTURE_RESET_SCORE } else { "60" }
$env:VISIONAI_UI_CAPTURE_HOLD_MS = if ($env:VISIONAI_UI_CAPTURE_HOLD_MS) { $env:VISIONAI_UI_CAPTURE_HOLD_MS } else { "180" }
$env:VISIONAI_UI_CAPTURE_COOLDOWN_MS = if ($env:VISIONAI_UI_CAPTURE_COOLDOWN_MS) { $env:VISIONAI_UI_CAPTURE_COOLDOWN_MS } else { "350" }
$env:VISIONAI_UI_REQUIRE_STABLE = if ($env:VISIONAI_UI_REQUIRE_STABLE) { $env:VISIONAI_UI_REQUIRE_STABLE } else { "1" }
$env:VISIONAI_UI_STABLE_SAMPLES = if ($env:VISIONAI_UI_STABLE_SAMPLES) { $env:VISIONAI_UI_STABLE_SAMPLES } else { "2" }
$env:VISIONAI_UI_STABLE_WINDOW_MS = if ($env:VISIONAI_UI_STABLE_WINDOW_MS) { $env:VISIONAI_UI_STABLE_WINDOW_MS } else { "1200" }
$env:VISIONAI_UI_MAX_DP_SPREAD = if ($env:VISIONAI_UI_MAX_DP_SPREAD) { $env:VISIONAI_UI_MAX_DP_SPREAD } else { "0.9" }
$env:VISIONAI_UI_MAX_DP_TREND = if ($env:VISIONAI_UI_MAX_DP_TREND) { $env:VISIONAI_UI_MAX_DP_TREND } else { "0.45" }
$env:VISIONAI_UI_BLOCK_DP_MARGIN = if ($env:VISIONAI_UI_BLOCK_DP_MARGIN) { $env:VISIONAI_UI_BLOCK_DP_MARGIN } else { "0.3" }
$env:VISIONAI_UI_MAX_CAPTURE_GAP = if ($env:VISIONAI_UI_MAX_CAPTURE_GAP) { $env:VISIONAI_UI_MAX_CAPTURE_GAP } else { "1.8" }
$env:VISIONAI_UI_INCOMPATIBLE_RESET_MS = if ($env:VISIONAI_UI_INCOMPATIBLE_RESET_MS) { $env:VISIONAI_UI_INCOMPATIBLE_RESET_MS } else { "1600" }
$env:VISIONAI_UI_MIN_GEOMETRY_SCORE = if ($env:VISIONAI_UI_MIN_GEOMETRY_SCORE) { $env:VISIONAI_UI_MIN_GEOMETRY_SCORE } else { "65" }
$env:VISIONAI_UI_TOTAL_CAPTURES = if ($env:VISIONAI_UI_TOTAL_CAPTURES) { $env:VISIONAI_UI_TOTAL_CAPTURES } else { "1" }
$env:VISIONAI_MIN_BATCH_CAPTURES = if ($env:VISIONAI_MIN_BATCH_CAPTURES) { $env:VISIONAI_MIN_BATCH_CAPTURES } else { "1" }
$env:VISIONAI_MIN_BATCH_GEOMETRY_SCORE = if ($env:VISIONAI_MIN_BATCH_GEOMETRY_SCORE) { $env:VISIONAI_MIN_BATCH_GEOMETRY_SCORE } else { "65" }
$env:VISIONAI_MAX_BATCH_ERRO_MM = if ($env:VISIONAI_MAX_BATCH_ERRO_MM) { $env:VISIONAI_MAX_BATCH_ERRO_MM } else { "1.8" }
$env:VISIONAI_MAX_BATCH_STD_MM = if ($env:VISIONAI_MAX_BATCH_STD_MM) { $env:VISIONAI_MAX_BATCH_STD_MM } else { "1.0" }
$env:VISIONAI_VALIDATE_DP_RANGE = if ($env:VISIONAI_VALIDATE_DP_RANGE) { $env:VISIONAI_VALIDATE_DP_RANGE } else { "1" }
$env:VISIONAI_MIN_CALIBRATION_SAMPLES = if ($env:VISIONAI_MIN_CALIBRATION_SAMPLES) { $env:VISIONAI_MIN_CALIBRATION_SAMPLES } else { "3" }
$env:VISIONAI_MAX_CALIBRATION_FACTOR_DELTA = if ($env:VISIONAI_MAX_CALIBRATION_FACTOR_DELTA) { $env:VISIONAI_MAX_CALIBRATION_FACTOR_DELTA } else { "0.08" }
$env:VISIONAI_USE_MEDIAN_RESULT = if ($env:VISIONAI_USE_MEDIAN_RESULT) { $env:VISIONAI_USE_MEDIAN_RESULT } else { "1" }
$env:VISIONAI_UI_PHOTO_MAX_WIDTH = if ($env:VISIONAI_UI_PHOTO_MAX_WIDTH) { $env:VISIONAI_UI_PHOTO_MAX_WIDTH } else { "720" }
$env:VISIONAI_UI_PHOTO_QUALITY = if ($env:VISIONAI_UI_PHOTO_QUALITY) { $env:VISIONAI_UI_PHOTO_QUALITY } else { "0.68" }
$env:VISIONAI_SCALE_MULTIPLIER = if ($env:VISIONAI_SCALE_MULTIPLIER) { $env:VISIONAI_SCALE_MULTIPLIER } else { "1.00" }
$env:VISIONAI_MIN_CAPTURE_IRIS_PX = if ($env:VISIONAI_MIN_CAPTURE_IRIS_PX) { $env:VISIONAI_MIN_CAPTURE_IRIS_PX } else { "10.0" }
$env:VISIONAI_MAX_CAPTURE_IRIS_PX = if ($env:VISIONAI_MAX_CAPTURE_IRIS_PX) { $env:VISIONAI_MAX_CAPTURE_IRIS_PX } else { "14.5" }
$env:VISIONAI_IDEAL_CAPTURE_IRIS_MIN_PX = if ($env:VISIONAI_IDEAL_CAPTURE_IRIS_MIN_PX) { $env:VISIONAI_IDEAL_CAPTURE_IRIS_MIN_PX } else { "11.0" }
$env:VISIONAI_IDEAL_CAPTURE_IRIS_MAX_PX = if ($env:VISIONAI_IDEAL_CAPTURE_IRIS_MAX_PX) { $env:VISIONAI_IDEAL_CAPTURE_IRIS_MAX_PX } else { "13.9" }
$env:VISIONAI_UI_CROP_PADDING_X = if ($env:VISIONAI_UI_CROP_PADDING_X) { $env:VISIONAI_UI_CROP_PADDING_X } else { "1.36" }
$env:VISIONAI_UI_CROP_PADDING_Y = if ($env:VISIONAI_UI_CROP_PADDING_Y) { $env:VISIONAI_UI_CROP_PADDING_Y } else { "1.22" }
$env:VISIONAI_MAX_DNP_DIFF_MM = if ($env:VISIONAI_MAX_DNP_DIFF_MM) { $env:VISIONAI_MAX_DNP_DIFF_MM } else { "5.0" }
$env:VISIONAI_MAX_APPROVAL_YAW = if ($env:VISIONAI_MAX_APPROVAL_YAW) { $env:VISIONAI_MAX_APPROVAL_YAW } else { "4.5" }
$env:VISIONAI_RESULT_PREVIEW_MS = if ($env:VISIONAI_RESULT_PREVIEW_MS) { $env:VISIONAI_RESULT_PREVIEW_MS } else { "5500" }

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host ""
    Write-Host "Python nao encontrado no PATH."
    Write-Host ""
    exit 1
}

$pythonPath = & $pythonCmd.Source -c "import sys; print(sys.executable)"
Write-Host "Python:      $pythonPath"

if ($usarPostgresRender) {
    & $pythonCmd.Source -c "import psycopg" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Instalando driver PostgreSQL psycopg[binary]..."
        & $pythonCmd.Source -m pip install "psycopg[binary]"
    }

    $psycopgVersion = & $pythonCmd.Source -c "import psycopg; print(psycopg.__version__)"
}

$localIp = Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Wi-Fi" -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "169.254.*" } |
    Select-Object -First 1 -ExpandProperty IPAddress

Write-Host "VisionAI medicao local"
Write-Host "URL local:   http://localhost:$($env:PORT)"
if ($localIp) {
    Write-Host "URL rede:    http://$localIp`:$($env:PORT)"
}
if ($usarPostgresRender) {
    Write-Host "Banco:       PostgreSQL Render"
    Write-Host "PostgreSQL:  psycopg $psycopgVersion"
} else {
    Write-Host "Banco:       SQLite local de teste"
    Write-Host "Arquivo DB:  $($env:VISIONAI_DB_PATH)"
    Write-Host "CSV local:   $(Join-Path $env:VISIONAI_DATA_DIR "pacientes_medicoes.csv")"
}
Write-Host "Captura:     score $($env:VISIONAI_UI_CAPTURE_SCORE_MIN), $($env:VISIONAI_UI_CAPTURE_HOLD_MS)ms, $($env:VISIONAI_UI_TOTAL_CAPTURES) capturas, escala x$($env:VISIONAI_SCALE_MULTIPLIER)"
Write-Host "Distancia:   iris $($env:VISIONAI_MIN_CAPTURE_IRIS_PX)-$($env:VISIONAI_MAX_CAPTURE_IRIS_PX)px, ideal $($env:VISIONAI_IDEAL_CAPTURE_IRIS_MIN_PX)-$($env:VISIONAI_IDEAL_CAPTURE_IRIS_MAX_PX)px"
Write-Host "Recorte:     x$($env:VISIONAI_UI_CROP_PADDING_X) / y$($env:VISIONAI_UI_CROP_PADDING_Y), revisar DNP>$($env:VISIONAI_MAX_DNP_DIFF_MM)mm, yaw>$($env:VISIONAI_MAX_APPROVAL_YAW)"
Write-Host ""

& $pythonCmd.Source app.py
