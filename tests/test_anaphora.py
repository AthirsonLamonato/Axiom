"""Testes para a resolução de anáfora/seguimento (modules/anaphora.py)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules import anaphora


def _with_last(monkeypatch, last):
    monkeypatch.setattr(anaphora, "_last_command", lambda: last)


def test_repeat_reissues_last_command(monkeypatch):
    _with_last(monkeypatch, "toca coldplay")
    assert anaphora.resolve("toca de novo") == "toca coldplay"
    assert anaphora.resolve("repete") == "toca coldplay"


def test_close_pronoun_targets_last_opened(monkeypatch):
    _with_last(monkeypatch, "abre o chrome")
    assert anaphora.resolve("fecha ele") == "fecha o chrome"


def test_ellipsis_agenda(monkeypatch):
    _with_last(monkeypatch, "agenda hoje")
    assert anaphora.resolve("e amanhã?") == "agenda amanhã"


def test_ellipsis_weather_place(monkeypatch):
    _with_last(monkeypatch, "como está o tempo")
    assert anaphora.resolve("e em Recife?") == "como está o tempo em recife"


def test_increment_inherits_adjust(monkeypatch):
    _with_last(monkeypatch, "aumenta o volume")
    assert anaphora.resolve("mais") == "aumenta o volume"


def test_non_followup_passes_through(monkeypatch):
    _with_last(monkeypatch, "abre o chrome")
    assert anaphora.resolve("toca queen") == "toca queen"


def test_no_history_passes_through(monkeypatch):
    _with_last(monkeypatch, "")
    assert anaphora.resolve("de novo") == "de novo"
