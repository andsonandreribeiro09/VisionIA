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

$env:VISIONAI_APP = "admin"
$env:FLASK_DEBUG = "0"
$env:PORT = if ($env:VISIONAI_ADMIN_PORT) { $env:VISIONAI_ADMIN_PORT } else { "5002" }
$env:VISIONAI_ADMIN_USER = if ($env:VISIONAI_ADMIN_USER) { $env:VISIONAI_ADMIN_USER } else { "admin" }
$env:VISIONAI_ADMIN_PASSWORD = if ($env:VISIONAI_ADMIN_PASSWORD) { $env:VISIONAI_ADMIN_PASSWORD } else { "visionai-admin" }

if (-not $env:DATABASE_URL) {
    $env:VISIONAI_DB_PATH = if ($env:VISIONAI_ADMIN_DB_PATH) { $env:VISIONAI_ADMIN_DB_PATH } else { Join-Path $projectDir "data\visionai_admin.db" }
    $dbDir = Split-Path -Parent $env:VISIONAI_DB_PATH
    if ($dbDir) {
        New-Item -ItemType Directory -Path $dbDir -Force | Out-Null
    }
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
Write-Host "VisionAI admin local"
Write-Host "URL local:   http://localhost:$($env:PORT)/admin"
Write-Host "Usuario:     $($env:VISIONAI_ADMIN_USER)"
Write-Host "Senha:       $($env:VISIONAI_ADMIN_PASSWORD)"
if ($env:DATABASE_URL) {
    Write-Host "Banco:       PostgreSQL"
} else {
    Write-Host "Banco:       SQLite local"
    Write-Host "Arquivo DB:  $($env:VISIONAI_DB_PATH)"
}
Write-Host ""

& $pythonCmd.Source app.py
