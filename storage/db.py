"""
storage/db.py — Banco de dados SQLite para histórico de comandos e sessões
"""

import sqlite3
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = "data/pacoca.db"


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

            CREATE INDEX IF NOT EXISTS idx_command_history_ts ON command_history (ts);
            CREATE INDEX IF NOT EXISTS idx_transcriptions_ts ON transcriptions (ts);
            CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions (started_at);
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


def cleanup_old_data(days: int = 30) -> str:
    """
    Remove dados antigos do banco e arquivos de log/transcrição.
    Política: mantém os últimos `days` dias.
    days <= 0 é tratado como desabilitado (retorna sem apagar nada).
    """
    if days <= 0:
        return "Limpeza ignorada: privacy.retention_days=0 (desabilitado)."

    from pathlib import Path
    from datetime import timedelta

    cutoff_dt = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff_dt.isoformat()

    removed: dict = {"commands": 0, "transcriptions": 0, "sessions": 0, "files": 0}
    with _connect() as conn:
        cur = conn.execute("DELETE FROM command_history WHERE ts < ?", (cutoff_str,))
        removed["commands"] = cur.rowcount
        cur = conn.execute("DELETE FROM transcriptions WHERE ts < ?", (cutoff_str,))
        removed["transcriptions"] = cur.rowcount
        # Tabela de sessões (se existir)
        try:
            cur = conn.execute(
                "DELETE FROM sessions WHERE started_at < ? AND ended_at IS NOT NULL",
                (cutoff_str,),
            )
            removed["sessions"] = cur.rowcount
        except Exception:
            pass

    # Remove arquivos antigos: transcrições (.md, .txt), áudios (.wav, .mp3)
    _FILE_GLOBS = ["*.md", "*.txt", "*.wav", "*.mp3", "*.flac"]
    _SEARCH_DIRS = [
        Path("data/transcriptions"),
        Path("data/audio"),
        Path("data/recordings"),
    ]
    for d in _SEARCH_DIRS:
        if d.exists():
            for pattern in _FILE_GLOBS:
                for f in d.glob(pattern):
                    try:
                        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff_dt:
                            f.unlink()
                            removed["files"] += 1
                    except Exception:
                        pass

    # Limpa entradas antigas na knowledge base (se suportado)
    try:
        from storage.knowledge_base import cleanup_old_entries
        kb_removed = cleanup_old_entries(cutoff_str)
        if kb_removed:
            removed["kb_entries"] = kb_removed
    except Exception:
        pass

    # Trunca log se maior que 50 MB
    log_path = Path("logs/pacoca.log")
    if log_path.exists() and log_path.stat().st_size > 50 * 1024 * 1024:
        try:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            log_path.write_text("\n".join(lines[-5000:]) + "\n", encoding="utf-8")
            removed["log_truncated"] = True
        except Exception:
            pass

    logger.info("Limpeza: %s", removed)
    parts = [f"{v} {k}" for k, v in removed.items() if isinstance(v, int) and v > 0]
    summary = ", ".join(parts) if parts else "nada a remover"
    return f"Limpeza concluída (últimos {days} dias mantidos): {summary}."
