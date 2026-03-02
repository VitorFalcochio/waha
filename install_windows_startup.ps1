$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$runner = Join-Path $PSScriptRoot "run_bot_forever.ps1"
$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$startupCmd = Join-Path $startupDir "WahaBotForever.cmd"

if (!(Test-Path $runner)) {
    throw "Arquivo nao encontrado: $runner"
}

if (!(Test-Path $startupDir)) {
    New-Item -ItemType Directory -Path $startupDir | Out-Null
}

$content = @"
@echo off
cd /d "$PSScriptRoot"
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "$runner"
"@

Set-Content -Path $startupCmd -Value $content -Encoding ASCII

Write-Host "[OK] Startup configurado para o usuario atual."
Write-Host "[OK] Arquivo criado: $startupCmd"
Write-Host "Use o script uninstall_windows_startup.ps1 para remover."
