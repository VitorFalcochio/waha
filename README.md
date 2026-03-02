# WAHA Print Bot (Windows)

Arquivos essenciais:
- `waha.py`: webhook FastAPI + impressao ESC/POS + deduplicacao
- `waha.env`: variaveis do WAHA e do bot
- `run_bot_forever.ps1`: loop de execucao com restart automatico
- `ensure_waha_container.ps1`: garante WAHA Docker na porta 3000
- `install_windows_startup.ps1`: instala inicializacao automatica no login
- `uninstall_windows_startup.ps1`: remove inicializacao automatica

## Rodar manualmente

```powershell
cd C:\Users\Comercial1\Desktop\Waha
powershell -ExecutionPolicy Bypass -File .\run_bot_forever.ps1
```

## Ativar startup no Windows

```powershell
cd C:\Users\Comercial1\Desktop\Waha
powershell -ExecutionPolicy Bypass -File .\install_windows_startup.ps1
```

## Remover startup

```powershell
cd C:\Users\Comercial1\Desktop\Waha
powershell -ExecutionPolicy Bypass -File .\uninstall_windows_startup.ps1
```
