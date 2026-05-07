"""Testes para storage/db.py"""

import os
import sys
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import storage.db as db


def _make_connect(db_path):
    def _connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    return _connect


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "axiom_test.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "_connect", _make_connect(db_path))
    db.init()
    return db_path


def test_init_creates_tables(fresh_db):
    conn = sqlite3.connect(fresh_db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert {"command_history", "sessions", "transcriptions"} <= tables


def test_log_command(fresh_db):
    db.log_command("abre o chrome", "Abrindo chrome.", duration_ms=42)

    conn = sqlite3.connect(fresh_db)
    row = conn.execute(
        "SELECT command, response, duration_ms FROM command_history"
    ).fetchone()
    conn.close()

    assert row[0] == "abre o chrome"
    assert row[1] == "Abrindo chrome."
    assert row[2] == 42


def test_get_history_order(fresh_db):
    db.log_command("primeiro", "resp1")
    db.log_command("segundo", "resp2")

    history = db.get_history(limit=10)
    assert len(history) == 2
    assert history[0]["command"] == "segundo"  # DESC
    assert history[1]["command"] == "primeiro"


def test_get_history_respects_limit(fresh_db):
    for i in range(10):
        db.log_command(f"cmd_{i}", f"resp_{i}")

    history = db.get_history(limit=3)
    assert len(history) == 3


def test_log_transcription(fresh_db):
    db.log_transcription("data/transcricao_test.md", duration_s=120)

    conn = sqlite3.connect(fresh_db)
    row = conn.execute("SELECT filepath, duration_s FROM transcriptions").fetchone()
    conn.close()

    assert row[0] == "data/transcricao_test.md"
    assert row[1] == 120


def test_idempotent_init(fresh_db):
    """Chamar init() duas vezes não deve quebrar."""
    db.init()
    db.init()
    history = db.get_history()
    assert isinstance(history, list)
