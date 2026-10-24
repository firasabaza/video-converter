# Installation du convertisseur vidéo sous Windows.
# Installe FFmpeg et uv avec winget si besoin, puis les dépendances Python.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Say($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User") + ";$env:USERPROFILE\.local\bin"
}

Say "FFmpeg"
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "winget est introuvable. Installez « App Installer » depuis le Microsoft Store, ou FFmpeg depuis https://www.gyan.dev/ffmpeg/builds/"
        exit 1
    }
    # Version « full » de Gyan : inclut NVENC, Quick Sync (QSV) et AMF.
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    Refresh-Path
}
ffmpeg -hide_banner -version | Select-Object -First 1

Say "uv (gestionnaire Python)"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    Refresh-Path
}
uv --version

Say "Dépendances Python"
uv sync --no-dev

Say "Accélération matérielle détectée"
uv run --no-dev video-converter encoders

Say "Installation terminée"
Write-Host "Lancez l'application en double-cliquant sur start.bat"
