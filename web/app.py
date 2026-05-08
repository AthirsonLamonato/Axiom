"""
web/app.py — Dashboard web local do Axiom
Inicie com: python -m uvicorn web.app:app --host 127.0.0.1 --port 7755
Ou via voz: 'abre o dashboard' / 'inicia a interface web'
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_orchestrator = None
DEFAULT_PORT = 7755


def set_orchestrator(orc) -> None:
    global _orchestrator
    _orchestrator = orc


def _make_app():
    try:
        from fastapi import FastAPI, Form, Request
        from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
    except ImportError:
        return None

    app = FastAPI(title="Axiom Dashboard", docs_url=None, redoc_url=None)

    # ── HTML do dashboard ──────────────────────────────────────────────
    _HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Axiom Dashboard</title>
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
    background: #161b22; border: 1px solid #21262d; border-radius: 8px;
    padding: 16px;
  }
  .card.full { grid-column: 1 / -1; }
  .badge {
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 0.78em; font-weight: bold; margin: 2px;
  }
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
  input[type=text] {
    background: #0d1117; border: 1px solid #30363d; color: #c9d1d9;
    padding: 8px 12px; border-radius: 6px; width: calc(100% - 100px);
    font-size: 14px; outline: none;
  }
  input[type=text]:focus { border-color: #58a6ff; }
  button {
    background: #238636; color: #fff; border: none; border-radius: 6px;
    padding: 8px 16px; cursor: pointer; font-size: 14px; margin-left: 8px;
  }
  button:hover { background: #2ea043; }
  .response-box {
    background: #0d1117; border-left: 3px solid #58a6ff;
    padding: 10px 14px; border-radius: 0 6px 6px 0;
    margin-top: 12px; white-space: pre-wrap; color: #79c0ff; font-size: 0.9em;
  }
  table { width: 100%; border-collapse: collapse; }
  th { color: #8b949e; font-size: 0.72em; text-transform: uppercase;
       padding: 6px 8px; text-align: left; border-bottom: 1px solid #21262d; }
  td { padding: 6px 8px; border-bottom: 1px solid #161b22; font-size: 0.88em; }
  td.ts { color: #8b949e; white-space: nowrap; width: 80px; }
  td.cmd { color: #c9d1d9; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  td.resp { color: #8b949e; font-size: 0.85em; max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .reminder-row { padding: 6px 0; border-bottom: 1px solid #21262d; }
  .reminder-row:last-child { border-bottom: none; }
  .reminder-time { color: #58a6ff; font-weight: bold; margin-right: 8px; }
  .empty { color: #8b949e; font-style: italic; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
</style>
</head>
<body>
<h1>⚡ AXIOM</h1>

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

  <!-- Comando -->
  <div class="card full">
    <h2>Enviar Comando</h2>
    <form hx-post="/api/command"
          hx-target="#cmd-response"
          hx-swap="innerHTML"
          hx-trigger="submit">
      <input type="text" name="command" placeholder="Digite ou fale um comando..." autofocus>
      <button type="submit">Enviar</button>
    </form>
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

  <!-- Contexto -->
  <div class="card">
    <h2>Contexto da Sessão</h2>
    <div id="context-block"
         hx-get="/api/context-html"
         hx-trigger="load, every 20s"
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
  Axiom Dashboard — <a href="/api/status">JSON</a>
</p>
</body>
</html>"""

    # ── Fragmentos HTML parciais (usados pelo htmx) ────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return HTMLResponse(content=_HTML)

    @app.get("/api/status-html", response_class=HTMLResponse)
    async def status_html():
        data = _get_status_data()
        profile = data["profile"]
        badge_cls = f"badge-{profile}" if profile in ("work","casual","focus","meeting","night") else "badge-default"
        lang_display = {
            "pt": "Português", "en": "Inglês", "es": "Espanhol",
            "fr": "Francês",   "de": "Alemão", "it": "Italiano",
        }.get(data["language"], data["language"])
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

    @app.post("/api/command", response_class=HTMLResponse)
    async def run_command(command: str = Form(...)):
        if not command.strip():
            return HTMLResponse("")
        response = ""
        if _orchestrator:
            try:
                result = _orchestrator.dispatch_chain(command.strip())
                response = result or "(sem resposta)"
            except Exception as e:
                response = f"Erro: {e}"
        else:
            response = "Orchestrator não inicializado."
        escaped = response.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return HTMLResponse(f'<div class="response-box">{escaped}</div>')

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
            rows += f'<div class="reminder-row"><span class="reminder-time">⏰ {t}</span>{r["message"]}</div>'
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
            cmd = (r["command"] or "")[:60]
            resp = (r["response"] or "")[:100]
            html += f"<tr><td class='ts'>{ts}</td><td class='cmd'>{cmd}</td><td class='resp'>{resp}</td></tr>"
        html += "</table>"
        return HTMLResponse(html)

    @app.get("/api/status")
    async def api_status():
        from fastapi.responses import JSONResponse
        return JSONResponse(_get_status_data())

    @app.get("/api/history")
    async def api_history():
        from fastapi.responses import JSONResponse
        from storage.db import get_history
        return JSONResponse(get_history(limit=50))

    return app


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


# Instância global do app (para uvicorn)
app = _make_app()
