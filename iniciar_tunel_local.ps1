$ErrorActionPreference = "Stop"

$port = if ($env:PORT) { $env:PORT } else { "5000" }
$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue

if ($cloudflared) {
    $cloudflaredPath = $cloudflared.Source
} else {
    $cloudflaredPath = Get-ChildItem "$env:LOCALAPPDATA" -Recurse -Filter cloudflared.exe -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}

if (-not $cloudflaredPath) {
    Write-Host ""
    Write-Host "cloudflared nao encontrado."
    Write-Host "Instale com: winget install --id Cloudflare.cloudflared"
    Write-Host ""
    exit 1
}

Write-Host "Abrindo tunel HTTPS para http://localhost:$port"
Write-Host "Copie a URL https://...trycloudflare.com que aparecer e abra no tablet."
Write-Host ""

& $cloudflaredPath tunnel --url "http://localhost:$port"
