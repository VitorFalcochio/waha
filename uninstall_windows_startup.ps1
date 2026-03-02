$ErrorActionPreference = "Stop"

$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$startupCmd = Join-Path $startupDir "WahaBotForever.cmd"

if (Test-Path $startupCmd) {
    Remove-Item -Path $startupCmd -Force
    Write-Host "[OK] Startup removido: $startupCmd"
} else {
    Write-Host "[OK] Nenhum startup encontrado para remover."
}
