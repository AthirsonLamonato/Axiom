"""
web/app.py — Dashboard web local do Paçoca
Inicie com: python -m uvicorn web.app:app --host 127.0.0.1 --port 7755
Ou via voz: 'abre o dashboard' / 'python main.py --web'
"""

import asyncio
import hashlib
import hmac
import html as html_lib
import json
import logging
import queue as _queue_module
import secrets
import threading
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urlsplit

logger = logging.getLogger(__name__)

_orchestrator = None
_web_password: str = ""
DEFAULT_PORT = 7755

# Token sincronizador de CSRF — gerado uma vez por processo, injetado nas páginas
# autenticadas via hx-headers (htmx) e validado nas rotas POST que alteram estado.
_CSRF_TOKEN = secrets.token_urlsafe(32)

# ── Sessão: cookie assinado (HMAC) com timestamp de emissão embutido ──
# Diferente de um simples hash da senha, o cookie por si só carrega quando foi
# emitido — não depende de um relógio em memória compartilhado entre clientes
# (cada sessão expira pela própria idade, não por um "_last_seen" global), e
# reiniciar o processo invalida sessões antigas automaticamente (chave nova).
_SESSION_SECRET = secrets.token_urlsafe(32)


def _session_timeout_s() -> int:
    try:
        from core.config import Config
        return max(1, int(Config().get("security.session_timeout_min", 30))) * 60
    except Exception:
        return 1800


def _sign_session(ts: str) -> str:
    msg = f"{_token_for(_web_password)}.{ts}".encode()
    return hmac.new(_SESSION_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def _make_session_cookie() -> str:
    ts = str(int(time.time()))
    return f"{ts}.{_sign_session(ts)}"


def _valid_session_cookie(token: str) -> bool:
    """Valida assinatura e expiração por inatividade (security.session_timeout_min)."""
    if not _web_password:
        return True
    ts_str, _, sig = token.partition(".")
    if not sig or not hmac.compare_digest(sig, _sign_session(ts_str)):
        return False
    try:
        ts = int(ts_str)
    except ValueError:
        return False
    return (time.time() - ts) <= _session_timeout_s()


# ── Rate limiting de login (por IP) ───────────────────────────────────
_login_attempts: dict = {}
_login_attempts_lock = threading.Lock()


def _login_max_attempts() -> int:
    try:
        from core.config import Config
        return max(1, int(Config().get("security.login_max_attempts", 5)))
    except Exception:
        return 5


def _login_window_s() -> int:
    try:
        from core.config import Config
        return max(1, int(Config().get("security.login_window_s", 60)))
    except Exception:
        return 60


def _login_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    window = _login_window_s()
    with _login_attempts_lock:
        # Varre todas as IPs (não só a atual) para não acumular entradas
        # esquecidas de IPs que tentaram uma vez e nunca mais voltaram.
        for other_ip in [k for k, v in _login_attempts.items()
                          if not any(now - t < window for t in v)]:
            del _login_attempts[other_ip]
        attempts = [t for t in _login_attempts.get(ip, []) if now - t < window]
        if attempts:
            _login_attempts[ip] = attempts
        else:
            _login_attempts.pop(ip, None)
        return len(attempts) >= _login_max_attempts()


def _record_login_failure(ip: str) -> None:
    with _login_attempts_lock:
        _login_attempts.setdefault(ip, []).append(time.monotonic())


# ── Heartbeat de WebSocket ─────────────────────────────────────────────
_WS_PING_INTERVAL_S = 30
_WS_PONG_TIMEOUT_S = 90

# ── Bus de eventos (thread-safe → WebSocket clients) ─────────────────
_event_queues: list = []
_event_queues_lock = threading.Lock()


def push_event(event_type: str, message: str) -> None:
    """Envia evento para todos os clientes WebSocket conectados. Thread-safe."""
    payload = json.dumps({
        "type": event_type,
        "message": message,
        "ts": datetime.now().strftime("%H:%M:%S"),
    })
    with _event_queues_lock:
        for q in list(_event_queues):
            try:
                q.put_nowait(payload)
            except _queue_module.Full:
                pass


def set_orchestrator(orc) -> None:
    global _orchestrator
    _orchestrator = orc


def set_password(pwd: str) -> None:
    global _web_password
    _web_password = pwd.strip()


def _token_for(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _password_correct(password: str) -> bool:
    if not _web_password:
        return True
    return hmac.compare_digest(_token_for(password), _token_for(_web_password))


def _valid_websocket(websocket) -> bool:
    token = websocket.cookies.get("pacoca_token", "")
    if not _valid_session_cookie(token):
        return False

    origin = websocket.headers.get("origin", "")
    host = websocket.headers.get("host", "")
    if origin and urlsplit(origin).netloc != host:
        return False
    return True


# ── Factory do app ────────────────────────────────────────────────────

def _make_app():
    try:
        from fastapi import (
            FastAPI, Form, Request, WebSocket, WebSocketDisconnect,
        )
        from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
        from starlette.middleware.base import BaseHTTPMiddleware
    except ImportError:
        return None

    app = FastAPI(title="Paçoca Dashboard", docs_url=None, redoc_url=None)

    # ── Middleware de autenticação ─────────────────────────────────────
    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if not _web_password:
                return await call_next(request)
            skip = {"/login", "/favicon.ico"}
            if request.url.path in skip or request.url.path.startswith("/ws"):
                return await call_next(request)
            token = request.cookies.get("pacoca_token", "")
            if not _valid_session_cookie(token):
                resp = RedirectResponse("/login")
                resp.delete_cookie("pacoca_token")
                return resp
            resp = await call_next(request)
            # Renova o cookie a cada requisição (sessão "deslizante" por
            # inatividade) — cada cliente tem seu próprio timestamp, sem
            # depender de um relógio global compartilhado.
            resp.set_cookie(
                "pacoca_token", _make_session_cookie(),
                httponly=True, samesite="strict",
            )
            return resp

    app.add_middleware(AuthMiddleware)

    # ── HTML ──────────────────────────────────────────────────────────

    _LOGIN_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"><title>Paçoca — Login</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',monospace;
       display:flex;align-items:center;justify-content:center;height:100vh}}
  .card{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:32px;width:320px}}
  h1{{color:#58a6ff;font-size:1.4em;letter-spacing:2px;margin-bottom:24px}}
  input{{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:8px 12px;
         border-radius:6px;width:100%;font-size:14px;outline:none}}
  input:focus{{border-color:#58a6ff}}
  button{{background:#238636;color:#fff;border:none;border-radius:6px;
          padding:8px 16px;cursor:pointer;font-size:14px;width:100%;margin-top:12px}}
  button:hover{{background:#2ea043}}
  .err{{color:#f85149;font-size:0.85em;margin-top:10px}}
</style>
</head>
<body>
<div class="card">
  <h1>⚡ Paçoca</h1>
  <form method="post" action="/login">
    <input type="password" name="password" placeholder="Senha do dashboard" autofocus>
    <button type="submit">Entrar</button>
  </form>
  {error}
</div>
</body></html>"""

    _HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Paçoca Dashboard</title>
<script src="https://unpkg.com/htmx.org@1.9.10"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0d1117; color: #c9d1d9; font-family: 'Segoe UI', monospace;
    padding: 24px; font-size: 14px;
  }
  h1 { color: #58a6ff; font-size: 1.4em; margin-bottom: 16px; letter-spacing: 2px; }
  h2 { color: #8b949e; font-size: 0.75em; text-transform: uppercase;
       letter-spacing: 1px; margin-bottom: 10px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
  .card {
    background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 16px;
  }
  .card.full { grid-column: 1 / -1; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 12px;
           font-size: 0.78em; font-weight: bold; margin: 2px; }
  .badge-work    { background: #1f3a5f; color: #58a6ff; }
  .badge-casual  { background: #2d2040; color: #c084fc; }
  .badge-focus   { background: #3d1c1c; color: #f85149; }
  .badge-meeting { background: #1c3328; color: #3fb950; }
  .badge-night   { background: #1c1c2e; color: #8b949e; }
  .badge-default { background: #21262d; color: #c9d1d9; }
  .stat-row { display: flex; gap: 24px; flex-wrap: wrap; }
  .stat { text-align: center; }
  .stat-val { font-size: 1.8em; font-weight: bold; color: #58a6ff; }
  .stat-lbl { font-size: 0.7em; color: #8b949e; text-transform: uppercase; }
  .cmd-row { display: flex; gap: 8px; }
  input[type=text], input[type=password] {
    background: #0d1117; border: 1px solid #30363d; color: #c9d1d9;
    padding: 8px 12px; border-radius: 6px; flex: 1;
    font-size: 14px; outline: none;
  }
  input[type=text]:focus, input[type=password]:focus { border-color: #58a6ff; }
  button {
    background: #238636; color: #fff; border: none; border-radius: 6px;
    padding: 8px 16px; cursor: pointer; font-size: 14px;
  }
  button:hover { background: #2ea043; }
  button.danger { background: #6e1a1a; }
  button.danger:hover { background: #8b2020; }
  .response-box {
    background: #0d1117; border-left: 3px solid #58a6ff;
    padding: 10px 14px; border-radius: 0 6px 6px 0;
    margin-top: 12px; white-space: pre-wrap; color: #79c0ff; font-size: 0.9em;
  }
  .connecting { border-left-color: #8b949e; color: #8b949e; }
  table { width: 100%; border-collapse: collapse; }
  th { color: #8b949e; font-size: 0.72em; text-transform: uppercase;
       padding: 6px 8px; text-align: left; border-bottom: 1px solid #21262d; }
  td { padding: 6px 8px; border-bottom: 1px solid #161b22; font-size: 0.88em; }
  td.ts   { color: #8b949e; white-space: nowrap; width: 80px; }
  td.cmd  { color: #c9d1d9; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  td.resp { color: #8b949e; font-size: 0.85em; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .reminder-row { padding: 6px 0; border-bottom: 1px solid #21262d; }
  .reminder-row:last-child { border-bottom: none; }
  .reminder-time { color: #58a6ff; font-weight: bold; margin-right: 8px; }
  .event-row { padding: 5px 0; border-bottom: 1px solid #21262d; font-size: 0.88em; }
  .event-row:last-child { border-bottom: none; }
  .event-ts  { color: #8b949e; margin-right: 6px; font-size: 0.8em; }
  .event-type-reminder { color: #f0883e; }
  .event-type-meeting  { color: #3fb950; }
  .event-type-info     { color: #58a6ff; }
  .routine-row { display: flex; align-items: center; justify-content: space-between;
                 padding: 6px 0; border-bottom: 1px solid #21262d; }
  .routine-row:last-child { border-bottom: none; }
  .routine-name { color: #58a6ff; font-weight: bold; margin-right: 8px; }
  .routine-steps { color: #8b949e; font-size: 0.82em; }
  .add-form { margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
  .add-form input { min-width: 120px; flex: 1; }
  .empty { color: #8b949e; font-style: italic; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  #ws-status { font-size: 0.72em; color: #8b949e; margin-left: 8px; }
  #ws-status.ok { color: #3fb950; }
</style>
</head>
<body>
<h1>⚡ Paçoca <span id="ws-status">● conectando...</span></h1>
<p style="color:#8b949e;font-size:0.82em;margin-bottom:16px">
  <a href="/" style="color:#58a6ff">Dashboard</a> · <a href="/metrics">Métricas</a> · <a href="/integrations">Integrações</a> · <a href="/docs">Documentação</a>
</p>

<div class="grid">
  <!-- Status -->
  <div class="card">
    <h2>Status</h2>
    <div id="status-block"
         hx-get="/api/status-html"
         hx-trigger="load, every 10s"
         hx-swap="innerHTML">Carregando...</div>
  </div>

  <!-- Stats -->
  <div class="card">
    <h2>Sessão</h2>
    <div id="stats-block"
         hx-get="/api/stats-html"
         hx-trigger="load, every 15s"
         hx-swap="innerHTML">Carregando...</div>
  </div>

  <!-- Comando (WebSocket) -->
  <div class="card full">
    <h2>Enviar Comando</h2>
    <div class="cmd-row">
      <input type="text" id="cmd-input" placeholder="Digite um comando... (suporta 'e depois', 'em seguida')" autofocus>
      <button onclick="sendCommand()">Enviar</button>
    </div>
    <div id="cmd-response"></div>
  </div>

  <!-- Lembretes -->
  <div class="card">
    <h2>Lembretes</h2>
    <div id="reminders-block"
         hx-get="/api/reminders-html"
         hx-trigger="load, every 15s"
         hx-swap="innerHTML">Carregando...</div>
  </div>

  <!-- Eventos ao vivo -->
  <div class="card">
    <h2>Eventos ao vivo</h2>
    <div id="events-list"><div class="empty">Aguardando eventos...</div></div>
  </div>

  <!-- Contexto -->
  <div class="card">
    <h2>Contexto da Sessão</h2>
    <div id="context-block"
         hx-get="/api/context-html"
         hx-trigger="load, every 20s"
         hx-swap="innerHTML">Carregando...</div>
  </div>

  <!-- Rotinas -->
  <div class="card">
    <h2>Rotinas</h2>
    <div id="routines-block"
         hx-get="/api/routines-html"
         hx-trigger="load"
         hx-swap="innerHTML">Carregando...</div>
  </div>

  <!-- Histórico -->
  <div class="card full">
    <h2>Histórico de Comandos</h2>
    <div id="history-block"
         hx-get="/api/history-html"
         hx-trigger="load, every 8s"
         hx-swap="innerHTML">Carregando...</div>
  </div>
</div>

<p style="color:#8b949e;font-size:0.72em;text-align:center;margin-top:8px;">
  Paçoca Dashboard — <a href="/api/status">JSON</a>
</p>

<script>
// ── WebSocket: comando ────────────────────────────────────────────────
let cmdWs;
function connectCmdWs() {
  const wsScheme = location.protocol === 'https:' ? 'wss://' : 'ws://';
  cmdWs = new WebSocket(wsScheme + location.host + '/ws/command');
  cmdWs.onopen = () => {
    document.getElementById('ws-status').textContent = '● online';
    document.getElementById('ws-status').className = 'ok';
  };
  cmdWs.onmessage = (e) => {
    if (e.data.startsWith('{')) {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'ping') { cmdWs.send(JSON.stringify({type: 'pong'})); return; }
      } catch {}
    }
    document.getElementById('cmd-response').innerHTML = e.data;
  };
  cmdWs.onclose = () => {
    document.getElementById('ws-status').textContent = '● reconectando...';
    document.getElementById('ws-status').className = '';
    setTimeout(connectCmdWs, 2000);
  };
}
connectCmdWs();

function sendCommand() {
  const input = document.getElementById('cmd-input');
  const cmd = input.value.trim();
  if (!cmd) return;
  if (!cmdWs || cmdWs.readyState !== WebSocket.OPEN) {
    document.getElementById('cmd-response').innerHTML =
      '<div class="response-box connecting">Reconectando ao servidor...</div>';
    return;
  }
  document.getElementById('cmd-response').innerHTML =
    '<div class="response-box connecting">Processando...</div>';
  cmdWs.send(JSON.stringify({command: cmd}));
  input.value = '';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('cmd-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendCommand();
  });
});

// ── WebSocket: eventos ao vivo ────────────────────────────────────────
let evtWs;
function connectEvtWs() {
  const wsScheme = location.protocol === 'https:' ? 'wss://' : 'ws://';
  evtWs = new WebSocket(wsScheme + location.host + '/ws/events');
  evtWs.onmessage = (e) => {
    let evt;
    try { evt = JSON.parse(e.data); } catch { return; }
    if (evt.type === 'ping') { evtWs.send(JSON.stringify({type: 'pong'})); return; }
    const list = document.getElementById('events-list');
    const empty = list.querySelector('.empty');
    if (empty) empty.remove();
    const div = document.createElement('div');
    div.className = 'event-row';
    const eventType = ['reminder', 'meeting', 'info'].includes(evt.type) ? evt.type : 'info';
    const ts = document.createElement('span');
    ts.className = 'event-ts';
    ts.textContent = evt.ts || '';
    const type = document.createElement('span');
    type.className = 'event-type-' + eventType;
    type.textContent = '[' + eventType + ']';
    div.append(ts, type, document.createTextNode(' ' + (evt.message || '')));
    list.prepend(div);
    while (list.children.length > 6) list.removeChild(list.lastChild);
  };
  evtWs.onclose = () => setTimeout(connectEvtWs, 3000);
}
connectEvtWs();
</script>
</body>
</html>"""

    # ── Rotas de autenticação ─────────────────────────────────────────

    @app.get("/login", response_class=HTMLResponse)
    async def login_page():
        return HTMLResponse(_LOGIN_HTML.format(error=""))

    @app.post("/login")
    async def login_post(request: Request, password: str = Form(...)):
        ip = request.client.host if request.client else "unknown"
        if _login_rate_limited(ip):
            return HTMLResponse(
                _LOGIN_HTML.format(
                    error='<p class="err">Muitas tentativas. Aguarde 1 minuto.</p>'
                ),
                status_code=429,
            )
        if _password_correct(password):
            resp = RedirectResponse("/", status_code=303)
            resp.set_cookie(
                "pacoca_token", _make_session_cookie(),
                httponly=True, samesite="strict",
            )
            return resp
        _record_login_failure(ip)
        return HTMLResponse(
            _LOGIN_HTML.format(error='<p class="err">Senha incorreta.</p>'),
            status_code=401,
        )

    @app.get("/logout")
    async def logout():
        resp = RedirectResponse("/login")
        resp.delete_cookie("pacoca_token")
        return resp

    # ── Dashboard principal ───────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        page = _HTML.replace(
            "<body>",
            f'<body hx-headers=\'{{"X-CSRF-Token": "{_CSRF_TOKEN}"}}\'>',
            1,
        )
        return HTMLResponse(content=page)

    # ── WebSocket: execução de comandos ───────────────────────────────

    @app.websocket("/ws/command")
    async def ws_command(websocket: WebSocket):
        if not _valid_websocket(websocket):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        # Token capturado na conexão — sua validade (assinatura + idade)
        # é reavaliada periodicamente, sem precisar de estado global.
        session_token = websocket.cookies.get("pacoca_token", "")
        last_activity = time.monotonic()
        try:
            while True:
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_text(), timeout=_WS_PING_INTERVAL_S
                    )
                except asyncio.TimeoutError:
                    if time.monotonic() - last_activity > _WS_PONG_TIMEOUT_S:
                        logger.info("ws_command: heartbeat sem resposta, encerrando conexão")
                        break
                    if not _valid_session_cookie(session_token):
                        logger.info("ws_command: sessão expirada, encerrando conexão")
                        break
                    await websocket.send_text(json.dumps({"type": "ping"}))
                    continue
                if not _valid_session_cookie(session_token):
                    logger.info("ws_command: sessão expirada, encerrando conexão")
                    break
                last_activity = time.monotonic()
                try:
                    payload = json.loads(data)
                    if payload.get("type") == "pong":
                        continue
                    cmd = payload.get("command", "").strip()
                except Exception:
                    cmd = data.strip()
                if not cmd:
                    continue
                if _orchestrator:
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None, _orchestrator.dispatch_chain, cmd
                    )
                else:
                    response = "Orchestrator não inicializado."
                ts = datetime.now().strftime("%H:%M")
                esc = html_lib.escape(response or "")
                await websocket.send_text(
                    f'<div class="response-box">'
                    f'<span style="color:#8b949e;font-size:0.8em">[{ts}]</span> {esc}'
                    f'</div>'
                )
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.debug("ws_command encerrado: %s", exc)

    # ── WebSocket: eventos ao vivo ────────────────────────────────────

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket):
        if not _valid_websocket(websocket):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        session_token = websocket.cookies.get("pacoca_token", "")
        q: _queue_module.Queue = _queue_module.Queue(maxsize=50)
        with _event_queues_lock:
            _event_queues.append(q)
        last_activity = time.monotonic()
        last_ping = time.monotonic()
        try:
            while True:
                try:
                    payload = q.get_nowait()
                    await websocket.send_text(payload)
                except _queue_module.Empty:
                    pass
                try:
                    await asyncio.wait_for(websocket.receive_text(), timeout=0.3)
                    last_activity = time.monotonic()
                except asyncio.TimeoutError:
                    pass
                now = time.monotonic()
                if now - last_activity > _WS_PONG_TIMEOUT_S:
                    logger.info("ws_events: heartbeat sem resposta, encerrando conexão")
                    break
                if now - last_ping > _WS_PING_INTERVAL_S:
                    if not _valid_session_cookie(session_token):
                        logger.info("ws_events: sessão expirada, encerrando conexão")
                        break
                    await websocket.send_text(json.dumps({"type": "ping"}))
                    last_ping = now
        except (WebSocketDisconnect, Exception):
            pass
        finally:
            with _event_queues_lock:
                if q in _event_queues:
                    _event_queues.remove(q)

    # ── Fragmentos HTML (htmx polling) ───────────────────────────────

    @app.get("/api/status-html", response_class=HTMLResponse)
    async def status_html():
        data = _get_status_data()
        profile = html_lib.escape(str(data["profile"]))
        badge_cls = f"badge-{profile}" if profile in ("work", "casual", "focus", "meeting", "night") else "badge-default"
        lang_display = {
            "pt": "Português", "en": "Inglês", "es": "Espanhol",
            "fr": "Francês",   "de": "Alemão", "it": "Italiano",
        }.get(data["language"], data["language"])
        lang_display = html_lib.escape(str(lang_display))
        meeting = "🔴 Em reunião" if data["in_meeting"] else "⚪ Aguardando"
        detector = "✅ Ativo" if data["detector_on"] else "⏸ Inativo"
        return HTMLResponse(f"""
            <div><b>Perfil:</b> <span class="badge {badge_cls}">{profile}</span></div>
            <div style="margin-top:8px"><b>Idioma STT:</b> {lang_display}</div>
            <div style="margin-top:4px"><b>Detector de reunião:</b> {detector}</div>
            <div style="margin-top:4px"><b>Estado:</b> {meeting}</div>
        """)

    @app.get("/api/stats-html", response_class=HTMLResponse)
    async def stats_html():
        data = _get_status_data()
        return HTMLResponse(f"""
            <div class="stat-row">
              <div class="stat">
                <div class="stat-val">{data['history_count']}</div>
                <div class="stat-lbl">Comandos</div>
              </div>
              <div class="stat">
                <div class="stat-val">{data['context_turns']}</div>
                <div class="stat-lbl">Contexto</div>
              </div>
              <div class="stat">
                <div class="stat-val">{data['reminder_count']}</div>
                <div class="stat-lbl">Lembretes</div>
              </div>
              <div class="stat">
                <div class="stat-val">{data['plugin_count']}</div>
                <div class="stat-lbl">Plugins</div>
              </div>
            </div>
        """)

    @app.get("/api/reminders-html", response_class=HTMLResponse)
    async def reminders_html():
        try:
            from modules.reminders import _reminders, _lock
            with _lock:
                pending = [(rid, r) for rid, r in _reminders.items() if not r["fired"]]
        except Exception:
            pending = []
        if not pending:
            return HTMLResponse('<div class="empty">Nenhum lembrete pendente.</div>')
        rows = ""
        for _, r in sorted(pending, key=lambda x: x[1]["fire_at"]):
            t = r["fire_at"].strftime("%H:%M")
            message = html_lib.escape(str(r["message"]))
            rows += f'<div class="reminder-row"><span class="reminder-time">⏰ {t}</span>{message}</div>'
        return HTMLResponse(rows)

    @app.get("/api/context-html", response_class=HTMLResponse)
    async def context_html():
        try:
            from storage.context import get_turns
            turns = get_turns()
        except Exception:
            turns = []
        if not turns:
            return HTMLResponse('<div class="empty">Nenhuma interação no contexto.</div>')
        rows = ""
        for cmd, resp in turns[-5:]:
            short_resp = resp[:80] + "..." if len(resp) > 80 else resp
            cmd = html_lib.escape(str(cmd))
            short_resp = html_lib.escape(str(short_resp))
            rows += (
                f'<div style="margin-bottom:8px">'
                f'<div style="color:#c9d1d9">» {cmd}</div>'
                f'<div style="color:#8b949e;font-size:0.85em;padding-left:12px">{short_resp}</div>'
                f'</div>'
            )
        return HTMLResponse(rows)

    @app.get("/api/history-html", response_class=HTMLResponse)
    async def history_html():
        try:
            from storage.db import get_history
            rows = get_history(limit=30)
        except Exception:
            rows = []
        if not rows:
            return HTMLResponse('<div class="empty">Nenhum comando registrado.</div>')
        html = "<table><tr><th>Hora</th><th>Comando</th><th>Resposta</th></tr>"
        for r in rows:
            ts = r["ts"][11:16] if r["ts"] else ""
            cmd = html_lib.escape((r["command"] or "")[:60])
            resp = html_lib.escape((r["response"] or "")[:100])
            html += f"<tr><td class='ts'>{ts}</td><td class='cmd'>{cmd}</td><td class='resp'>{resp}</td></tr>"
        html += "</table>"
        return HTMLResponse(html)

    # ── Editor de rotinas ─────────────────────────────────────────────

    @app.get("/api/routines-html", response_class=HTMLResponse)
    async def routines_html():
        routines = {}
        if _orchestrator:
            try:
                routines = _orchestrator.config.get("routines", {}) or {}
            except Exception:
                pass
        html = ""
        for name, body in routines.items():
            label = body.get("name", name) if isinstance(body, dict) else name
            steps = body.get("steps", []) if isinstance(body, dict) else []
            steps_txt = ", ".join(s.get("action", "?") for s in steps) if steps else "sem etapas"
            safe_name = html_lib.escape(str(name))
            safe_label = html_lib.escape(str(label))
            safe_steps = html_lib.escape(str(steps_txt))
            encoded_name = quote(str(name), safe="")
            html += (
                f'<div class="routine-row">'
                f'<div><span class="routine-name">{safe_name}</span> '
                f'<span class="routine-steps">{safe_label} ({safe_steps})</span></div>'
                f'<button class="danger" '
                f'hx-post="/api/routines/delete/{encoded_name}" '
                f'hx-target="#routines-block" hx-swap="innerHTML" '
                f'hx-confirm="Excluir esta rotina?">Excluir</button>'
                f'</div>'
            )
        if not html:
            html = '<div class="empty">Nenhuma rotina configurada.</div>'
        html += """
        <form class="add-form"
              hx-post="/api/routines/add"
              hx-target="#routines-block"
              hx-swap="innerHTML">
          <input type="text" name="name" placeholder="nome_rotina" required style="max-width:130px">
          <input type="text" name="label" placeholder="Descrição" required>
          <input type="text" name="action" placeholder="ação (ex: notify)" required style="max-width:120px">
          <input type="text" name="target" placeholder="target/mensagem">
          <button type="submit">+ Adicionar</button>
        </form>"""
        return HTMLResponse(html)

    @app.post("/api/routines/add", response_class=HTMLResponse)
    async def routines_add(
        request: Request,
        name: str = Form(...),
        label: str = Form(...),
        action: str = Form(...),
        target: str = Form(""),
    ):
        if request.headers.get("x-csrf-token") != _CSRF_TOKEN:
            return HTMLResponse('<div class="empty">Token CSRF inválido.</div>', status_code=403)
        if _orchestrator:
            try:
                import yaml
                routines = dict(_orchestrator.config.get("routines", {}) or {})
                step: dict = {"action": action.strip()}
                if target.strip():
                    step["target"] = target.strip()
                routines[name.strip()] = {"name": label.strip(), "steps": [step]}
                _orchestrator.config.set("routines", routines)
                try:
                    cfg_path = _orchestrator.config._path
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    data["routines"] = routines
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                except Exception:
                    pass
            except Exception as exc:
                return HTMLResponse(f'<div class="empty">Erro: {html_lib.escape(str(exc))}</div>')
        return await routines_html()

    @app.post("/api/routines/delete/{name}", response_class=HTMLResponse)
    async def routines_delete(request: Request, name: str):
        if request.headers.get("x-csrf-token") != _CSRF_TOKEN:
            return HTMLResponse('<div class="empty">Token CSRF inválido.</div>', status_code=403)
        if _orchestrator:
            try:
                import yaml
                routines = dict(_orchestrator.config.get("routines", {}) or {})
                routines.pop(name, None)
                _orchestrator.config.set("routines", routines)
                try:
                    cfg_path = _orchestrator.config._path
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    data["routines"] = routines
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                except Exception:
                    pass
            except Exception:
                pass
        return await routines_html()

    # ── JSON API ──────────────────────────────────────────────────────

    @app.get("/api/status")
    async def api_status():
        return JSONResponse(_get_status_data())

    @app.get("/api/history")
    async def api_history():
        try:
            from storage.db import get_history
            return JSONResponse(get_history(limit=50))
        except Exception:
            return JSONResponse([])

    @app.get("/api/metrics")
    async def api_metrics():
        try:
            from core.telemetry import get_summary, get_recent
            return JSONResponse({
                "summary": get_summary(),
                "recent": get_recent(20),
            })
        except Exception as e:
            return JSONResponse({"error": str(e)})

    @app.get("/api/integrations")
    async def api_integrations():
        return JSONResponse(_check_integrations())

    @app.post("/api/integrations/test/{name}")
    async def test_integration(name: str, request: Request):
        if request.headers.get("x-csrf-token") != _CSRF_TOKEN:
            return JSONResponse({"error": "Token CSRF inválido."}, status_code=403)
        result = _test_integration(name)
        return JSONResponse(result)

    # ── Páginas extras ────────────────────────────────────────────────

    @app.get("/integrations", response_class=HTMLResponse)
    async def integrations_page():
        data = _check_integrations()
        rows = ""
        for name, info in data.items():
            ok = info.get("ok", False)
            mark = "✓" if ok else "✗"
            color = "#3fb950" if ok else "#f85149"
            detail = html_lib.escape(str(info.get("detail", "")))
            cb = info.get("circuit_breaker", {})
            extra = ""
            if cb:
                extra = f' <span style="color:#8b949e;font-size:0.82em">(CB: {cb.get("failures",0)} falhas, open={cb.get("open",False)})</span>'
            rows += (
                f'<tr>'
                f'<td style="color:{color};font-size:1.1em;width:24px">{mark}</td>'
                f'<td style="font-weight:bold">{html_lib.escape(name)}</td>'
                f'<td>{detail}{extra}</td>'
                f'<td><button onclick="testIntegration(\'{html_lib.escape(name)}\')" '
                f'id="btn-{html_lib.escape(name)}" style="padding:4px 10px;font-size:0.85em">Testar</button></td>'
                f'</tr>'
            )
        return HTMLResponse(f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<title>Paçoca — Integrações</title>
<style>
  body{{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',monospace;padding:24px;font-size:14px}}
  h1{{color:#58a6ff;margin-bottom:16px}}
  table{{width:100%;border-collapse:collapse}}
  th{{color:#8b949e;font-size:0.72em;text-transform:uppercase;padding:8px;text-align:left;border-bottom:1px solid #21262d}}
  td{{padding:8px;border-bottom:1px solid #21262d}}
  button{{background:#238636;color:#fff;border:none;border-radius:6px;padding:6px 14px;cursor:pointer}}
  button:hover{{background:#2ea043}}
  #result{{margin-top:16px;background:#161b22;border:1px solid #21262d;border-radius:8px;padding:12px;
           white-space:pre;font-size:0.88em}}
  a{{color:#58a6ff}}
</style>
</head><body>
<h1>⚡ Paçoca — Integrações</h1>
<p style="color:#8b949e;margin-bottom:12px"><a href="/">Dashboard</a> · <a href="/metrics">Métricas</a> · <a href="/integrations" style="color:#58a6ff">Integrações</a> · <a href="/docs">Documentação</a></p>
<table>
<tr><th></th><th>Integração</th><th>Status</th><th>Ação</th></tr>
{rows}
</table>
<div id="result" style="display:none"></div>
<script>
async function testIntegration(name) {{
  const btn = document.getElementById('btn-' + name);
  btn.textContent = 'Testando...'; btn.disabled = true;
  const r = await fetch('/api/integrations/test/' + name, {{method:'POST', headers:{{'X-CSRF-Token':'{_CSRF_TOKEN}'}}}});
  const data = await r.json();
  const box = document.getElementById('result');
  box.style.display = 'block';
  box.textContent = name + ': ' + JSON.stringify(data, null, 2);
  btn.textContent = 'Testar'; btn.disabled = false;
}}
</script>
</body></html>""")

    @app.get("/docs", response_class=HTMLResponse)
    async def docs_page():
        try:
            from core.orchestrator import ROUTES
        except Exception:
            ROUTES = []

        # Agrupa rotas por módulo
        groups: dict[str, list[tuple]] = {}
        for item in ROUTES:
            pattern, target, confirm = item[0], item[1], item[2]
            module = target.split(":")[0].split(".")[-1]
            groups.setdefault(module, []).append((pattern, target.split(":")[-1], confirm))

        _GROUP_LABELS = {
            "spotify_ctrl":        "🎵 Spotify",
            "dev_tools":           "💻 Dev Tools & Git",
            "overlay":             "🪟 Overlay",
            "web_server":          "🌐 Dashboard Web",
            "system_control":      "⚙️ Sistema",
            "transcription":       "🎙️ Transcrição",
            "obsidian":            "📓 Obsidian",
            "summarizer":          "📝 Resumos & IA",
            "finance":             "💰 Finanças",
            "weather":             "🌤️ Clima",
            "routines":            "🔄 Rotinas",
            "productivity":        "📊 Produtividade & Timer",
            "meeting_detector":    "📡 Detector de Reunião",
            "profiles":            "👤 Perfis",
            "calendar_integration":"📅 Calendário",
            "stt":                 "🎤 STT & Idioma",
            "reminders":           "⏰ Lembretes",
            "clipboard_tools":     "📋 Clipboard",
            "screen_reader":       "👁️ Leitura de Tela",
            "context":             "🧠 Contexto",
            "plugin_loader":       "🔌 Plugins",
            "orchestrator":        "🤖 Assistente & Memória",
            "backup":              "💾 Backup",
        }

        sections_html = ""
        for mod, routes in groups.items():
            label = _GROUP_LABELS.get(mod, f"📦 {mod}")
            rows = ""
            for pattern, fn, confirm in routes:
                safe_p = html_lib.escape(pattern)
                safe_f = html_lib.escape(fn)
                warn = ' <span style="color:#f0883e;font-size:0.8em">⚠ confirmação</span>' if confirm else ""
                rows += f'<tr><td class="pat"><code>{safe_p}</code></td><td class="fn">{safe_f}{warn}</td></tr>'
            sections_html += f"""
            <div class="section">
              <h2>{html_lib.escape(label)}</h2>
              <table><tr><th>Padrão de comando</th><th>Função</th></tr>{rows}</table>
            </div>"""

        return HTMLResponse(f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<title>Paçoca — Documentação</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',monospace;padding:24px;font-size:14px}}
  h1{{color:#58a6ff;margin-bottom:4px;font-size:1.4em;letter-spacing:2px}}
  h2{{color:#e3b341;font-size:0.8em;text-transform:uppercase;letter-spacing:1px;
      margin:0 0 8px;padding:6px 10px;background:#1c1a10;border-left:3px solid #e3b341;border-radius:0 4px 4px 0}}
  .nav{{margin:10px 0 20px;display:flex;gap:16px;font-size:0.85em;border-bottom:1px solid #21262d;padding-bottom:12px}}
  .nav a{{color:#8b949e;text-decoration:none}} .nav a:hover,.nav a.active{{color:#58a6ff}}
  .section{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px 16px;margin-bottom:14px}}
  table{{width:100%;border-collapse:collapse}}
  th{{color:#8b949e;font-size:0.72em;text-transform:uppercase;padding:5px 8px;text-align:left;border-bottom:1px solid #21262d}}
  td{{padding:4px 8px;border-bottom:1px solid #0d1117;vertical-align:top}}
  td.pat{{width:55%;font-size:0.82em}} td.fn{{font-size:0.82em;color:#79c0ff}}
  code{{background:#0d1117;padding:1px 5px;border-radius:4px;font-family:monospace;color:#c9d1d9;font-size:0.95em}}
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
  .kbd{{background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;
        padding:2px 8px;font-family:monospace;font-size:0.85em}}
  .info-table td{{padding:6px 10px;color:#8b949e}} .info-table td:first-child{{color:#c9d1d9;width:160px}}
  .info-table tr:hover td{{background:#21262d}}
  .badge{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:0.78em;background:#1f3a5f;color:#58a6ff}}
  .subtitle{{color:#8b949e;font-size:0.82em;margin-bottom:16px}}
  @media(max-width:700px){{.two-col{{grid-template-columns:1fr}}}}
</style>
</head><body>
<h1>⚡ Paçoca — Documentação</h1>
<p class="subtitle">Referência completa de comandos, atalhos, configuração e arquitetura.</p>
<nav class="nav">
  <a href="/">Dashboard</a>
  <a href="/metrics">Métricas</a>
  <a href="/integrations">Integrações</a>
  <a href="/docs" class="active">Documentação</a>
</nav>

<div class="two-col" style="margin-bottom:14px">
  <!-- Atalhos de teclado -->
  <div class="section">
    <h2>⌨️ Atalhos de Teclado</h2>
    <table class="info-table">
      <tr><td><span class="kbd">Ctrl+Shift+A</span></td><td>Mostrar / ocultar overlay</td></tr>
      <tr><td><span class="kbd">Ctrl+Shift+Space</span></td><td>Push-to-talk (captura voz sem wake word)</td></tr>
      <tr><td><span class="kbd">Ctrl+Shift+T</span></td><td>Iniciar transcrição</td></tr>
      <tr><td><span class="kbd">Ctrl+Shift+S</span></td><td>Parar transcrição</td></tr>
    </table>
  </div>

  <!-- Modos de execução -->
  <div class="section">
    <h2>🚀 Modos de Execução</h2>
    <table class="info-table">
      <tr><td><code>--mode text</code></td><td>Entrada por teclado (sem microfone)</td></tr>
      <tr><td><code>--mode voice</code></td><td>Wake word + STT (requer requirements-voice.txt)</td></tr>
      <tr><td><code>--no-tts</code></td><td>Desativa Text-to-Speech</td></tr>
      <tr><td><code>--no-overlay</code></td><td>Desativa janela flutuante</td></tr>
      <tr><td><code>--profile work</code></td><td>Perfil ativo: work / casual / focus / meeting / night</td></tr>
      <tr><td><code>--web</code></td><td>Inicia dashboard web em localhost:7755</td></tr>
      <tr><td><code>--edit-routines</code></td><td>Editor interativo de rotinas no terminal</td></tr>
    </table>
  </div>

  <!-- Arquitetura -->
  <div class="section">
    <h2>🏗️ Arquitetura NLU</h2>
    <table class="info-table">
      <tr><td>Camada 1 — Regex</td><td>&lt;1ms · {len(ROUTES)} rotas em ROUTES</td></tr>
      <tr><td>Camada 2 — TF-IDF</td><td>&lt;5ms · scikit-learn · classify_local()</td></tr>
      <tr><td>Camada 3 — LLM</td><td>Groq (online) → Ollama (fallback local)</td></tr>
      <tr><td>Circuit breaker</td><td>3 falhas → pausa 120s</td></tr>
      <tr><td>Truncagem</td><td>Contexto ≤ 24 000 chars, garante sempre</td></tr>
      <tr><td>Streaming TTS</td><td>Fala por frases durante geração do LLM</td></tr>
    </table>
  </div>

  <!-- Configuração -->
  <div class="section">
    <h2>⚙️ Config (core/config.yaml)</h2>
    <table class="info-table">
      <tr><td><code>ai.provider</code></td><td>groq (padrão) | ollama</td></tr>
      <tr><td><code>ai.model</code></td><td>llama3 | mistral | phi3</td></tr>
      <tr><td><code>ai.groq_model</code></td><td>llama-3.1-8b-instant (padrão)</td></tr>
      <tr><td><code>stt.model</code></td><td>tiny | base | small | medium | large</td></tr>
      <tr><td><code>tts.engine</code></td><td>edge | pyttsx3 | coqui</td></tr>
      <tr><td><code>overlay.position</code></td><td>top-left | top-right | bottom-left | bottom-right</td></tr>
      <tr><td><code>privacy.retention_days</code></td><td>dias de histórico (0 = sem limpeza)</td></tr>
      <tr><td><code>obsidian.vault_path</code></td><td>caminho para vault Markdown</td></tr>
      <tr><td><code>web.password</code></td><td>senha do dashboard (vazio = sem auth)</td></tr>
    </table>
  </div>
</div>

<!-- Comandos por categoria -->
<div class="section" style="margin-bottom:14px">
  <h2>📚 Todos os Comandos ({len(ROUTES)} rotas)</h2>
  <p style="color:#8b949e;font-size:0.8em;margin-bottom:12px">
    Padrões regex — capture groups <code>(.+)</code> capturam o argumento do comando.
    <span style="color:#f0883e">⚠ confirmação</span> = ação crítica que pede confirmação antes de executar.
  </p>
  <div class="two-col">
    {"".join(f'<div>{s}</div>' for s in (sections_html or "<p style='color:#8b949e'>Nenhuma rota encontrada.</p>").split("</div>") if s.strip())}
  </div>
</div>

<p style="color:#8b949e;font-size:0.72em;text-align:center;margin-top:8px">
  Paçoca · <a href="https://github.com/AthirsonLamonato/Pacoca" style="color:#58a6ff">github.com/AthirsonLamonato/Pacoca</a>
</p>
</body></html>""")

    @app.get("/metrics", response_class=HTMLResponse)
    async def metrics_page():
        try:
            from core.telemetry import get_summary, get_recent
            summary = get_summary()
            recent = get_recent(20)
        except Exception:
            summary, recent = {}, []

        total = summary.get("total_commands", 0)
        success = round(summary.get("success_rate", 0) * 100, 1)
        avg_lat = summary.get("avg_latency_ms", 0)
        fallback = round(summary.get("fallback_rate", 0) * 100, 1)
        providers_html = ""
        for p, cnt in (summary.get("providers", {}) or {}).items():
            providers_html += f'<span style="margin-right:12px"><b style="color:#58a6ff">{html_lib.escape(str(cnt))}</b> {html_lib.escape(str(p))}</span>'
        llm_html = ""
        for p, stats in (summary.get("llm", {}) or {}).items():
            llm_html += (
                f'<tr><td>{html_lib.escape(str(p))}</td>'
                f'<td>{stats.get("calls",0)}</td>'
                f'<td>{stats.get("total_tokens",0)}</td>'
                f'<td>{stats.get("avg_latency_ms",0)} ms</td></tr>'
            )
        rows_html = ""
        for r in recent:
            ts = datetime.fromtimestamp(r.get("ts", 0)).strftime("%H:%M:%S")
            route = html_lib.escape(str(r.get("route","")[:30]))
            prov = html_lib.escape(str(r.get("provider","")[:10]))
            lat = r.get("latency_ms", 0)
            ok = "✓" if r.get("success") else "✗"
            color = "#3fb950" if r.get("success") else "#f85149"
            fallb = "⚡" if r.get("fallback") else ""
            rows_html += f'<tr><td>{ts}</td><td>{route}</td><td>{prov}</td><td>{lat} ms</td><td style="color:{color}">{ok} {fallb}</td></tr>'

        return HTMLResponse(f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<title>Paçoca — Métricas</title>
<style>
  body{{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',monospace;padding:24px;font-size:14px}}
  h1{{color:#58a6ff;margin-bottom:16px}}
  h2{{color:#8b949e;font-size:0.75em;text-transform:uppercase;letter-spacing:1px;margin:16px 0 8px}}
  .stat-row{{display:flex;gap:24px;flex-wrap:wrap;margin-bottom:16px}}
  .stat{{text-align:center}}
  .stat-val{{font-size:1.8em;font-weight:bold;color:#58a6ff}}
  .stat-lbl{{font-size:0.7em;color:#8b949e;text-transform:uppercase}}
  table{{width:100%;border-collapse:collapse;margin-bottom:16px}}
  th{{color:#8b949e;font-size:0.72em;text-transform:uppercase;padding:6px 8px;text-align:left;border-bottom:1px solid #21262d}}
  td{{padding:6px 8px;border-bottom:1px solid #161b22;font-size:0.88em}}
  a{{color:#58a6ff}}
</style>
</head><body>
<h1>⚡ Paçoca — Métricas</h1>
<p style="color:#8b949e;margin-bottom:12px"><a href="/">Dashboard</a> · <a href="/metrics" style="color:#58a6ff">Métricas</a> · <a href="/integrations">Integrações</a> · <a href="/docs">Documentação</a></p>
<div class="stat-row">
  <div class="stat"><div class="stat-val">{total}</div><div class="stat-lbl">Comandos</div></div>
  <div class="stat"><div class="stat-val">{success}%</div><div class="stat-lbl">Sucesso</div></div>
  <div class="stat"><div class="stat-val">{avg_lat} ms</div><div class="stat-lbl">Latência média</div></div>
  <div class="stat"><div class="stat-val">{fallback}%</div><div class="stat-lbl">Fallback</div></div>
</div>
<h2>Provedores usados</h2>
<p>{providers_html or '<span style="color:#8b949e">Nenhum comando ainda.</span>'}</p>
<h2>Chamadas LLM por provedor</h2>
<table><tr><th>Provedor</th><th>Chamadas</th><th>Tokens total</th><th>Latência média</th></tr>
{llm_html or '<tr><td colspan="4" style="color:#8b949e">Nenhuma chamada LLM registrada.</td></tr>'}
</table>
<h2>Últimos 20 comandos</h2>
<table><tr><th>Hora</th><th>Rota</th><th>Provedor</th><th>Latência</th><th>Status</th></tr>
{rows_html or '<tr><td colspan="5" style="color:#8b949e">Nenhum comando ainda.</td></tr>'}
</table>
</body></html>""")

    return app


# ── Coleta de dados de status ─────────────────────────────────────────

def _get_status_data() -> dict:
    profile = "work"
    language = "pt"
    context_turns = 0
    reminder_count = 0
    history_count = 0
    plugin_count = 0
    in_meeting = False
    detector_on = False

    try:
        from core.profiles import _get_manager
        profile = _get_manager().active
    except Exception:
        pass
    try:
        from input.stt import _active_language, _voice
        language = _voice.config.get("stt.language", "pt") if _voice else (_active_language or "pt")
    except Exception:
        pass
    try:
        from storage.context import get_turns
        context_turns = len(get_turns())
    except Exception:
        pass
    try:
        from modules.reminders import _reminders, _lock
        with _lock:
            reminder_count = sum(1 for r in _reminders.values() if not r["fired"])
    except Exception:
        pass
    try:
        from storage.db import get_history
        history_count = len(get_history(limit=500))
    except Exception:
        pass
    try:
        if _orchestrator:
            plugin_count = len(_orchestrator._plugin_routes)
    except Exception:
        pass
    try:
        from modules.meeting_detector import _in_meeting as _im, _monitoring as _mon
        in_meeting = _im
        detector_on = _mon
    except Exception:
        pass

    return {
        "profile": profile,
        "language": language,
        "context_turns": context_turns,
        "reminder_count": reminder_count,
        "history_count": history_count,
        "plugin_count": plugin_count,
        "in_meeting": in_meeting,
        "detector_on": detector_on,
    }


def _check_integrations() -> dict:
    """
    Verifica status de cada integração: chave, token, conectividade.
    Cada entrada inclui os campos 'ok' (bool) e 'detail' (str) para uso em
    respostas por voz, além de campos detalhados para o dashboard.
    """
    import os, time as _t
    from pathlib import Path
    results: dict[str, dict] = {}

    # Groq
    groq_key = os.environ.get("GROQ_API_KEY", "")
    try:
        from core.providers import _groq_failures, _groq_open_until, _circuit_is_open
        cb_open = _t.monotonic() < _groq_open_until
        cb_failures = _groq_failures
    except Exception:
        cb_open, cb_failures = False, 0
    groq_ok = bool(groq_key) and not cb_open
    results["groq"] = {
        "ok": groq_ok,
        "detail": "chave configurada" if groq_key else "sem GROQ_API_KEY",
        "configured": bool(groq_key),
        "key_hint": f"***{groq_key[-4:]}" if len(groq_key) > 4 else ("configurada" if groq_key else ""),
        "circuit_breaker": {"failures": cb_failures, "open": cb_open},
    }
    if cb_open:
        results["groq"]["detail"] = f"circuit breaker aberto ({cb_failures} falhas)"

    # Ollama
    try:
        import requests as _req
        r = _req.get("http://localhost:11434/api/tags", timeout=2)
        models = [m["name"] for m in r.json().get("models", [])[:5]] if r.ok else []
        results["ollama"] = {
            "ok": r.ok, "detail": f"{len(models)} modelos" if models else "sem modelos",
            "configured": True, "reachable": r.ok, "models": models,
        }
    except Exception:
        results["ollama"] = {"ok": False, "detail": "indisponível", "configured": False, "reachable": False}

    # Spotify
    token_path = Path(".spotify_token.json")
    spotify_ok = token_path.exists()
    results["spotify"] = {
        "ok": spotify_ok,
        "detail": "autorizado" if spotify_ok else "não autorizado (diga: autoriza o Spotify)",
        "configured": spotify_ok,
        "token_file": str(token_path) if spotify_ok else None,
    }

    # Google Calendar
    cal_token = Path("core/google_token.json")
    cal_ok = cal_token.exists()
    results["google_calendar"] = {
        "ok": cal_ok,
        "detail": "autorizado" if cal_ok else "não autorizado",
        "configured": cal_ok,
        "token_file": str(cal_token) if cal_ok else None,
    }

    return results


def _test_integration(name: str) -> dict:
    """Testa conectividade de uma integração específica."""
    import time
    t0 = time.monotonic()
    try:
        if name == "groq":
            # Testa Groq diretamente, sem fallback para Ollama
            from core.providers import get_client, _record_groq_failure
            from core.config import Config
            client = get_client(Config())
            if not client._get_groq_key():
                return {"ok": False, "error": "GROQ_API_KEY não configurada", "latency_ms": 0}
            try:
                data = client._groq_raw([{"role": "user", "content": "responda só: ok"}], max_tokens=5)
                resp = (data["choices"][0]["message"].get("content") or "").strip()
                return {"ok": True, "latency_ms": round((time.monotonic()-t0)*1000, 1), "response": resp[:50], "provider": "groq"}
            except Exception as exc:
                return {"ok": False, "error": str(exc), "latency_ms": round((time.monotonic()-t0)*1000, 1), "provider": "groq"}

        if name == "ollama":
            import requests as _req
            r = _req.get("http://localhost:11434/api/tags", timeout=4)
            return {"ok": r.ok, "latency_ms": round((time.monotonic()-t0)*1000, 1)}

        if name == "spotify":
            from modules.spotify_ctrl import current_track
            resp = current_track()
            return {"ok": "Erro" not in resp, "response": resp[:80]}

        if name == "weather":
            from modules.weather import get_weather
            resp = get_weather("São Paulo")
            return {"ok": "Não consegui" not in resp, "latency_ms": round((time.monotonic()-t0)*1000, 1), "sample": resp[:80]}

        return {"ok": False, "error": f"Integração desconhecida: {name}"}

    except Exception as e:
        return {"ok": False, "error": str(e), "latency_ms": round((time.monotonic()-t0)*1000, 1)}


# Instância global do app (para uvicorn)
app = _make_app()
