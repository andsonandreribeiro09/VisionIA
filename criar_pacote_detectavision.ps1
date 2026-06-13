$ErrorActionPreference = "Stop"

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

$packageRoot = Join-Path $projectDir "pacotes"
$stageDir = Join-Path $packageRoot "DetectaVision-Cliente"
$zipPath = Join-Path $packageRoot "DetectaVision-Cliente.zip"
$cloudflaredDir = Join-Path $env:USERPROFILE ".cloudflared"

New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null

if (Test-Path $stageDir) {
    Remove-Item -LiteralPath $stageDir -Recurse -Force
}

if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

$files = @(
    "admin_app.py",
    "app.py",
    "database.py",
    "face_landmarker.task",
    "laboratorio_app.py",
    "medicao_app.py",
    "requirements.txt",
    "requirements_laboratorio.txt",
    "requirements_admin.txt",
    "vision_engine.py",
    "visionai_shared.py",
    "iniciar_medicao_local.ps1",
    "iniciar_laboratorio_local.ps1",
    "iniciar_tunel_local.ps1",
    "iniciar_detectavision_medicao.ps1",
    "iniciar_detectavision_laboratorio.ps1",
    "preparar_detectavision_cliente.ps1",
    "INSTALACAO_DETECTA_VISION.md",
    "COMO_RODAR_LOCAL.md"
)

foreach ($file in $files) {
    Copy-Item -LiteralPath (Join-Path $projectDir $file) -Destination $stageDir -Force
}

Copy-Item -LiteralPath (Join-Path $projectDir "templates") -Destination $stageDir -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectDir "static") -Destination $stageDir -Recurse -Force

foreach ($generatedDir in @("static\fotos", "static\relatorios")) {
    $path = Join-Path $stageDir $generatedDir
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

Copy-Item -LiteralPath (Join-Path $projectDir "instalador_detectavision\instalar.ps1") -Destination (Join-Path $stageDir "instalar.ps1") -Force

if (Test-Path $cloudflaredDir -PathType Container) {
    $stageCloudflared = Join-Path $stageDir "cloudflared"
    New-Item -ItemType Directory -Path $stageCloudflared -Force | Out-Null

    foreach ($item in @("config.yml", "2a5c26a2-054a-4779-96b0-8d14a69572f0.json", "cert.pem")) {
        $source = Join-Path $cloudflaredDir $item
        if (Test-Path $source -PathType Leaf) {
            Copy-Item -LiteralPath $source -Destination $stageCloudflared -Force
        }
    }
}

Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath -Force

Write-Host ""
Write-Host "Pacote criado:"
Write-Host $zipPath
Write-Host ""
Write-Host "ATENCAO: este ZIP pode conter credenciais do Cloudflare Tunnel."
Write-Host "Nao publique esse arquivo no GitHub. Use apenas para instalar no PC da loja."
Write-Host ""
