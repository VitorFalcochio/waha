$ErrorActionPreference = "Continue"

Set-Location $PSScriptRoot

$containerName = "waha-local"
$sessionsDir = Join-Path $PSScriptRoot ".waha-sessions"
$envFile = Join-Path $PSScriptRoot "waha.env"

if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[WAHA] Docker nao encontrado no PATH."
    exit 1
}

# Se a API ja estiver respondendo, nao faz nada.
try {
    $ok = Invoke-WebRequest -Uri "http://localhost:3000/" -UseBasicParsing -TimeoutSec 2
    if ($ok.StatusCode -ge 200 -and $ok.StatusCode -lt 500) {
        Write-Host "[WAHA] API ja responde em localhost:3000"
        exit 0
    }
} catch {}

if (!(Test-Path $sessionsDir)) {
    New-Item -ItemType Directory -Path $sessionsDir | Out-Null
}

$containerExists = docker ps -a --filter "name=^/$containerName$" --format "{{.Names}}"
if ($containerExists -eq $containerName) {
    docker start $containerName > $null 2>&1
    Write-Host "[WAHA] Container existente iniciado: $containerName"
    exit 0
}

if (!(Test-Path $envFile)) {
    Write-Host "[WAHA] Aviso: waha.env nao encontrado em $envFile. Subindo com defaults."
}

$args = @(
    "run",
    "-d",
    "--name", $containerName,
    "--restart", "unless-stopped",
    "-p", "3000:3000",
    "-e", "NODE_ENV=test",
    "-v", "$sessionsDir`:/app/.sessions"
)

if (Test-Path $envFile) {
    $args += @("--env-file", $envFile)
}

# Algumas instalacoes Linux do Docker Desktop exigem mapeamento explicito.
$args += @("--add-host", "host.docker.internal:host-gateway")
$args += "devlikeapro/waha:latest"

docker @args > $null 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[WAHA] Container criado e iniciado: $containerName"
    exit 0
}

Write-Host "[WAHA] Falha ao iniciar container $containerName."
exit 1
