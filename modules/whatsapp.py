"""
modules/whatsapp.py — Envio de mensagens via WhatsApp Web (pywhatkit)

⚠ Segurança: por padrão só é permitido enviar mensagens para o número do
próprio usuário (whatsapp.allowed_numbers no config.yaml). Qualquer envio
passa antes pela confirmação explícita do ToolRegistry/orchestrator — esta
camada é uma segunda barreira, independente da confirmação.
"""

import logging
import re

logger = logging.getLogger(__name__)


def _get_config():
    from core.config import Config
    return Config()


def _normalize_number(raw: str) -> str:
    """Mantém apenas dígitos e o '+' inicial, se houver."""
    raw = raw.strip()
    digits = re.sub(r"[^\d]", "", raw)
    return f"+{digits}" if digits else ""


def _resolve_contact(contact: str) -> str:
    """Resolve um nome de contato para número via whatsapp.contacts, ou
    retorna o próprio valor se já parecer um número."""
    contact = contact.strip()
    config = _get_config()
    contacts = config.get("whatsapp.contacts", {}) or {}

    # Já é um número (contém pelo menos 8 dígitos)?
    digits = re.sub(r"[^\d]", "", contact)
    if len(digits) >= 8:
        return _normalize_number(contact)

    for name, number in contacts.items():
        if name.lower() == contact.lower():
            return _normalize_number(str(number))

    return ""


def _is_allowed(number: str) -> bool:
    config = _get_config()
    allowed = config.get("whatsapp.allowed_numbers", []) or []
    allowed_normalized = {_normalize_number(str(n)) for n in allowed}
    return _normalize_number(number) in allowed_normalized


def send(contact: str, message: str, *_) -> str:
    """Envia `message` para `contact` (nome cadastrado ou número) via WhatsApp Web.

    Camadas de segurança, nesta ordem:
      1. ToolRegistry/orchestrator já exigiu confirmação explícita antes de chamar isto.
      2. O número resolvido precisa estar em whatsapp.allowed_numbers (whitelist).
    """
    config = _get_config()
    if not config.get("whatsapp.enabled", True):
        return "Envio de WhatsApp está desabilitado (whatsapp.enabled: false)."

    number = _resolve_contact(contact)
    if not number:
        return f"Não conheço o contato '{contact}'. Cadastre em whatsapp.contacts no config.yaml."

    if not _is_allowed(number):
        return (
            f"Por segurança, só posso enviar mensagens para números autorizados em "
            f"whatsapp.allowed_numbers. '{contact}' ({number}) não está na lista — "
            f"nenhuma mensagem foi enviada."
        )

    logger.warning(
        "⚠ ENVIANDO MENSAGEM REAL VIA WHATSAPP para %s: %r", number, message
    )
    print(f"\n[Paçoca] ⚠ Enviando mensagem real via WhatsApp para {number}: {message!r}")

    try:
        import pywhatkit
    except ImportError:
        return (
            "pywhatkit não está instalado. Rode 'pip install pywhatkit' para "
            "habilitar o envio de mensagens via WhatsApp Web."
        )

    try:
        pywhatkit.sendwhatmsg_instantly(
            number, message, wait_time=20, tab_close=True, close_time=3,
        )
        return f"Mensagem enviada para {contact} ({number})."
    except Exception as e:
        logger.error("Falha ao enviar mensagem WhatsApp: %s", e, exc_info=True)
        return f"Falha ao enviar mensagem via WhatsApp: {e}"
