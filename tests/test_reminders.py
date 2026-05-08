"""Testes para modules/reminders.py"""

import os
import sys
import pytest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.reminders import _parse_fire_time, _extract_message, add, list_reminders, cancel, _reminders, _lock


@pytest.fixture(autouse=True)
def reset_reminders():
    with _lock:
        _reminders.clear()
    yield
    with _lock:
        _reminders.clear()


# ── _parse_fire_time ──────────────────────────────────────────────────

def test_parse_em_minutos():
    t = _parse_fire_time("em 30 minutos")
    assert t is not None
    delta = (t - datetime.now()).total_seconds() / 60
    assert 28 < delta < 32


def test_parse_em_horas():
    t = _parse_fire_time("em 2 horas")
    assert t is not None
    delta = (t - datetime.now()).total_seconds() / 3600
    assert 1.9 < delta < 2.1


def test_parse_as_hora_com_acento():
    t = _parse_fire_time("às 10h30")
    assert t is not None
    assert t.hour == 10
    assert t.minute == 30


def test_parse_as_hora_sem_acento():
    t = _parse_fire_time("as 10h30")
    assert t is not None
    assert t.hour == 10
    assert t.minute == 30


def test_parse_as_com_dois_pontos():
    t = _parse_fire_time("às 14:45")
    assert t is not None
    assert t.hour == 14
    assert t.minute == 45


def test_parse_hora_no_passado_avanca_dia():
    passado = (datetime.now() - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    raw = f"às {passado.hour}h00"
    t = _parse_fire_time(raw)
    assert t is not None
    assert t > datetime.now()


def test_parse_invalido_retorna_none():
    assert _parse_fire_time("texto aleatório sem horário") is None


# ── _extract_message ──────────────────────────────────────────────────

def test_extract_remove_em_minutos():
    msg = _extract_message("em 30 minutos de fazer backup")
    assert "30 minutos" not in msg
    assert "backup" in msg


def test_extract_remove_as_hora():
    msg = _extract_message("às 15h de reunião")
    assert "15h" not in msg
    assert "reunião" in msg


def test_extract_remove_me_lembra():
    msg = _extract_message("me lembra em 10 minutos de ligar")
    assert "me lembra" not in msg
    assert "ligar" in msg


# ── Funções públicas ──────────────────────────────────────────────────

def test_add_retorna_confirmacao():
    result = add("em 60 minutos de testar")
    assert "Lembrete" in result
    assert "#" in result


def test_add_horario_invalido_retorna_erro():
    result = add("oi tudo bem")
    assert "Não entendi" in result or "exemplos" in result.lower()


def test_list_reminders_vazio():
    result = list_reminders()
    assert "Nenhum" in result


def test_list_reminders_com_entry():
    add("em 60 minutos de teste")
    result = list_reminders()
    assert "teste" in result


def test_cancel_todos():
    add("em 60 minutos de a")
    add("em 90 minutos de b")
    result = cancel()
    assert "cancelado" in result.lower()
    assert list_reminders() == "Nenhum lembrete pendente."


def test_cancel_por_id():
    add("em 60 minutos de alvo")
    with _lock:
        rid = max(_reminders.keys())
    result = cancel(str(rid))
    assert str(rid) in result
    assert "cancelado" in result.lower()
