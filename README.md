# WAHA Print Bot

[![Platform](https://img.shields.io/badge/platform-Windows-0078D6)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://www.python.org/)
[![WAHA](https://img.shields.io/badge/WAHA-Docker-2496ED)](https://github.com/devlikeapro/waha)

Automacao de impressao para pedidos recebidos via WhatsApp.

O projeto conecta WAHA + FastAPI e imprime automaticamente em impressora termica quando a mensagem termina com `#IMPRESSAO`.

## O que este bot faz

- Recebe eventos `message.any` do WAHA
- Filtra apenas mensagens com gatilho na ultima linha
- Remove o gatilho antes de imprimir
- Evita reimpressao com deduplicacao em `state.json`
- Imprime via:
  - ESC/POS por IP (`TCP 9100`)
  - Win32 (`pywin32`)
- Pode iniciar automaticamente com o Windows

## Fluxo em 10 segundos

```text
WhatsApp -> WAHA (Docker) -> /waha/webhook (FastAPI) -> Impressora termica
```

## Instalar em outro PC (via GitHub)

### 1) Clonar o repositorio

```powershell
cd C:\
git clone https://github.com/VitorFalcochio/waha.git Waha
cd C:\Waha
```

Se a pasta ja existir e voce quiser atualizar:

```powershell
cd C:\Waha
git pull origin main
```

### 2) Preparar o Python

```powershell
cd C:\Waha
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn requests pywin32
```

### 3) Criar e ajustar o `waha.env`

```powershell
Copy-Item .\waha.env.example .\waha.env
notepad .\waha.env
```

Campos minimos:

```env
WAHA_API_KEY=SEU_TOKEN
PRINT_MODE=ip
PRINTER_IP=192.168.0.130
TRIGGER=#IMPRESSAO
```

### 4) Subir o sistema

```powershell
cd C:\Waha
powershell -ExecutionPolicy Bypass -File .\run_bot_forever.ps1
```

### 5) Parear e validar

1. Abra `http://localhost:3000/dashboard`
2. Va em `Sessions > default` e escaneie o QR Code
3. Confirme status `WORKING`
4. Valide bot em `http://localhost:8000/health` (esperado: `{"ok":true}`)

## Instalacao Rapida

### 1) Requisitos

- Windows
- Docker Desktop ativo
- Python 3.11+
- Celular com WhatsApp para pareamento

### 2) Preparar ambiente Python

```powershell
cd C:\Waha
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn requests pywin32
```

### 3) Configurar `waha.env`

Copie `waha.env.example` para `waha.env` e ajuste os valores:

```env
WAHA_API_KEY=SEU_TOKEN
PRINT_MODE=ip
PRINTER_IP=192.168.0.130
PRINTER_PORT=9100
TRIGGER=#IMPRESSAO
WAHA_WEBHOOK_URL=http://IP_DO_PC:8000/waha/webhook
```

Para impressora Windows:

```env
PRINT_MODE=win32
PRINTER_NAME=Nome da impressora no Windows
```

### 4) Subir tudo

```powershell
cd C:\Waha
powershell -ExecutionPolicy Bypass -File .\run_bot_forever.ps1
```

Esse script:
- garante o container WAHA em `http://localhost:3000`
- sobe o bot em `http://localhost:8000`
- reinicia automaticamente se o processo cair

### 5) Parear WhatsApp

1. Abra `http://localhost:3000/dashboard`
2. Acesse `Sessions > default`
3. Escaneie o QR Code
4. Confirme status `WORKING`

## Teste de impressao

Envie para seu proprio numero:

```text
PEDIDO #1001
1x X-Burger
1x Suco de Laranja
Observacao: sem cebola
#IMPRESSAO
```

Verificacao:
- WAHA: `http://localhost:3000`
- Bot: `http://localhost:8000/health` retorna `{"ok":true}`

## Inicializacao automatica no Windows

### Instalar

```powershell
cd C:\Waha
powershell -ExecutionPolicy Bypass -File .\install_windows_startup.ps1
```

### Remover

```powershell
cd C:\Waha
powershell -ExecutionPolicy Bypass -File .\uninstall_windows_startup.ps1
```

## Arquivos principais

- `waha.py`: webhook + regras de impressao
- `waha.env`: configuracao local (nao versionar)
- `waha.env.example`: modelo de configuracao
- `run_bot_forever.ps1`: supervisor do bot
- `ensure_waha_container.ps1`: sobe/garante WAHA no Docker
- `install_windows_startup.ps1`: ativa startup
- `uninstall_windows_startup.ps1`: remove startup
- `MANUAL.txt`: instalacao para cliente final

## Troubleshooting

### Sessao nao fica `WORKING`

- Refaca pareamento no dashboard
- Verifique internet do celular
- Confirme que a sessao `default` esta ativa

### Nao imprime

- Validar `PRINT_MODE`, `PRINTER_IP`/`PRINTER_NAME`
- Confirmar `#IMPRESSAO` na ultima linha
- Verificar se o bot esta saudavel em `/health`

### WAHA nao sobe

- Confirmar Docker Desktop ativo
- Executar `ensure_waha_container.ps1` manualmente
- Revisar `logs\bot.err.log`

## Seguranca

- Nunca comitar `waha.env`
- Nunca expor `WAHA_API_KEY`
- Manter o host em rede confiavel
