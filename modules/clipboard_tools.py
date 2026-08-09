"""
modules/clipboard_tools.py — Acesso à área de transferência por voz
Requer: pip install pyperclip
"""

import logging

logger = logging.getLogger(__name__)

_last_response: str = ""


def set_last_response(text: str) -> None:
    """Chamado pelo Orchestrator após cada resposta para habilitar 'copia o último resultado'."""
    global _last_response
    _last_response = text


def copy_text(text: str, *_) -> str:
    try:
        import pyperclip
    except ImportError:
        return "pyperclip não instalado: pip install pyperclip"
    try:
        pyperclip.copy(text.strip())
        short = text[:80] + "..." if len(text) > 80 else text
        return f"Copiado para a área de transferência: {short}"
    except Exception as e:
        return f"Erro ao copiar: {e}"


def copy_last(*_) -> str:
    if not _last_response:
        return "Nenhuma resposta recente do Paçoca para copiar."
    return copy_text(_last_response)


def read_clipboard(*_) -> str:
    try:
        import pyperclip
    except ImportError:
        return "pyperclip não instalado: pip install pyperclip"
    try:
        text = pyperclip.paste()
        if not text or not text.strip():
            return "Área de transferência vazia."
        from modules.privacy_guard import sanitize_text
        safe_text = sanitize_text(text)
        preview = safe_text[:400] + "\n... (truncado)" if len(safe_text) > 400 else safe_text
        return f"Área de transferência:\n{preview}"
    except Exception as e:
        return f"Erro ao ler clipboard: {e}"


def clear_clipboard(*_) -> str:
    try:
        import pyperclip
        pyperclip.copy("")
        return "Área de transferência limpa."
    except ImportError:
        return "pyperclip não instalado: pip install pyperclip"
    except Exception as e:
        return f"Erro: {e}"
