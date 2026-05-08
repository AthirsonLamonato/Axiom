"""
modules/web_server.py — Gerencia o servidor web do dashboard Axiom
Comandos: 'abre o dashboard', 'inicia a interface web', 'para o servidor web'
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_server_thread: Optional[threading.Thread] = None
_server_running = False
PORT = 7755
HOST = "127.0.0.1"


def start(*_) -> str:
    global _server_thread, _server_running
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

    # Propaga senha do config para o app web
    try:
        from core.config import Config
        _cfg = Config()
        pwd = _cfg.get("web.password", "")
        if pwd:
            from web.app import set_password
            set_password(pwd)
    except Exception:
        pass

    _server_running = True

    def _run():
        global _server_running
        try:
            uvicorn.run(
                "web.app:app",
                host=HOST, port=PORT,
                log_level="warning",
                reload=False,
            )
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
    global _server_running
    if not _server_running:
        return "Servidor web não está rodando."
    _server_running = False
    return "Servidor web encerrado."


def _open_browser():
    import webbrowser
    import platform
    url = f"http://{HOST}:{PORT}"
    try:
        webbrowser.open(url)
    except Exception:
        pass


def set_orc(orc) -> None:
    """Chamado pelo Orchestrator para injetar a referência no app web."""
    try:
        from web.app import set_orchestrator
        set_orchestrator(orc)
    except Exception:
        pass
