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

$env:VISIONAI_APP = "laboratorio"
$env:VISIONAI_LOCAL_MODE = "1"
$env:FLASK_DEBUG = "0"
$env:PORT = if ($env:VISIONAI_LAB_PORT) { $env:VISIONAI_LAB_PORT } else { "5001" }

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
}

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

Write-Host "VisionAI laboratorio local"
Write-Host "URL local:   http://localhost:$($env:PORT)/laboratorio"

if ($usarPostgresRender) {
    Write-Host "Banco:       PostgreSQL Render"
    Write-Host "PostgreSQL:  psycopg $psycopgVersion"
} else {
    Write-Host "Banco:       SQLite local de teste"
    Write-Host "Arquivo DB:  $($env:VISIONAI_DB_PATH)"
    Write-Host "CSV local:   $(Join-Path $env:VISIONAI_DATA_DIR "pacientes_medicoes.csv")"
}
Write-Host ""

& $pythonCmd.Source app.py
