$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:VISIONAI_ENV_FILE = Join-Path $projectDir ".env.detectavision.local"

if (-not (Test-Path $env:VISIONAI_ENV_FILE)) {
    Write-Host ""
    Write-Host "Perfil da Detecta Vision nao encontrado."
    Write-Host "Rode primeiro: .\preparar_detectavision_cliente.ps1 -LimparBanco"
    Write-Host ""
    exit 1
}

& (Join-Path $projectDir "iniciar_laboratorio_local.ps1")
