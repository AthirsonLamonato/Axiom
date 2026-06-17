"""
modules/semantic_router.py — Cache semântico de roteamento (camada 2.5)

Fica entre o classificador TF-IDF (camada 2) e o LLM (camada 3). Sempre que o
LLM resolve um comando novo em chamada(s) de ferramenta, o par
`comando → tool calls` é guardado com o embedding do comando. Da próxima vez,
uma paráfrase parecida é resolvida AQUI, localmente, sem nova chamada ao LLM —
o roteamento fica mais rápido e barato quanto mais o usuário usa.

Segurança contra erro de slot
-----------------------------
O risco de um cache semântico é devolver o argumento errado (ex.: cachear
"toca Coldplay" e reaproveitar para "toca Queen"). Por isso, ao recuperar um
acerto, exigimos que TODO valor de argumento em texto da chamada cacheada ainda
apareça (literalmente) no novo comando. Se não aparecer, ignoramos o acerto e
deixamos o LLM resolver. Comandos sem argumentos livres (a maioria) acertam
sempre; os parametrizados só acertam quando é realmente seguro.

Degrada com elegância: se não há backend de embeddings (ai.embeddings_provider
= none / indisponível), `recall()` e `remember()` viram no-ops silenciosos.
"""

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("data/semantic_cache.db")
_lock = threading.Lock()
_initialized = False


def _config():
    from core.config import Config
    return Config()


def _enabled() -> bool:
    try:
        return bool(_config().get("semantic_router.enabled", True))
    except Exception:
        return True


def _threshold() -> float:
    try:
        return float(_config().get("semantic_router.threshold", 0.90))
    except Exception:
        return 0.90


def _max_entries() -> int:
    try:
        return int(_config().get("semantic_router.max_entries", 500))
    except Exception:
        return 500


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init():
    global _initialized
    if _initialized:
        return
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_cache (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                command    TEXT NOT NULL UNIQUE,
                embedding  BLOB NOT NULL,
                model      TEXT NOT NULL,
                calls_json TEXT NOT NULL,
                hits       INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_used  TEXT NOT NULL
            )
        """)
    _initialized = True


def _embed(text: str):
    """Embedding do comando, ou None se indisponível (nunca levanta)."""
    try:
        from core.embeddings import embed_text
        return embed_text(text)
    except Exception:
        return None


def _arg_values(calls: list[dict]) -> list[str]:
    """Extrai valores de argumento em texto (para o guard de slot)."""
    out = []
    for call in calls:
        for v in (call.get("arguments") or {}).values():
            if isinstance(v, str) and v.strip():
                out.append(v.strip().lower())
    return out


# ── API pública ────────────────────────────────────────────────────────

def remember(command: str, calls: list[dict]) -> None:
    """Guarda o mapeamento comando → tool calls com o embedding do comando."""
    if not _enabled() or not command or not calls:
        return
    command = command.strip()
    if not command:
        return
    vec = _embed(command)
    if not vec:  # sem backend de embeddings → no-op
        return

    try:
        from core.embeddings import pack_embedding
        from core.config import Config
        model = Config().get("ai.embeddings_model", "gemini-embedding-001")
        blob = pack_embedding(vec)
        calls_json = json.dumps(calls, ensure_ascii=False)
    except Exception as e:
        logger.debug("semantic_router.remember: serialização falhou: %s", e)
        return

    _init()
    now = datetime.now().isoformat()
    with _lock:
        try:
            with _connect() as conn:
                conn.execute(
                    "INSERT INTO semantic_cache (command, embedding, model, calls_json, hits, created_at, last_used) "
                    "VALUES (?,?,?,?,0,?,?) "
                    "ON CONFLICT(command) DO UPDATE SET "
                    "  embedding=excluded.embedding, model=excluded.model, "
                    "  calls_json=excluded.calls_json, last_used=excluded.last_used",
                    (command.lower(), blob, model, calls_json, now, now),
                )
                _enforce_limit(conn)
            logger.debug("semantic_router: memorizado %r → %s", command, [c.get("name") for c in calls])
        except Exception as e:
            logger.debug("semantic_router.remember falhou: %s", e)


def _enforce_limit(conn: sqlite3.Connection) -> None:
    limit = _max_entries()
    count = conn.execute("SELECT COUNT(*) AS n FROM semantic_cache").fetchone()["n"]
    if count > limit:
        # remove os menos úteis: menor hits, mais antigos no uso
        conn.execute(
            "DELETE FROM semantic_cache WHERE id IN ("
            "  SELECT id FROM semantic_cache ORDER BY hits ASC, last_used ASC LIMIT ?"
            ")",
            (count - limit,),
        )


def recall(command: str) -> list[dict] | None:
    """Tenta resolver `command` por similaridade com comandos já vistos.

    Retorna a lista de tool calls cacheada se houver acerto seguro acima do
    limiar, ou None (deixando o LLM resolver).
    """
    if not _enabled() or not command or not command.strip():
        return None
    _init()

    # Atalho barato: se o cache está vazio, nem calcula embedding.
    try:
        with _connect() as conn:
            if conn.execute("SELECT COUNT(*) AS n FROM semantic_cache").fetchone()["n"] == 0:
                return None
            rows = conn.execute(
                "SELECT id, command, embedding, calls_json, hits FROM semantic_cache"
            ).fetchall()
    except Exception:
        return None

    vec = _embed(command)
    if not vec:
        return None

    from core.embeddings import unpack_embedding, cosine_similarity
    threshold = _threshold()
    cmd_lower = command.lower()

    best = None
    best_sim = 0.0
    for row in rows:
        try:
            stored = unpack_embedding(row["embedding"])
        except Exception:
            continue
        sim = cosine_similarity(vec, stored)
        if sim > best_sim:
            best_sim = sim
            best = row

    if best is None or best_sim < threshold:
        return None

    try:
        calls = json.loads(best["calls_json"])
    except Exception:
        return None

    # Guard de slot: todo valor de argumento em texto precisa estar no comando.
    for val in _arg_values(calls):
        if val not in cmd_lower:
            logger.debug(
                "semantic_router: acerto descartado (sim=%.3f) — slot %r ausente em %r",
                best_sim, val, command,
            )
            return None

    # Confere que as ferramentas ainda existem (evita cache obsoleto).
    try:
        from modules.tools import known_tools
        valid = known_tools()
        if any(c.get("name") not in valid for c in calls):
            return None
    except Exception:
        pass

    with _lock:
        try:
            with _connect() as conn:
                conn.execute(
                    "UPDATE semantic_cache SET hits=hits+1, last_used=? WHERE id=?",
                    (datetime.now().isoformat(), best["id"]),
                )
        except Exception:
            pass

    logger.info("semantic_router: acerto (sim=%.3f) %r → %s",
                best_sim, command, [c.get("name") for c in calls])
    return calls


def stats(*_) -> str:
    """Resumo do cache semântico (comando de voz/texto)."""
    if not _enabled():
        return "Cache semântico desativado (semantic_router.enabled: false)."
    _init()
    try:
        with _connect() as conn:
            n = conn.execute("SELECT COUNT(*) AS n FROM semantic_cache").fetchone()["n"]
            hits = conn.execute("SELECT COALESCE(SUM(hits),0) AS h FROM semantic_cache").fetchone()["h"]
    except Exception as e:
        return f"Erro ao consultar cache semântico: {e}"
    return (f"Cache semântico: {n} comando(s) memorizado(s), "
            f"{hits} acerto(s) servido(s) sem LLM.")


def clear(*_) -> str:
    _init()
    with _lock:
        try:
            with _connect() as conn:
                conn.execute("DELETE FROM semantic_cache")
        except Exception as e:
            return f"Erro ao limpar cache semântico: {e}"
    return "Cache semântico limpo."
