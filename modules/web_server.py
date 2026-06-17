"""
modules/web_server.py — Gerencia o servidor web do dashboard Paçoca
Comandos: 'abre o dashboard', 'inicia a interface web', 'para o servidor web'
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_server_thread: Optional[threading.Thread] = None
_server = None
_server_running = False
_server_orc = None
PORT = 7755
HOST = "127.0.0.1"


def start(*_) -> str:
    global _server_thread, _server, _server_running
    if _server_running:
        _open_browser()
        return f"Dashboard já está rodando em http://{HOST}:{PORT}"

    try:
        import uvicorn
    except ImportError:
        return (
            "uvicorn não instalado.\n"
            "Execute: pip install fastapi uvicorn"
        )
    try:
        from web.app import app as _app
        if _app is None:
            return "FastAPI não disponível. Execute: pip install fastapi"
    except ImportError:
        return "Módulo web não disponível. Execute: pip install fastapi uvicorn"

    # Injeta referência ao orchestrator se disponível
    try:
        from core.orchestrator import Orchestrator  # noqa: F401
        from web.app import set_orchestrator
        # O orchestrator chama web_server.set_orc(self) após iniciar
    except Exception:
        pass

    # Propaga senha do config para o app web (usa config do orchestrator se disponível)
    try:
        from web.app import set_password
        cfg = _server_orc.config if _server_orc else None
        if cfg is None:
            from core.config import Config
            cfg = Config()
        pwd = cfg.get("web.password", "")
        set_password(pwd)
    except Exception:
        pass

    _server_running = True
    config = uvicorn.Config(
        _app,
        host=HOST,
        port=PORT,
        log_level="warning",
        reload=False,
    )
    _server = uvicorn.Server(config)

    def _run():
        global _server_running
        try:
            _server.run()
        finally:
            _server_running = False

    _server_thread = threading.Thread(target=_run, daemon=True)
    _server_thread.start()

    # Aguarda o servidor subir
    import time
    time.sleep(1.2)
    _open_browser()

    return f"Dashboard disponível em http://{HOST}:{PORT}"


def stop(*_) -> str:
    global _server, _server_thread, _server_running
    if not _server_running or _server is None:
        return "Servidor web não está rodando."
    _server.should_exit = True
    if _server_thread and _server_thread.is_alive():
        _server_thread.join(timeout=5)
    if _server_thread and _server_thread.is_alive():
        return "Servidor web está demorando para encerrar."
    _server_running = False
    _server = None
    _server_thread = None
    return "Servidor web encerrado."


def _open_browser():
    import webbrowser
    url = f"http://{HOST}:{PORT}"
    try:
        webbrowser.open(url)
    except Exception:
        pass


def set_orc(orc) -> None:
    """Chamado pelo Orchestrator para injetar a referência no app web."""
    global _server_orc
    _server_orc = orc
    try:
        from web.app import set_orchestrator
        set_orchestrator(orc)
    except Exception:
        pass
