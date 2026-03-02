import hashlib
import json
import os
import re
import socket
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import quote

import requests
import uvicorn
import win32print
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def is_truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                row = line.strip()
                if not row or row.startswith("#") or "=" not in row:
                    continue
                key, value = row.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
    except Exception:
        pass


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / "waha.env"
load_env_file(ENV_FILE)

# =======================
# CONFIG (edite aqui)
# =======================
TRIGGER = os.getenv("TRIGGER", "#IMPRESSAO").strip() or "#IMPRESSAO"
REMOVE_TRIGGER_FROM_PRINT = is_truthy(os.getenv("REMOVE_TRIGGER_FROM_PRINT"), True)
STATE_FILE = os.getenv("STATE_FILE", "state.json")
MAX_STATE_IDS = read_int_env("MAX_STATE_IDS", 8000)

# Filtro de origem:
# - from_me_only: imprime so mensagens enviadas por voce
# - all: imprime qualquer origem
PRINT_SOURCE_MODE = os.getenv("PRINT_SOURCE_MODE", "from_me_only").strip().lower()
if PRINT_SOURCE_MODE not in {"from_me_only", "all"}:
    PRINT_SOURCE_MODE = "from_me_only"

# Impressao
PRINT_MODE = os.getenv("PRINT_MODE", "auto").strip().lower()  # auto | ip | win32
if PRINT_MODE not in {"auto", "ip", "win32"}:
    PRINT_MODE = "auto"

PRINTER_IP = os.getenv("PRINTER_IP", "192.168.0.130").strip()
PRINTER_PORT = read_int_env("PRINTER_PORT", 9100)
PRINTER_NAME = os.getenv("PRINTER_NAME", "").strip()

MAX_PRINT_RETRIES = read_int_env("MAX_PRINT_RETRIES", 3)
PRINT_RETRY_DELAY_SECONDS = read_float_env("PRINT_RETRY_DELAY_SECONDS", 1.5)
SOCKET_TIMEOUT_SECONDS = read_float_env("SOCKET_TIMEOUT_SECONDS", 5.0)

# WAHA
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://localhost:3000").strip()
WAHA_SESSION = os.getenv("WAHA_SESSION", "default").strip()
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "").strip()
WAHA_EXPECTED_EVENT = os.getenv("WAHA_EXPECTED_EVENT", "message.any").strip().lower()
WAHA_REQUEST_TIMEOUT_SECONDS = read_float_env("WAHA_REQUEST_TIMEOUT_SECONDS", 8.0)

WAHA_SYNC_WEBHOOK_ON_START = is_truthy(os.getenv("WAHA_SYNC_WEBHOOK_ON_START"), True)
WAHA_WEBHOOK_URL = os.getenv("WAHA_WEBHOOK_URL", "").strip()
WAHA_WEBHOOK_HOST = os.getenv("WAHA_WEBHOOK_HOST", "").strip()
WAHA_WEBHOOK_PORT = read_int_env("WAHA_WEBHOOK_PORT", 8000)
WAHA_WEBHOOK_PATH = os.getenv("WAHA_WEBHOOK_PATH", "/waha/webhook").strip() or "/waha/webhook"
if not WAHA_WEBHOOK_PATH.startswith("/"):
    WAHA_WEBHOOK_PATH = f"/{WAHA_WEBHOOK_PATH}"

# Se quiser testar via polling em um chat especifico:
FORCE_CHAT_ID = os.getenv("FORCE_CHAT_ID", "").strip()

TERMINAL_DASHBOARD = is_truthy(os.getenv("TERMINAL_DASHBOARD"), True)
TERMINAL_LIST_LIMIT = read_int_env("TERMINAL_LIST_LIMIT", 12)

TRIGGER_LAST_LINE_RE = re.compile(rf"^\s*{re.escape(TRIGGER)}\s*$", re.IGNORECASE)
TRIGGER_TAIL_RE = re.compile(rf"\n?\s*{re.escape(TRIGGER)}\s*$", re.IGNORECASE)

STATE_LOCK = threading.Lock()
TERMINAL_LOCK = threading.Lock()
TERMINAL_STATUS = "Iniciando..."
TERMINAL_PRINTED: List[Dict[str, str]] = []


def detect_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


def resolve_webhook_url() -> str:
    if WAHA_WEBHOOK_URL:
        return WAHA_WEBHOOK_URL
    host = WAHA_WEBHOOK_HOST or detect_local_ip()
    return f"http://{host}:{WAHA_WEBHOOK_PORT}{WAHA_WEBHOOK_PATH}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    set_terminal_status("Bot online. Aguardando gatilhos...")
    if FORCE_CHAT_ID:
        threading.Thread(target=polling_loop, daemon=True, name="waha-polling").start()
    if WAHA_SYNC_WEBHOOK_ON_START:
        threading.Thread(target=sync_waha_webhook_with_retry, daemon=True, name="waha-webhook-sync").start()
    yield


app = FastAPI(lifespan=lifespan)

# ---------- Estado e Terminal ----------


def load_state() -> Dict[str, Any]:
    state = {"printed_ids": []}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and isinstance(loaded.get("printed_ids"), list):
                state["printed_ids"] = [str(v) for v in loaded["printed_ids"] if v]
        except Exception:
            state["printed_ids"] = []
    state["printed_ids"] = state["printed_ids"][-MAX_STATE_IDS:]
    state["_set"] = set(state["printed_ids"])
    return state


def save_state(state: Dict[str, Any]) -> None:
    temp_file = f"{STATE_FILE}.tmp"
    data = {"printed_ids": state["printed_ids"][-MAX_STATE_IDS:]}
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, STATE_FILE)


STATE = load_state()


def already_printed(msg_id: str) -> bool:
    with STATE_LOCK:
        return msg_id in STATE["_set"]


def remember_printed(msg_id: str) -> None:
    with STATE_LOCK:
        if msg_id in STATE["_set"]:
            return
        STATE["_set"].add(msg_id)
        STATE["printed_ids"].append(msg_id)
        if len(STATE["printed_ids"]) > MAX_STATE_IDS:
            STATE["printed_ids"] = STATE["printed_ids"][-MAX_STATE_IDS:]
            STATE["_set"] = set(STATE["printed_ids"])
        save_state(STATE)


def set_terminal_status(status: str) -> None:
    global TERMINAL_STATUS
    with TERMINAL_LOCK:
        TERMINAL_STATUS = status
    render_dashboard()


def render_dashboard() -> None:
    if not TERMINAL_DASHBOARD:
        return
    with TERMINAL_LOCK:
        os.system("cls" if os.name == "nt" else "clear")
        print(f"=== MONITOR DE IMPRESSAO - WAHA ===\nStatus: {TERMINAL_STATUS}")
        print(f"Trigger: {TRIGGER} | Origem: {PRINT_SOURCE_MODE} | Modo impressao: {PRINT_MODE}\n")
        print("ULTIMOS IMPRESSOS:")
        for item in TERMINAL_PRINTED[-TERMINAL_LIST_LIMIT:]:
            print(f"- [{item['time']}] Chat: {item['chat']}")


# ---------- Gatilho e parsing ----------


def should_print(text: str) -> bool:
    if not text or not text.strip():
        return False
    lines = re.split(r"\r?\n", text.strip())
    for line in reversed(lines):
        if line.strip():
            return bool(TRIGGER_LAST_LINE_RE.match(line))
    return False


def sanitize_for_print(text: str) -> str:
    if not REMOVE_TRIGGER_FROM_PRINT:
        return text.strip()
    return TRIGGER_TAIL_RE.sub("", text.strip()).strip()


def normalize_msg_id(raw_id: Any) -> str:
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()
    if isinstance(raw_id, dict):
        for key in ("_serialized", "id", "_id"):
            value = raw_id.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        parts = [str(raw_id.get(k, "")) for k in ("remote", "id", "participant", "fromMe")]
        joined = "|".join(parts).strip("|")
        if joined:
            return hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return ""


def make_fallback_id(chat_id: str, text: str, timestamp: Any) -> str:
    raw = f"{chat_id}|{timestamp}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_event_and_payload(data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    event = str(data.get("event") or data.get("eventName") or "").strip()
    payload = data.get("payload")
    if not isinstance(payload, dict):
        payload = data.get("data")
    if not isinstance(payload, dict):
        payload = data
    return event, payload


def extract_text(payload: Dict[str, Any]) -> str:
    if isinstance(payload.get("body"), str):
        return payload["body"]
    if isinstance(payload.get("text"), str):
        return payload["text"]
    if isinstance(payload.get("message"), str):
        return payload["message"]
    if isinstance(payload.get("message"), dict):
        msg = payload["message"]
        for key in ("body", "text", "conversation"):
            if isinstance(msg.get(key), str):
                return msg[key]
    return ""


def extract_from_me(payload: Dict[str, Any]) -> bool:
    if isinstance(payload.get("fromMe"), bool):
        return payload["fromMe"]
    if isinstance(payload.get("message"), dict) and isinstance(payload["message"].get("fromMe"), bool):
        return payload["message"]["fromMe"]
    if isinstance(payload.get("id"), dict) and isinstance(payload["id"].get("fromMe"), bool):
        return payload["id"]["fromMe"]
    return False


# ---------- WAHA webhook sync ----------


def _waha_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    return headers


def sync_waha_webhook_once() -> bool:
    if not WAHA_API_KEY:
        return True

    target_url = resolve_webhook_url()
    session_url = f"{WAHA_BASE_URL}/api/sessions/{WAHA_SESSION}"
    headers = _waha_headers()

    try:
        response = requests.get(session_url, headers=headers, timeout=WAHA_REQUEST_TIMEOUT_SECONDS)
        if response.status_code != 200:
            return False

        session_info = response.json() if response.content else {}
        config = session_info.get("config") if isinstance(session_info, dict) else None
        config = config if isinstance(config, dict) else {}
        webhooks = config.get("webhooks") if isinstance(config.get("webhooks"), list) else []

        already_configured = any(
            isinstance(item, dict)
            and item.get("url") == target_url
            and WAHA_EXPECTED_EVENT in (item.get("events") or [])
            for item in webhooks
        )
        if already_configured:
            return True

        new_config = dict(config)
        new_config["webhooks"] = [{"url": target_url, "events": [WAHA_EXPECTED_EVENT]}]
        update = requests.put(
            session_url,
            headers=headers,
            json={"config": new_config},
            timeout=WAHA_REQUEST_TIMEOUT_SECONDS,
        )
        return update.status_code in {200, 201}
    except Exception:
        return False


def sync_waha_webhook_with_retry() -> None:
    if not WAHA_API_KEY:
        set_terminal_status("WAHA_API_KEY ausente. Sincronizacao de webhook ignorada.")
        return
    for _ in range(12):
        if sync_waha_webhook_once():
            set_terminal_status("Webhook WAHA sincronizado com sucesso.")
            return
        time.sleep(5)
    set_terminal_status("Nao foi possivel sincronizar webhook no WAHA automaticamente.")


# ---------- Impressao ESC/POS ----------


def build_escpos_payload(content: str) -> bytes:
    cmd_init = b"\x1b\x40"
    cmd_center = b"\x1b\x61\x01"
    cmd_left = b"\x1b\x61\x00"
    cmd_bold_on = b"\x1b\x45\x01"
    cmd_bold_off = b"\x1b\x45\x00"
    cmd_double_size = b"\x1d\x21\x11"  # fonte dupla (altura/largura)
    cmd_normal_size = b"\x1d\x21\x00"
    cmd_feed = b"\x1b\x64\x06"
    cmd_cut = b"\x1d\x56\x00"

    header = (
        cmd_center
        + cmd_double_size
        + cmd_bold_on
        + "NOVO PEDIDO\n\n".encode("cp850", errors="ignore")
        + cmd_normal_size
        + cmd_bold_off
    )
    body = (content + "\n").encode("cp850", errors="ignore")
    return cmd_init + header + cmd_left + body + cmd_feed + cmd_cut


def print_via_ip(payload: bytes) -> None:
    last_error = None
    for attempt in range(1, MAX_PRINT_RETRIES + 1):
        try:
            with socket.create_connection((PRINTER_IP, PRINTER_PORT), timeout=SOCKET_TIMEOUT_SECONDS) as sock:
                sock.sendall(payload)
            return
        except OSError as exc:
            last_error = exc
            if attempt < MAX_PRINT_RETRIES:
                time.sleep(PRINT_RETRY_DELAY_SECONDS * attempt)
    raise RuntimeError(
        f"Falha ao imprimir via IP {PRINTER_IP}:{PRINTER_PORT} apos {MAX_PRINT_RETRIES} tentativas: {last_error}"
    )


def print_via_win32(payload: bytes) -> None:
    if not PRINTER_NAME:
        raise RuntimeError("PRINTER_NAME nao configurado para modo win32.")

    last_error = None
    for attempt in range(1, MAX_PRINT_RETRIES + 1):
        printer = None
        try:
            printer = win32print.OpenPrinter(PRINTER_NAME)
            win32print.StartDocPrinter(printer, 1, ("Cupom WAHA", None, "RAW"))
            win32print.StartPagePrinter(printer)
            win32print.WritePrinter(printer, payload)
            win32print.EndPagePrinter(printer)
            win32print.EndDocPrinter(printer)
            return
        except Exception as exc:
            last_error = exc
            if attempt < MAX_PRINT_RETRIES:
                time.sleep(PRINT_RETRY_DELAY_SECONDS * attempt)
        finally:
            if printer is not None:
                try:
                    win32print.ClosePrinter(printer)
                except Exception:
                    pass
    raise RuntimeError(
        f"Falha ao imprimir via Win32 na impressora '{PRINTER_NAME}' apos {MAX_PRINT_RETRIES} tentativas: {last_error}"
    )


def print_receipt(text: str) -> None:
    payload = build_escpos_payload(text)
    errors: List[str] = []

    if PRINT_MODE in ("ip", "auto"):
        if PRINTER_IP:
            try:
                print_via_ip(payload)
                return
            except Exception as exc:
                errors.append(str(exc))
                if PRINT_MODE == "ip":
                    raise
        elif PRINT_MODE == "ip":
            raise RuntimeError("PRINTER_IP nao configurado para modo ip.")

    if PRINT_MODE in ("win32", "auto"):
        try:
            print_via_win32(payload)
            return
        except Exception as exc:
            errors.append(str(exc))
            if PRINT_MODE == "win32":
                raise

    raise RuntimeError(" | ".join(errors) if errors else "Nenhum metodo de impressao configurado.")


# ---------- Pipeline ----------


def handle_message_pipeline(payload: Dict[str, Any], source: str, event: str = "") -> Dict[str, Any]:
    text = extract_text(payload).strip()
    chat_id = str(payload.get("chatId") or payload.get("from") or "unknown")
    from_me = extract_from_me(payload)

    if not text:
        return {"ok": True, "skip": "vazio"}

    if PRINT_SOURCE_MODE == "from_me_only" and not from_me:
        return {"ok": True, "skip": "nao_enviado_por_mim"}

    if not should_print(text):
        return {"ok": True, "skip": "sem_gatilho_na_ultima_linha"}

    msg_id = normalize_msg_id(payload.get("id")) or make_fallback_id(
        chat_id=chat_id,
        text=text,
        timestamp=payload.get("timestamp") or payload.get("t"),
    )

    if already_printed(msg_id):
        return {"ok": True, "skip": "duplicado"}

    to_print = sanitize_for_print(text)

    try:
        print_receipt(to_print)
        remember_printed(msg_id)
        entry = {"time": datetime.now().strftime("%H:%M"), "chat": chat_id, "msg_id": msg_id}
        with TERMINAL_LOCK:
            TERMINAL_PRINTED.append(entry)
        set_terminal_status("Pedido impresso com sucesso!")
        return {"ok": True, "printed": True, "message_id": msg_id, "source": source, "event": event}
    except Exception as exc:
        set_terminal_status(f"Erro ao imprimir: {exc}")
        return {"ok": False, "error": str(exc), "message_id": msg_id}


# ---------- Endpoints e loops ----------


@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}


@app.post("/waha/webhook")
async def waha_webhook(request: Request) -> JSONResponse:
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "json_invalido"})

    if not isinstance(data, dict):
        return JSONResponse(status_code=400, content={"ok": False, "error": "payload_invalido"})

    event, payload = extract_event_and_payload(data)
    event_lc = event.lower() if event else ""
    if event_lc and event_lc != WAHA_EXPECTED_EVENT:
        return JSONResponse(status_code=200, content={"ok": True, "skip": f"evento_ignorado:{event}"})

    result = handle_message_pipeline(payload, source="webhook", event=event_lc)
    status = 200 if result.get("ok") else 500
    return JSONResponse(status_code=status, content=result)


def polling_loop() -> None:
    set_terminal_status(f"Polling ativo no chat: {FORCE_CHAT_ID}")
    while True:
        try:
            url = f"{WAHA_BASE_URL}/api/{WAHA_SESSION}/chats/{quote(FORCE_CHAT_ID)}/messages?limit=10"
            headers = {"X-Api-Key": WAHA_API_KEY} if WAHA_API_KEY else {}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                msgs = response.json()
                if isinstance(msgs, list):
                    for msg in msgs:
                        if isinstance(msg, dict):
                            handle_message_pipeline(msg, source="polling")
        except Exception:
            pass
        time.sleep(2)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
