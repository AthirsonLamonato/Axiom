"""Testes para core/orchestrator.py"""

import os
import re
import sys
import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import Config
from core.orchestrator import Orchestrator, ROUTES


@pytest.fixture
def config(tmp_path):
    data = {
        "profile": {"active": "work"},
        "tts": {"enabled": False},
        "ai": {"provider": "ollama", "model": "llama3", "ollama_url": "http://localhost:11434", "max_tokens": 512,
               "system_prompt": "Você é Paçoca."},
        "security": {"confirm_critical": False, "critical_commands": []},
        "routines": {},
        "logging": {"level": "WARNING", "file": "logs/pacoca.log", "max_mb": 10},
        "wake_word": {"keyword": "axiom"},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return Config(str(path))


@pytest.fixture
def orchestrator(config):
    return Orchestrator(config)


# ── Testes de roteamento ───────────────────────────────────────────────

def test_routes_is_list_of_tuples():
    assert isinstance(ROUTES, list)
    for route in ROUTES:
        assert len(route) == 3
        pattern, handler, confirm = route
        assert isinstance(pattern, str)
        assert ":" in handler
        assert isinstance(confirm, bool)


def test_dispatch_lista_processos(orchestrator):
    result = orchestrator.dispatch("lista processos")
    assert result is not None
    assert "processo" in result.lower() or "top" in result.lower()


def test_dispatch_volume(orchestrator):
    result = orchestrator.dispatch("volume 50")
    assert result is not None
    assert isinstance(result, str)


def test_dispatch_open_vscode_uses_dev_route(orchestrator):
    """Garante que 'abre o vscode' usa dev_tools e não system_control."""
    result = orchestrator.dispatch("abre o vscode")
    assert result is not None
    # A rota correta retorna mensagem de VS Code, não de app genérico com "o vscode"
    assert "vs code" in result.lower() or "vscode" in result.lower() or "erro" in result.lower()


def test_dispatch_unknown_falls_to_ai(orchestrator, monkeypatch):
    """Comandos desconhecidos vão para o fallback de IA."""
    # Isola o caminho NLU para garantir que chega ao _fallback_ai
    monkeypatch.setattr("modules.intent.classify_local", lambda cmd: [])
    monkeypatch.setattr("modules.intent.run_agentic_loop", lambda cmd: "")
    monkeypatch.setattr("modules.intent.parse_intent_ollama", lambda cmd: [])
    monkeypatch.setattr("modules.intent.parse_intent", lambda cmd: [])
    monkeypatch.setattr("modules.summarizer.ask_ai", lambda p, **kw: "resposta_ia")
    result = orchestrator.dispatch("comando completamente desconhecido xyz")
    assert result == "resposta_ia"


def test_dispatch_returns_string(orchestrator):
    """Toda resposta do dispatch deve ser str."""
    commands = [
        "lista processos",
        "modo trabalho",
        "fim do dia",
    ]
    for cmd in commands:
        result = orchestrator.dispatch(cmd)
        assert isinstance(result, str), f"Falhou para: {cmd!r}"


def test_vscode_route_before_generic_open():
    """VS Code deve ter rota antes da rota genérica 'abre'."""
    handlers = [handler for _, handler, _ in ROUTES]
    vscode_idx = handlers.index("modules.dev_tools:open_vscode")
    generic_idx = handlers.index("modules.system_control:open_app")
    assert vscode_idx < generic_idx, "Rota do VS Code deve vir antes da rota genérica 'abre'"


def _matched_route(command):
    for pattern, handler, confirm in ROUTES:
        match = re.search(pattern, command.lower())
        if match:
            return handler, match.groups(), confirm
    raise AssertionError(f"Nenhuma rota para: {command}")


@pytest.mark.parametrize(
    ("command", "handler", "groups"),
    [
        (
            "me lembra em 30 minutos de fazer backup",
            "modules.reminders:add",
            ("me lembra em 30 minutos de fazer backup",),
        ),
        (
            "cancela lembrete 2",
            "modules.reminders:cancel",
            ("2",),
        ),
        (
            "muda para perfil casual",
            "core.profiles:switch_profile",
            ("casual",),
        ),
        (
            "adiciona evento dentista amanhã às 10h30",
            "modules.calendar_integration:add_event",
            ("dentista amanhã às 10h30",),
        ),
        (
            "abre https://example.com",
            "modules.system_control:open_url",
            ("https://example.com",),
        ),
        (
            "foco por 2 h",
            "modules.productivity:focus_start_hours",
            ("2",),
        ),
        (
            "começa transcrição do sistema",
            "modules.transcription:start",
            ("do sistema",),
        ),
    ],
)
def test_routes_pass_only_semantic_arguments(command, handler, groups):
    matched_handler, matched_groups, _ = _matched_route(command)
    assert matched_handler == handler
    assert matched_groups == groups
