$ErrorActionPreference = "Continue"

Set-Location $PSScriptRoot

$logsDir = Join-Path $PSScriptRoot "logs"
if (!(Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

$outLog = Join-Path $logsDir "bot.out.log"
$errLog = Join-Path $logsDir "bot.err.log"
$python = Join-Path $PSScriptRoot ".venv\\Scripts\\python.exe"
$wahaPy = Join-Path $PSScriptRoot "waha.py"
$ensureWaha = Join-Path $PSScriptRoot "ensure_waha_container.ps1"

if (!(Test-Path $python)) {
    Add-Content -Path $errLog -Value ("[{0}] Python nao encontrado em {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $python)
    exit 1
}

if (!(Test-Path $wahaPy)) {
    Add-Content -Path $errLog -Value ("[{0}] Arquivo nao encontrado: {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $wahaPy)
    exit 1
}

while ($true) {
    $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        Add-Content -Path $outLog -Value ("[{0}] Porta 8000 ja ocupada (PID={1}). Aguardando..." -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $listener.OwningProcess)
        Start-Sleep -Seconds 10
        continue
    }

    try {
        if (Test-Path $ensureWaha) {
            & $ensureWaha 1>> $outLog 2>> $errLog
        }
    } catch {
        Add-Content -Path $errLog -Value ("[{0}] Falha ao garantir container WAHA: {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $_.Exception.Message)
    }

    Add-Content -Path $outLog -Value ("[{0}] Iniciando bot..." -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))

    & $python $wahaPy 1>> $outLog 2>> $errLog
    $exitCode = $LASTEXITCODE

    Add-Content -Path $errLog -Value ("[{0}] Bot encerrou (code={1}). Reiniciando em 5s..." -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $exitCode)
    Start-Sleep -Seconds 5
}
