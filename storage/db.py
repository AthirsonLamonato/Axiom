"""
storage/db.py — Banco de dados SQLite para histórico de comandos e sessões
"""

import sqlite3
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = "data/axiom.db"


def _connect() -> sqlite3.Connection:
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    """Cria as tabelas se não existirem."""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS command_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT    NOT NULL,
                command   TEXT    NOT NULL,
                response  TEXT,
                duration_ms INTEGER
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at   TEXT,
                mode       TEXT
            );

            CREATE TABLE IF NOT EXISTS transcriptions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT NOT NULL,
                filepath   TEXT NOT NULL,
                duration_s INTEGER
            );
        """)
    logger.info("Banco de dados inicializado")


def log_command(command: str, response: str, duration_ms: int = 0):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO command_history (ts, command, response, duration_ms) VALUES (?,?,?,?)",
            (datetime.now().isoformat(), command, response, duration_ms),
        )


def get_history(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT ts, command, response FROM command_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def log_transcription(filepath: str, duration_s: int = 0):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO transcriptions (ts, filepath, duration_s) VALUES (?,?,?)",
            (datetime.now().isoformat(), filepath, duration_s),
        )
