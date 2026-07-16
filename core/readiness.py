"""Diagnóstico executável das capacidades prometidas pelo Paçoca."""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    required: bool
    detail: str
    fix: str = ""


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _module_check(name: str, module: str, required: bool, fix: str) -> Check:
    ok = _has_module(module)
    return Check(name, ok, required, "instalado" if ok else "ausente", "" if ok else fix)


def _check_ollama(config, required: bool) -> Check:
    expected = str(config.get("ai.model", "llama3")).strip()
    url = str(config.get("ai.ollama_url", "http://localhost:11434")).rstrip("/")
    try:
        import requests
        response = requests.get(f"{url}/api/tags", timeout=3)
        response.raise_for_status()
        models = [
            str(item.get("name") or item.get("model") or "")
            for item in response.json().get("models", [])
        ]
        normalized = {name.split(":", 1)[0].lower() for name in models}
        expected_normalized = expected.split(":", 1)[0].lower()
        if expected.lower() in {name.lower() for name in models} or expected_normalized in normalized:
            return Check("IA local (Ollama)", True, required, f"modelo {expected} disponível")
        installed = ", ".join(models[:4]) or "nenhum"
        return Check(
            "IA local (Ollama)",
            False,
            required,
            f"servidor ativo, mas modelo {expected} ausente (instalados: {installed})",
            f"ollama pull {expected}",
        )
    except Exception as exc:
        return Check(
            "IA local (Ollama)",
            False,
            required,
            f"indisponível: {type(exc).__name__}",
            "instale/inicie o Ollama e execute: ollama pull llama3",
        )


def _check_groq(config, required: bool) -> Check:
    try:
        from core.providers import _resolve_key
        key = _resolve_key("ai.groq_api_key", "GROQ_API_KEY", config)
    except Exception:
        key = os.environ.get("GROQ_API_KEY", "")
    return Check(
        "IA online (Groq)",
        bool(key),
        required,
        "chave configurada" if key else "GROQ_API_KEY ausente",
        "configure GROQ_API_KEY ou use ai.provider: ollama" if not key else "",
    )


def _check_microphone(required: bool) -> Check:
    if not _has_module("pyaudio"):
        return Check(
            "Microfone (PyAudio)",
            False,
            required,
            "PyAudio ausente",
            "pip install -r requirements-voice.txt",
        )
    try:
        import pyaudio

        audio = pyaudio.PyAudio()
        inputs = []
        try:
            for index in range(audio.get_device_count()):
                info = audio.get_device_info_by_index(index)
                if int(info.get("maxInputChannels", 0)) > 0:
                    inputs.append(str(info.get("name", f"dispositivo {index}")))
        finally:
            audio.terminate()
        if inputs:
            return Check("Microfone (PyAudio)", True, required, inputs[0])
        return Check("Microfone (PyAudio)", False, required, "nenhuma entrada de áudio encontrada")
    except Exception as exc:
        return Check(
            "Microfone (PyAudio)",
            False,
            required,
            f"falha ao enumerar áudio: {type(exc).__name__}",
            "verifique o microfone padrão e as permissões do Windows",
        )


def _check_wakeword(config, required: bool) -> Check:
    if not _has_module("openwakeword"):
        return Check(
            "Wake word Hey Jarvis",
            False,
            required,
            "openWakeWord ausente",
            "execute setup.bat e escolha a instalacao Jarvis completa",
        )

    custom_path = str(config.get("wake_word.model_path", "") or "").strip()
    if custom_path:
        ok = os.path.isfile(custom_path)
        return Check(
            "Wake word personalizado",
            ok,
            required,
            custom_path if ok else f"arquivo ausente: {custom_path}",
            "corrija wake_word.model_path ou deixe vazio para usar Hey Jarvis" if not ok else "",
        )

    try:
        from input.stt import ensure_default_wakeword_model

        model_path = ensure_default_wakeword_model(download=False)
    except Exception:
        model_path = None
    return Check(
        "Wake word Hey Jarvis",
        bool(model_path),
        required,
        "modelo ONNX pronto" if model_path else "modelo de ativacao nao foi baixado",
        "execute setup.bat e escolha a instalacao Jarvis completa" if not model_path else "",
    )


def run_checks(config, mode: str = "voice", web: bool = False) -> list[Check]:
    voice = mode == "voice"
    provider = str(config.get("ai.provider", "ollama")).lower()
    checks = [
        _module_check("Configuração YAML", "yaml", True, "pip install -r requirements.txt"),
        _check_ollama(config, provider in ("ollama", "auto")),
        _check_groq(config, provider == "groq"),
    ]

    if config.get("tts.enabled", True):
        tts_ok = _has_module("edge_tts") or _has_module("pyttsx3")
        checks.append(Check(
            "Resposta por voz (TTS)",
            tts_ok,
            True,
            "edge-tts/pyttsx3 disponível" if tts_ok else "nenhum motor instalado",
            "pip install -r requirements.txt" if not tts_ok else "",
        ))

    if config.get("overlay.enabled", True):
        checks.append(_module_check(
            "Janela desktop", "PyQt6", True, "pip install -r requirements.txt"
        ))

    if voice:
        checks.extend([
            _module_check(
                "Reconhecimento Whisper",
                "faster_whisper",
                True,
                "pip install -r requirements-voice.txt",
            ),
            _check_microphone(True),
        ])
        if config.get("wake_word.enabled", True):
            checks.append(_check_wakeword(config, True))

    if web:
        checks.extend([
            _module_check("Dashboard FastAPI", "fastapi", True, "pip install -r requirements.txt"),
            _module_check("Servidor Uvicorn", "uvicorn", True, "pip install -r requirements.txt"),
        ])
    return checks


def format_report(checks: list[Check]) -> str:
    lines = ["", "Diagnóstico do Paçoca", "=" * 54]
    for check in checks:
        mark = "OK" if check.ok else ("ERRO" if check.required else "AVISO")
        lines.append(f"[{mark:5}] {check.name}: {check.detail}")
        if check.fix:
            lines.append(f"        Como corrigir: {check.fix}")
    required_ok = all(check.ok for check in checks if check.required)
    lines.extend([
        "-" * 54,
        "Pronto para executar." if required_ok else "Há requisitos obrigatórios pendentes.",
    ])
    return "\n".join(lines)


def doctor(config, mode: str = "voice", web: bool = False) -> tuple[bool, str]:
    checks = run_checks(config, mode=mode, web=web)
    return all(check.ok for check in checks if check.required), format_report(checks)
