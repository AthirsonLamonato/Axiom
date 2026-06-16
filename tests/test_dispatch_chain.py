"""Testes para dispatch_chain e _matches_route do Orchestrator."""

import os
import sys
import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import Config
from core.orchestrator import Orchestrator, ROUTES, _CHAIN_SEP, _CHAIN_AND


@pytest.fixture
def config(tmp_path):
    data = {
        "profile": {"active": "work"},
        "tts": {"enabled": False},
        "ai": {"provider": "ollama", "model": "llama3",
               "ollama_url": "http://localhost:11434", "max_tokens": 512,
               "system_prompt": "Você é Paçoca."},
        "security": {"confirm_critical": False, "critical_commands": []},
        "plugins": {"enabled": False},
        "routines": {},
        "logging": {"level": "WARNING", "file": "logs/pacoca.log", "max_mb": 10},
        "wake_word": {"keyword": "paçoca"},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return Config(str(path))


@pytest.fixture
def orc(config):
    return Orchestrator(config)


# ── Regex dos separadores ─────────────────────────────────────────────

def test_chain_sep_e_depois():
    parts = _CHAIN_SEP.split("foco por 25 min e depois para o timer")
    assert len(parts) == 2
    assert "foco por 25 min" in parts[0]


def test_chain_sep_em_seguida():
    parts = _CHAIN_SEP.split("lista processos em seguida volume 50")
    assert len(parts) == 2


def test_chain_sep_entao_sem_acento():
    parts = _CHAIN_SEP.split("abre o overlay entao fecha o overlay")
    assert len(parts) == 2


def test_chain_sep_nao_divide_sem_conector():
    parts = _CHAIN_SEP.split("lista processos")
    assert len(parts) == 1


# ── _matches_route ────────────────────────────────────────────────────

def test_matches_route_conhecido(orc):
    assert orc._matches_route("lista processos") is True


def test_matches_route_volume(orc):
    assert orc._matches_route("volume 70") is True


def test_matches_route_desconhecido(orc):
    assert orc._matches_route("xyzxyz abc def 9999") is False


# ── dispatch_chain ────────────────────────────────────────────────────

def test_dispatch_chain_simples_delega_ao_dispatch(orc, monkeypatch):
    monkeypatch.setattr(orc, "dispatch", lambda cmd: "ok")
    result = orc.dispatch_chain("lista processos")
    assert result == "ok"


def test_dispatch_chain_conector_forte_executa_dois(orc, monkeypatch):
    chamadas = []
    def fake_dispatch(cmd):
        chamadas.append(cmd)
        return f"resp:{cmd}"
    monkeypatch.setattr(orc, "dispatch", fake_dispatch)
    result = orc.dispatch_chain("lista processos e depois volume 50")
    assert len(chamadas) == 2
    assert "resp:lista processos" in result
    assert "resp:volume 50" in result


def test_dispatch_chain_e_simples_so_divide_se_ambos_batem(orc, monkeypatch):
    chamadas = []
    monkeypatch.setattr(orc, "dispatch", lambda cmd: chamadas.append(cmd) or "ok")
    orc.dispatch_chain("lista processos e volume 50")
    assert len(chamadas) == 2


def test_dispatch_chain_e_simples_nao_divide_desconhecido(orc, monkeypatch):
    chamadas = []
    monkeypatch.setattr(orc, "dispatch", lambda cmd: chamadas.append(cmd) or "ok")
    orc.dispatch_chain("xyzxyz e volume 50")
    assert len(chamadas) == 1


def test_dispatch_chain_fala_parte_nao_streamada(orc, monkeypatch):
    """Regressão: se uma parte do encadeamento já falou via streaming
    (_tts_done=True), as demais partes não devem ficar mudas — cada uma
    deve ser falada individualmente, e o chamador não deve falar o texto
    combinado de novo (orc._tts_done deve terminar True)."""
    falas = []
    monkeypatch.setattr(orc.tts, "speak", lambda texto: falas.append(texto))

    def fake_dispatch(cmd):
        if "horas" in cmd:
            orc._tts_done = True  # simula resposta já falada via streaming
            return "são 10h"
        return f"resp:{cmd}"

    monkeypatch.setattr(orc, "dispatch", fake_dispatch)
    result = orc.dispatch_chain("que horas são e depois volume 50")

    assert "são 10h" in result
    assert "resp:volume 50" in result
    assert falas == ["resp:volume 50"]   # só a parte não-streamada foi falada aqui
    assert orc._tts_done is True          # chamador não deve falar o texto combinado de novo


def test_dashboard_route_antes_do_abre_generico():
    """'abre o dashboard' deve usar web_server, não system_control."""
    handlers = [h for _, h, _ in ROUTES]
    ws_idx = next(i for i, h in enumerate(handlers) if "web_server:start" in h)
    gen_idx = next(i for i, h in enumerate(handlers) if h == "modules.system_control:open_app")
    assert ws_idx < gen_idx
