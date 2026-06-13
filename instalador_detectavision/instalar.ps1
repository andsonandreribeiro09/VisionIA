param(
    [switch]$LimparBanco,
    [switch]$NaoIniciar,
    [string]$LicenseKey = ""
)

$ErrorActionPreference = "Stop"

$sourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installDir = "C:\VisionAI\DetectaVision"
$storeId = "detecta-vision-osasco-001"
$storeName = "Detecta Vision Osasco"
$medicaoUrl = "https://detectavision-medicao.visioniaotica.com.br"
$labUrl = "https://detectavision-lab.visioniaotica.com.br"
$adminUrl = "https://admin.visioniaotica.com.br/admin"
$licenseRequired = if ($LicenseKey) { "1" } else { "0" }
$clientDataDir = Join-Path $installDir "data\clientes\$storeId"
$backupDir = Join-Path $installDir "data\backups"
$dbPath = Join-Path $clientDataDir "visionai.db"
$csvPath = Join-Path $clientDataDir "pacientes_medicoes.csv"
$envPath = Join-Path $installDir ".env.detectavision.local"

function Write-Title($text) {
    Write-Host ""
    Write-Host "== $text =="
}

function Get-BrowserPath {
    $candidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate -PathType Leaf)) {
            return $candidate
        }
    }

    return "explorer.exe"
}

function New-Shortcut($shortcutPath, $targetPath, $arguments, $iconPath) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetPath
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = Split-Path -Parent $targetPath
    if ($iconPath -and (Test-Path $iconPath -PathType Leaf)) {
        $shortcut.IconLocation = $iconPath
    }
    $shortcut.Save()
}

Write-Title "Instalando VisionAI Detecta Vision"
Write-Host "Origem:  $sourceDir"
Write-Host "Destino: $installDir"

New-Item -ItemType Directory -Path $installDir -Force | Out-Null

$exclude = @(
    ".git",
    ".venv",
    "__pycache__",
    "data",
    "pacotes",
    "capturas",
    "instance",
    "instalador_detectavision"
)

Get-ChildItem -LiteralPath $sourceDir -Force | Where-Object {
    $exclude -notcontains $_.Name -and
    $_.Name -notlike ".env*" -and
    $_.Name -notlike "*.db" -and
    $_.Name -ne "pacientes_medicoes.csv"
} | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $installDir -Recurse -Force
}

if (Test-Path (Join-Path $installDir "static\fotos")) {
    Remove-Item -LiteralPath (Join-Path $installDir "static\fotos") -Recurse -Force
}

if (Test-Path (Join-Path $installDir "static\relatorios")) {
    Remove-Item -LiteralPath (Join-Path $installDir "static\relatorios") -Recurse -Force
}

New-Item -ItemType Directory -Path $clientDataDir -Force | Out-Null
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

if ($LimparBanco -or -not (Test-Path $dbPath -PathType Leaf)) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    if (Test-Path $dbPath -PathType Leaf) {
        Move-Item -LiteralPath $dbPath -Destination (Join-Path $backupDir "$storeId-$stamp.db")
    }
    if (Test-Path $csvPath -PathType Leaf) {
        Move-Item -LiteralPath $csvPath -Destination (Join-Path $backupDir "$storeId-$stamp-pacientes_medicoes.csv")
    }
}

@"
# Perfil local da loja Detecta Vision Osasco.
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
VISIONAI_MEDICAO_URL=$medicaoUrl
VISIONAI_LAB_URL=$labUrl
"@ | Set-Content -LiteralPath $envPath -Encoding UTF8

Write-Title "Preparando Python"
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "Python nao encontrado. Instale Python 3.11 ou 3.12 e rode este instalador novamente."
    Write-Host "Download: https://www.python.org/downloads/windows/"
    exit 1
}

$venvDir = Join-Path $installDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython -PathType Leaf)) {
    & $pythonCmd.Source -m venv $venvDir
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $installDir "requirements.txt")

Write-Title "Inicializando banco limpo"
$env:VISIONAI_APP = "medicao"
$env:VISIONAI_DB_MODE = "local"
$env:VISIONAI_USE_RENDER_DB = "0"
$env:VISIONAI_DB_PATH = "data\clientes\$storeId\visionai.db"
$env:VISIONAI_DATA_DIR = "data\clientes\$storeId"
$env:VISIONAI_LOCAL_DB_PATH = $env:VISIONAI_DB_PATH
$env:VISIONAI_LOCAL_DATA_DIR = $env:VISIONAI_DATA_DIR
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
Push-Location $installDir
& $venvPython -c "from visionai_shared import get_db; conn = get_db(); conn.close(); print('Banco inicializado com sucesso.')"
Pop-Location

Write-Title "Configurando Cloudflare Tunnel"
$packageCloudflared = Join-Path $sourceDir "cloudflared"
if (Test-Path $packageCloudflared -PathType Container) {
    $userCloudflared = Join-Path $env:USERPROFILE ".cloudflared"
    New-Item -ItemType Directory -Path $userCloudflared -Force | Out-Null
    Copy-Item -Path (Join-Path $packageCloudflared "*") -Destination $userCloudflared -Recurse -Force
    Write-Host "Configuracao do tunnel copiada para: $userCloudflared"
} else {
    Write-Host "Pasta cloudflared nao encontrada no pacote. Configure o tunnel manualmente se necessario."
}

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    $cloudflaredPath = Get-ChildItem "$env:LOCALAPPDATA" -Recurse -Filter cloudflared.exe -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $cloudflaredPath) {
        Write-Host "cloudflared nao encontrado. Tentando instalar via winget..."
        winget install --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements
    }
}

Write-Title "Criando inicializador"
$startScript = Join-Path $installDir "iniciar_sistema_detectavision.ps1"
@"
`$ErrorActionPreference = "Stop"
`$projectDir = "$installDir"
Set-Location `$projectDir
`$venvScripts = Join-Path `$projectDir ".venv\Scripts"
if (Test-Path (Join-Path `$venvScripts "python.exe")) {
    `$env:Path = "`$venvScripts;`$(`$env:Path)"
}

function Test-Port(`$port) {
    return [bool](Get-NetTCPConnection -LocalPort `$port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-Port 5000)) {
    Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`$projectDir\iniciar_detectavision_medicao.ps1") -WindowStyle Hidden
}

if (-not (Test-Port 5001)) {
    Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`$projectDir\iniciar_detectavision_laboratorio.ps1") -WindowStyle Hidden
}

if (-not (Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`$projectDir\iniciar_tunel_local.ps1") -WindowStyle Hidden
}
"@ | Set-Content -LiteralPath $startScript -Encoding UTF8

Write-Title "Criando icones"
$desktop = [Environment]::GetFolderPath("Desktop")
$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$browser = Get-BrowserPath
$browserArgs = if ($browser -eq "explorer.exe") { $labUrl } else { "--app=$labUrl" }
$powershellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

New-Shortcut `
    -shortcutPath (Join-Path $desktop "VisionAI Laboratorio.lnk") `
    -targetPath $browser `
    -arguments $browserArgs `
    -iconPath $browser

New-Shortcut `
    -shortcutPath (Join-Path $desktop "Iniciar VisionAI Detecta Vision.lnk") `
    -targetPath $powershellExe `
    -arguments "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`"" `
    -iconPath $powershellExe

New-Shortcut `
    -shortcutPath (Join-Path $startup "VisionAI Detecta Vision.lnk") `
    -targetPath $powershellExe `
    -arguments "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`"" `
    -iconPath $powershellExe

if (-not $NaoIniciar) {
    Write-Title "Iniciando sistema"
    & $powershellExe -NoProfile -ExecutionPolicy Bypass -File $startScript
}

Write-Title "Instalacao finalizada"
Write-Host "Medicao:      $medicaoUrl"
Write-Host "Laboratorio:  $labUrl"
Write-Host "Admin:        $adminUrl"
Write-Host "Banco:        $dbPath"
if ($LicenseKey) {
    Write-Host "Licenca:      vinculada ao admin central"
} else {
    Write-Host "Licenca:      nao informada; rode novamente com -LicenseKey para ativar o bloqueio"
}
Write-Host ""
Write-Host "Use o icone 'VisionAI Laboratorio' na area de trabalho."
