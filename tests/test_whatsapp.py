"""Testes para o envio de mensagens via WhatsApp (modules/whatsapp.py)."""

import sys
import types

from modules import whatsapp
from modules.external_actions import LIVE_ENV_TOKEN, LIVE_ENV_VAR


def _config_with(**overrides):
    data = {
        "whatsapp.enabled": True,
        "whatsapp.allowed_numbers": ["+5554991102959"],
        "whatsapp.contacts": {"fulano": "+5554991102959", "estranho": "+5511988887777"},
        "external_actions.mode": "simulate",
        "external_actions.live_enabled": False,
    }
    data.update(overrides)
    return type("C", (), {"get": lambda self, k, d=None: data.get(k, d)})()


def test_normalize_number_keeps_only_digits():
    assert whatsapp._normalize_number("+55 (54) 99110-2959") == "+5554991102959"


def test_resolve_contact_by_name(monkeypatch):
    monkeypatch.setattr(whatsapp, "_get_config", lambda: _config_with())
    assert whatsapp._resolve_contact("fulano") == "+5554991102959"


def test_resolve_contact_unknown_name_returns_empty(monkeypatch):
    monkeypatch.setattr(whatsapp, "_get_config", lambda: _config_with())
    assert whatsapp._resolve_contact("ninguém") == ""


def test_resolve_contact_accepts_raw_number(monkeypatch):
    monkeypatch.setattr(whatsapp, "_get_config", lambda: _config_with())
    assert whatsapp._resolve_contact("+55 54 99110 2959") == "+5554991102959"


def test_send_blocks_number_outside_whitelist(monkeypatch):
    monkeypatch.setattr(whatsapp, "_get_config", lambda: _config_with())
    result = whatsapp.send("estranho", "oi")
    assert "segurança" in result.lower()
    assert "***7777" in result
    assert "+5511988887777" not in result


def test_send_blocks_unknown_contact(monkeypatch):
    monkeypatch.setattr(whatsapp, "_get_config", lambda: _config_with())
    result = whatsapp.send("ninguém", "oi")
    assert "não conheço" in result.lower()


def test_send_respects_enabled_flag(monkeypatch):
    monkeypatch.setattr(whatsapp, "_get_config", lambda: _config_with(**{"whatsapp.enabled": False}))
    result = whatsapp.send("fulano", "oi")
    assert "desabilitado" in result.lower()


def test_send_defaults_to_simulation_without_calling_pywhatkit(monkeypatch):
    monkeypatch.setattr(whatsapp, "_get_config", lambda: _config_with())

    fake_pywhatkit = types.ModuleType("pywhatkit")
    calls = []
    fake_pywhatkit.sendwhatmsg_instantly = lambda *args, **kwargs: calls.append(args)
    monkeypatch.setitem(sys.modules, "pywhatkit", fake_pywhatkit)

    result = whatsapp.send("fulano", "Oi!")

    assert calls == []
    assert "SIMULAÇÃO" in result
    assert "Nada foi enviado" in result


def test_mocked_live_send_calls_pywhatkit_only_with_all_locks(monkeypatch):
    monkeypatch.setattr(
        whatsapp,
        "_get_config",
        lambda: _config_with(**{
            "external_actions.mode": "live",
            "external_actions.live_enabled": True,
        }),
    )
    monkeypatch.setenv(LIVE_ENV_VAR, LIVE_ENV_TOKEN)

    fake_pywhatkit = types.ModuleType("pywhatkit")
    calls = []

    def fake_send(number, message, wait_time=20, tab_close=True, close_time=3):
        calls.append((number, message))

    fake_pywhatkit.sendwhatmsg_instantly = fake_send
    monkeypatch.setitem(sys.modules, "pywhatkit", fake_pywhatkit)

    result = whatsapp.send("fulano", "Oi! O que você está fazendo?")

    assert calls == [("+5554991102959", "Oi! O que você está fazendo?")]
    assert "enviada" in result.lower()


def test_send_without_pywhatkit_installed_returns_friendly_error(monkeypatch):
    monkeypatch.setattr(
        whatsapp,
        "_get_config",
        lambda: _config_with(**{
            "external_actions.mode": "live",
            "external_actions.live_enabled": True,
        }),
    )
    monkeypatch.setenv(LIVE_ENV_VAR, LIVE_ENV_TOKEN)
    monkeypatch.setitem(sys.modules, "pywhatkit", None)

    result = whatsapp.send("fulano", "oi")

    assert "pywhatkit" in result.lower()
