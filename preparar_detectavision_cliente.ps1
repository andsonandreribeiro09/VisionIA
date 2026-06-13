param(
    [switch]$LimparBanco,
    [string]$LicenseKey = ""
)

$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

$storeId = "detecta-vision-osasco-001"
$storeName = "Detecta Vision Osasco"
$licenseRequired = if ($LicenseKey) { "1" } else { "0" }
$clientDir = Join-Path $projectDir "data\clientes\$storeId"
$backupDir = Join-Path $projectDir "data\backups"
$dbPath = Join-Path $clientDir "visionai.db"
$envPath = Join-Path $projectDir ".env.detectavision.local"

New-Item -ItemType Directory -Path $clientDir -Force | Out-Null
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

if ($LimparBanco -and (Test-Path $dbPath -PathType Leaf)) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupFile = Join-Path $backupDir "$storeId-$stamp.db"
    Move-Item -LiteralPath $dbPath -Destination $backupFile
    Write-Host "Banco anterior arquivado em: $backupFile"
}

$csvPath = Join-Path $clientDir "pacientes_medicoes.csv"
if ($LimparBanco -and (Test-Path $csvPath -PathType Leaf)) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupCsv = Join-Path $backupDir "$storeId-$stamp-pacientes_medicoes.csv"
    Move-Item -LiteralPath $csvPath -Destination $backupCsv
    Write-Host "CSV anterior arquivado em: $backupCsv"
}

@"
# Perfil local da loja Detecta Vision Osasco.
# Este arquivo fica fora do Git e define banco/dominios da instalacao do cliente.
VISIONAI_DB_MODE=local
VISIONAI_USE_RENDER_DB=0
VISIONAI_LOCAL_DB_PATH=data\clientes\$storeId\visionai.db
VISIONAI_LOCAL_DATA_DIR=data\clientes\$storeId
VISIONAI_MEDICAO_PORT=5000
VISIONAI_LAB_PORT=5001
VISIONAI_STORE_ID=$storeId
VISIONAI_STORE_NAME=$storeName
VISIONAI_LICENSE_SERVER=https://admin.visioniaotica.com.br
VISIONAI_LICENSE_KEY=$LicenseKey
VISIONAI_REQUIRE_LICENSE=$licenseRequired
VISIONAI_MACHINE_ID=DETECTA-VISION-OSASCO-PC01
VISIONAI_LICENSE_GRACE_HOURS=24
VISIONAI_MEDICAO_URL=https://detectavision-medicao.visioniaotica.com.br
VISIONAI_LAB_URL=https://detectavision-lab.visioniaotica.com.br
"@ | Set-Content -LiteralPath $envPath -Encoding UTF8

$env:VISIONAI_APP = "medicao"
$env:VISIONAI_DB_MODE = "local"
$env:VISIONAI_USE_RENDER_DB = "0"
$env:VISIONAI_LOCAL_DB_PATH = "data\clientes\$storeId\visionai.db"
$env:VISIONAI_LOCAL_DATA_DIR = "data\clientes\$storeId"
$env:VISIONAI_DB_PATH = $env:VISIONAI_LOCAL_DB_PATH
$env:VISIONAI_DATA_DIR = $env:VISIONAI_LOCAL_DATA_DIR
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host ""
    Write-Host "Python nao encontrado no PATH."
    Write-Host ""
    exit 1
}

& $pythonCmd.Source -c "from visionai_shared import get_db; conn = get_db(); conn.close(); print('Banco limpo inicializado.')"

Write-Host ""
Write-Host "Loja preparada: $storeName"
Write-Host "Perfil:         $envPath"
Write-Host "Banco limpo:    $dbPath"
Write-Host "CSV:            $csvPath"
Write-Host "Medicao:        https://detectavision-medicao.visioniaotica.com.br"
Write-Host "Laboratorio:    https://detectavision-lab.visioniaotica.com.br"
Write-Host ""
