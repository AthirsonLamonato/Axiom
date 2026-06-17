"""
storage/memory.py — Memória persistente de longo prazo
Registra interações, preferências, vocabulário aprendido e padrões de uso.
"""

import sqlite3
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = "data/memory.db"


def _connect() -> sqlite3.Connection:
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init():
    with _connect() as conn:
        conn.executescript("""
            -- Cada interação registrada com resultado
            CREATE TABLE IF NOT EXISTS interactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL,
                raw_input   TEXT    NOT NULL,
                resolved    TEXT,           -- comando após correção de vocabulário
                action      TEXT,           -- ferramenta/rota que foi executada
                response    TEXT,
                success     INTEGER DEFAULT 1,  -- 1=ok, 0=falhou/não entendeu
                source      TEXT    DEFAULT 'voice'  -- voice | text
            );

            -- Vocabulário aprendido: o que o Whisper escuta → o que o usuário quis dizer
            CREATE TABLE IF NOT EXISTS vocabulary (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                heard       TEXT    NOT NULL UNIQUE,  -- o que foi transcrito
                intended    TEXT    NOT NULL,          -- o que o usuário quis dizer
                confidence  REAL    DEFAULT 1.0,
                uses        INTEGER DEFAULT 1,
                created_at  TEXT    NOT NULL
            );

            -- Preferências do usuário (chave-valor)
            CREATE TABLE IF NOT EXISTS preferences (
                key         TEXT    PRIMARY KEY,
                value       TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            );

            -- Apps e recursos mais usados
            CREATE TABLE IF NOT EXISTS usage_stats (
                resource    TEXT    PRIMARY KEY,  -- nome do app, site, artista, etc.
                category    TEXT    NOT NULL,     -- app | music | browser | playlist
                count       INTEGER DEFAULT 1,
                last_used   TEXT    NOT NULL
            );

            -- Padrões aprendidos: frases que o usuário usa frequentemente
            CREATE TABLE IF NOT EXISTS learned_patterns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern     TEXT    NOT NULL UNIQUE,
                action      TEXT    NOT NULL,   -- "modules.x:func"
                param       TEXT,               -- parâmetro extraído
                hits        INTEGER DEFAULT 1,
                created_at  TEXT    NOT NULL
            );

            -- Confiança aprendida para confirmações (reduz fadiga de confirmação)
            CREATE TABLE IF NOT EXISTS confirm_trust (
                tool        TEXT    PRIMARY KEY,  -- nome da ferramenta
                approvals   INTEGER DEFAULT 0,    -- total de aprovações
                denials     INTEGER DEFAULT 0,    -- total de negações
                streak      INTEGER DEFAULT 0,    -- aprovações consecutivas (zera ao negar)
                updated_at  TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_interactions_ts ON interactions(ts);
            CREATE INDEX IF NOT EXISTS idx_usage_count ON usage_stats(count DESC);
        """)
    logger.info("Memory DB inicializado")


# ── Interações ─────────────────────────────────────────────────────────

def log_interaction(raw_input: str, response: str, action: str = "",
                    resolved: str = "", success: bool = True, source: str = "voice"):
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO interactions (ts, raw_input, resolved, action, response, success, source) "
                "VALUES (?,?,?,?,?,?,?)",
                (datetime.now().isoformat(), raw_input, resolved or raw_input,
                 action, response, int(success), source),
            )
    except Exception as e:
        logger.error("Erro ao registrar interação: %s", e)


def get_recent(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT ts, raw_input, action, response, success FROM interactions "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Vocabulário ────────────────────────────────────────────────────────

def add_vocabulary(heard: str, intended: str, confidence: float = 1.0):
    heard = heard.lower().strip()
    intended = intended.lower().strip()
    if heard == intended:
        return
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO vocabulary (heard, intended, confidence, uses, created_at) "
                "VALUES (?,?,?,1,?) "
                "ON CONFLICT(heard) DO UPDATE SET "
                "  intended=excluded.intended, "
                "  confidence=MAX(confidence, excluded.confidence), "
                "  uses=uses+1",
                (heard, intended, confidence, datetime.now().isoformat()),
            )
    except Exception as e:
        logger.error("Erro ao salvar vocabulário: %s", e)


def get_vocabulary() -> dict[str, str]:
    """Retorna {heard: intended} para correção de transcrições."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT heard, intended FROM vocabulary WHERE confidence >= 0.7 ORDER BY uses DESC"
            ).fetchall()
        return {r["heard"]: r["intended"] for r in rows}
    except Exception:
        return {}


def apply_vocabulary(text: str) -> str:
    """Aplica correções de vocabulário aprendido ao texto transcrito."""
    vocab = get_vocabulary()
    if not vocab:
        return text
    text_lower = text.lower()
    for heard, intended in vocab.items():
        if heard in text_lower:
            text_lower = text_lower.replace(heard, intended)
    # Preserva capitalização original da primeira letra
    return text_lower[0].upper() + text_lower[1:] if text_lower else text


# ── Preferências ───────────────────────────────────────────────────────

def set_preference(key: str, value: str):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO preferences (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, datetime.now().isoformat()),
        )


def get_preference(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def get_all_preferences() -> dict[str, str]:
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM preferences").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ── Estatísticas de uso ────────────────────────────────────────────────

def record_usage(resource: str, category: str):
    """Registra uso de um app, site, música, etc."""
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO usage_stats (resource, category, count, last_used) VALUES (?,?,1,?) "
                "ON CONFLICT(resource) DO UPDATE SET count=count+1, last_used=excluded.last_used",
                (resource.lower().strip(), category, datetime.now().isoformat()),
            )
    except Exception as e:
        logger.error("Erro ao registrar uso: %s", e)


def get_top_used(category: str = "", limit: int = 10) -> list[dict]:
    with _connect() as conn:
        if category:
            rows = conn.execute(
                "SELECT resource, count FROM usage_stats WHERE category=? ORDER BY count DESC LIMIT ?",
                (category, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT resource, category, count FROM usage_stats ORDER BY count DESC LIMIT ?",
                (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


# ── Padrões aprendidos ─────────────────────────────────────────────────

def add_learned_pattern(pattern: str, action: str, param: str = ""):
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO learned_patterns (pattern, action, param, hits, created_at) VALUES (?,?,?,1,?) "
                "ON CONFLICT(pattern) DO UPDATE SET hits=hits+1",
                (pattern.lower().strip(), action, param, datetime.now().isoformat()),
            )
    except Exception as e:
        logger.error("Erro ao salvar padrão: %s", e)


def get_learned_patterns() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT pattern, action, param FROM learned_patterns WHERE hits >= 2 ORDER BY hits DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Confiança aprendida (confirmações) ─────────────────────────────────

def record_confirmation(tool: str, approved: bool):
    """Registra o resultado de uma confirmação para uma ferramenta.

    Aprovar incrementa a sequência consecutiva (streak); negar a zera. Isso
    permite que o sistema deixe de perguntar por ações de risco médio que o
    usuário sempre aprova, sem nunca afrouxar ações de risco alto.
    """
    tool = (tool or "").strip()
    if not tool:
        return
    try:
        with _connect() as conn:
            if approved:
                conn.execute(
                    "INSERT INTO confirm_trust (tool, approvals, denials, streak, updated_at) "
                    "VALUES (?,1,0,1,?) "
                    "ON CONFLICT(tool) DO UPDATE SET "
                    "  approvals=approvals+1, streak=streak+1, updated_at=excluded.updated_at",
                    (tool, datetime.now().isoformat()),
                )
            else:
                conn.execute(
                    "INSERT INTO confirm_trust (tool, approvals, denials, streak, updated_at) "
                    "VALUES (?,0,1,0,?) "
                    "ON CONFLICT(tool) DO UPDATE SET "
                    "  denials=denials+1, streak=0, updated_at=excluded.updated_at",
                    (tool, datetime.now().isoformat()),
                )
    except Exception as e:
        logger.error("Erro ao registrar confiança de confirmação: %s", e)


def get_trust(tool: str) -> dict:
    """Retorna {approvals, denials, streak} para a ferramenta (zeros se inédita)."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT approvals, denials, streak FROM confirm_trust WHERE tool=?", (tool,)
            ).fetchone()
        return dict(row) if row else {"approvals": 0, "denials": 0, "streak": 0}
    except Exception:
        return {"approvals": 0, "denials": 0, "streak": 0}


def get_all_trust() -> list[dict]:
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT tool, approvals, denials, streak FROM confirm_trust ORDER BY streak DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def reset_trust(tool: str = "") -> None:
    """Zera a confiança de uma ferramenta, ou de todas se `tool` vazio."""
    try:
        with _connect() as conn:
            if tool:
                conn.execute("DELETE FROM confirm_trust WHERE tool=?", (tool,))
            else:
                conn.execute("DELETE FROM confirm_trust")
    except Exception as e:
        logger.error("Erro ao resetar confiança: %s", e)


# ── Resumo para contexto ───────────────────────────────────────────────

def build_memory_context() -> str:
    """Monta um resumo da memória do usuário para injetar nos prompts."""
    lines = []

    prefs = get_all_preferences()
    if prefs:
        lines.append("Preferências do usuário: " + ", ".join(f"{k}={v}" for k, v in prefs.items()))

    top_apps = get_top_used("app", 5)
    if top_apps:
        lines.append("Apps mais usados: " + ", ".join(r["resource"] for r in top_apps))

    top_music = get_top_used("music", 3)
    if top_music:
        lines.append("Músicas/playlists favoritas: " + ", ".join(r["resource"] for r in top_music))

    top_sites = get_top_used("browser", 3)
    if top_sites:
        lines.append("Sites frequentes: " + ", ".join(r["resource"] for r in top_sites))

    return "\n".join(lines)
