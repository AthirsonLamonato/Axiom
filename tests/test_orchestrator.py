"""Testes para core/orchestrator.py"""

import os
import re
import sys
import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import Config
from core.orchestrator import Orchestrator, ROUTES, _is_voice_exit, list_commands


def test_voice_exit_commands_are_explicit():
    assert _is_voice_exit(" Sair ") is True
    assert _is_voice_exit("Paçoca desligar") is True
    assert _is_voice_exit("desligar o monitor") is False


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
        "wake_word": {"keyword": "paçoca"},
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


def test_list_commands_is_human_readable():
    text = list_commands()

    assert "Comandos disponíveis" in text
    assert "[Sistema e apps]" in text
    assert "abre o VS Code" in text
    assert r"\s+" not in text
    assert "modules." not in text


def test_list_commands_filters_by_topic():
    text = list_commands("git")

    assert text.startswith("Ajuda: Dev e git")
    assert "git log" in text
    assert "[Sistema e apps]" not in text


def test_help_route_accepts_topic(orchestrator):
    result = orchestrator.dispatch("ajuda agenda")

    assert "Ajuda: agenda" in result
    assert "próximo evento" in result


def test_list_commands_accepts_specific_command():
    text = list_commands("commit")

    assert text.startswith("Ajuda: commit")
    assert "Cria um commit Git" in text
    assert 'commit "fix: corrige inicialização"' in text


def test_help_route_accepts_specific_command(orchestrator):
    result = orchestrator.dispatch("ajuda lembrete")

    assert "Ajuda: lembretes" in result
    assert "cancela lembrete 2" in result


def test_list_commands_unknown_topic():
    text = list_commands("banana")

    assert "Não encontrei ajuda" in text
    assert "Tópicos disponíveis" in text


def test_dispatch_lista_processos(orchestrator):
    result = orchestrator.dispatch("lista processos")
    assert result is not None
    assert "processo" in result.lower() or "top" in result.lower()


def test_dispatch_volume(orchestrator):
    result = orchestrator.dispatch("volume 50")
    assert result is not None
    assert isinstance(result, str)


def test_time_question_uses_local_clock(orchestrator):
    result = orchestrator.dispatch("que horas são")

    assert re.fullmatch(r"Agora são \d{2}:\d{2}\.", result)


def test_date_question_uses_local_calendar(orchestrator):
    result = orchestrator.dispatch("qual é a data de hoje")

    assert result.startswith("Hoje é ")
    assert re.search(r" de \d{4}\.$", result)


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
        (
            "que horas são",
            "modules.local_info:current_time",
            (),
        ),
    ],
)
def test_routes_pass_only_semantic_arguments(command, handler, groups):
    matched_handler, matched_groups, _ = _matched_route(command)
    assert matched_handler == handler
    assert matched_groups == groups


@pytest.mark.parametrize(
    "command",
    [
        "git pull",
        "formata o código",
        "adiciona evento dentista amanhã às 10h30",
    ],
)
def test_routes_require_confirmation_for_writes(command):
    _, _, requires_confirmation = _matched_route(command)
    assert requires_confirmation is True


def test_direct_route_uses_shared_confirmation_channel(orchestrator, monkeypatch):
    captured = {}

    def confirm(name, args):
        captured.update(name=name, args=args)
        return True

    monkeypatch.setattr("modules.intent._confirm_action", confirm)

    assert orchestrator._confirm("git pull") is True
    assert captured == {
        "name": "direct_command",
        "args": {"action": "git pull", "risk": "medium", "external": False},
    }
