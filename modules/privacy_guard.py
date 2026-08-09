"""Privacidade local para conteúdo persistido ou exibido por ferramentas."""

from __future__ import annotations

from core.logger import redact_sensitive


def redaction_enabled() -> bool:
    try:
        from core.config import Config
        return Config().get("privacy.redact_sensitive", True) is not False
    except Exception:
        return True


def sanitize_text(value: object) -> str:
    text = str(value or "")
    return redact_sensitive(text) if redaction_enabled() else text


def screenshots_allowed() -> bool:
    try:
        from core.config import Config
        return Config().get("privacy.allow_screenshots", False) is True
    except Exception:
        return False
