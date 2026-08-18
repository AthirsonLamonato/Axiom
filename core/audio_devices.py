"""Utilitários para seleção de dispositivos de áudio via PyAudio.

Os valores de configuração aceitam índice numérico, nome exato ou parte do nome.
A resolução é tolerante: dispositivo inválido retorna ``None`` para preservar o
comportamento padrão do sistema operacional.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _configured_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() in {"auto", "default", "padrao", "padrão"}:
            return None
        if value.isdigit():
            return int(value)
    return value


def resolve_device_index(pa, configured: Any, direction: str) -> int | None:
    """Resolve uma configuração para o índice PyAudio apropriado.

    ``direction`` deve ser ``input`` ou ``output``. Em caso de índice/nome
    inválido, registra um aviso e deixa o PyAudio escolher o dispositivo padrão.
    """
    configured = _configured_value(configured)
    if configured is None:
        return None

    is_input = direction == "input"
    if direction not in {"input", "output"}:
        raise ValueError("direction deve ser 'input' ou 'output'")

    count = pa.get_device_count()
    devices = []
    for index in range(count):
        try:
            info = pa.get_device_info_by_index(index)
        except Exception:
            continue
        channels = info.get("maxInputChannels" if is_input else "maxOutputChannels", 0)
        if channels:
            devices.append((index, str(info.get("name", ""))))

    if isinstance(configured, int):
        if any(index == configured for index, _ in devices):
            return configured
    else:
        wanted = str(configured).casefold()
        exact = next((index for index, name in devices if name.casefold() == wanted), None)
        if exact is not None:
            return exact
        partial = next((index for index, name in devices if wanted in name.casefold()), None)
        if partial is not None:
            return partial

    logger.warning("Dispositivo de áudio %r (%s) não encontrado; usando padrão", configured, direction)
    return None


def list_devices() -> list[dict[str, Any]]:
    """Retorna dispositivos disponíveis sem exigir PyAudio no import do módulo."""
    import pyaudio

    pa = pyaudio.PyAudio()
    try:
        result = []
        for index in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(index)
            result.append({
                "index": index,
                "name": info.get("name", ""),
                "input": int(info.get("maxInputChannels", 0) or 0) > 0,
                "output": int(info.get("maxOutputChannels", 0) or 0) > 0,
            })
        return result
    finally:
        pa.terminate()
