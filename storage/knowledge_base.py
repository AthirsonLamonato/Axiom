"""
storage/knowledge_base.py — Base de conhecimento estilo Obsidian
Memória persistente em Markdown + índice SQLite para busca rápida.

Estrutura em disco:
  data/kb/
  ├── memories/
  │   ├── preferences.md
  │   ├── projects.md
  │   ├── habits.md
  │   ├── corrections.md
  │   └── facts.md
  ├── conversations/
  │   └── 2026-06-13.md
  └── index.sqlite
"""

import json
import logging
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

KB_DIR   = Path("data/kb")
MEM_DIR  = KB_DIR / "memories"
CONV_DIR = KB_DIR / "conversations"
INDEX_DB = KB_DIR / "index.sqlite"

MEMORY_TYPES = ("preferences", "projects", "habits", "corrections", "facts")

_lock = threading.Lock()  # gravações thread-safe


# ── Bootstrap ──────────────────────────────────────────────────────────

def init():
    MEM_DIR.mkdir(parents=True, exist_ok=True)
    CONV_DIR.mkdir(parents=True, exist_ok=True)

    for t in MEMORY_TYPES:
        f = MEM_DIR / f"{t}.md"
        if not f.exists():
            f.write_text(
                f"---\ntype: {t}\ncreated_at: {_today()}\n---\n\n",
                encoding="utf-8",
            )

    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                type       TEXT NOT NULL,
                key        TEXT NOT NULL,
                content    TEXT NOT NULL,
                importance REAL    DEFAULT 0.5,
                updated_at TEXT    NOT NULL,
                tags       TEXT    DEFAULT '[]',
                UNIQUE(type, key)
            );
            CREATE INDEX IF NOT EXISTS idx_type ON memories(type);
            CREATE INDEX IF NOT EXISTS idx_imp  ON memories(importance DESC);
        """)
    logger.info("Knowledge base inicializada em %s", KB_DIR)


def _connect() -> sqlite3.Connection:
    INDEX_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(INDEX_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ── Gravação de memórias ───────────────────────────────────────────────

def save_memory(
    mem_type: str,
    key: str,
    content: str,
    importance: float = 0.5,
    tags: list[str] | None = None,
):
    """
    Salva ou atualiza uma entrada de memória no arquivo .md e no índice SQLite.

    mem_type: preferences | projects | habits | corrections | facts
    key:      identificador único dentro do tipo (ex: 'music_taste', 'response_style')
    content:  texto legível em português descrevendo a memória
    """
    if mem_type not in MEMORY_TYPES:
        mem_type = "facts"

    tags = tags or []
    key = re.sub(r"[^\w_-]", "_", key.lower().strip())[:60]
    importance = max(0.0, min(1.0, importance))
    today = _today()

    with _lock:
        _write_md(mem_type, key, content, importance, today)
        _index(mem_type, key, content, importance, today, tags)

    logger.debug("Memória salva: [%s] %s", mem_type, key)


def _write_md(mem_type: str, key: str, content: str, importance: float, date: str):
    path = MEM_DIR / f"{mem_type}.md"
    text = path.read_text(encoding="utf-8") if path.exists() else f"---\ntype: {mem_type}\n---\n\n"

    entry_marker = f"## {key}"
    new_block = (
        f"\n{entry_marker}\n"
        f"<!-- importance: {importance:.1f} | updated: {date} -->\n"
        f"{content.strip()}\n"
    )

    if entry_marker in text:
        # Substitui o bloco existente (do ## key até o próximo ## ou fim)
        pattern = rf"(## {re.escape(key)}\n)(.*?)(?=\n## |\Z)"
        replacement = new_block.lstrip("\n") + "\n"
        text = re.sub(pattern, replacement, text, flags=re.DOTALL)
    else:
        text = text.rstrip("\n") + "\n" + new_block

    path.write_text(text, encoding="utf-8")


def _index(mem_type, key, content, importance, date, tags):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO memories (type, key, content, importance, updated_at, tags) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(type, key) DO UPDATE SET "
            "content=excluded.content, importance=excluded.importance, "
            "updated_at=excluded.updated_at, tags=excluded.tags",
            (mem_type, key, content, importance, date, json.dumps(tags)),
        )


# ── Leitura e busca ────────────────────────────────────────────────────

def get_memories(mem_type: str | None = None, min_importance: float = 0.0) -> list[dict]:
    """Retorna entradas do índice, ordenadas por importância."""
    with _connect() as conn:
        if mem_type:
            rows = conn.execute(
                "SELECT type, key, content, importance, updated_at FROM memories "
                "WHERE type=? AND importance>=? ORDER BY importance DESC",
                (mem_type, min_importance),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT type, key, content, importance, updated_at FROM memories "
                "WHERE importance>=? ORDER BY importance DESC",
                (min_importance,),
            ).fetchall()
    return [dict(r) for r in rows]


def search_memories(query: str, limit: int = 5) -> list[dict]:
    """Busca semântica simples por palavras-chave no conteúdo."""
    words = [w.lower() for w in query.split() if len(w) > 3]
    if not words:
        return get_memories(min_importance=0.6)[:limit]

    with _connect() as conn:
        results = []
        for word in words:
            rows = conn.execute(
                "SELECT type, key, content, importance FROM memories "
                "WHERE lower(content) LIKE ? OR lower(key) LIKE ? "
                "ORDER BY importance DESC LIMIT ?",
                (f"%{word}%", f"%{word}%", limit),
            ).fetchall()
            for r in rows:
                if r not in results:
                    results.append(r)
    return [dict(r) for r in results[:limit]]


def build_context(query: str = "", max_entries: int = 8) -> str:
    """
    Monta o contexto de memória para injetar nos prompts do LLM.
    Sempre inclui entradas de alta importância + busca por relevância.
    """
    # Entradas de alta importância sempre presentes
    high = get_memories(min_importance=0.75)[:4]
    # Entradas relevantes para a query
    relevant = search_memories(query, limit=max_entries) if query else []
    # Junta sem duplicar
    seen_keys = {(e["type"], e["key"]) for e in high}
    combined = list(high) + [e for e in relevant if (e["type"], e["key"]) not in seen_keys]
    entries = combined[:max_entries]
    if not entries:
        return ""

    lines = ["[Memória do usuário]"]
    for e in entries:
        prefix = {"preferences": "Preferência", "habits": "Hábito",
                  "projects": "Projeto", "corrections": "Correção", "facts": "Fato"}.get(e["type"], "")
        lines.append(f"- {prefix}: {e['content']}")
    return "\n".join(lines)


# ── Log de conversas ───────────────────────────────────────────────────

def log_conversation(user_input: str, response: str):
    """Appenda o par pergunta/resposta no arquivo de conversa do dia."""
    today = _today()
    path = CONV_DIR / f"{today}.md"

    if not path.exists():
        path.write_text(
            f"---\ndate: {today}\n---\n\n",
            encoding="utf-8",
        )

    ts = datetime.now().strftime("%H:%M:%S")
    block = f"\n## {ts}\n\n**Você:** {user_input}\n\n**Paçoca:** {response}\n"

    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(block)


# ── Auto-aprendizado em background ────────────────────────────────────

def extract_and_learn(user_input: str, response: str):
    """
    Roda em thread background. Pede ao LLM para extrair fatos aprendíveis
    da troca atual e salva na base de conhecimento.
    """
    t = threading.Thread(
        target=_learn_worker,
        args=(user_input, response),
        daemon=True,
    )
    t.start()


def _learn_worker(user_input: str, response: str):
    """Extrai fatos aprendíveis em background via LLM. Opt-in via config."""
    try:
        from core.config import Config
        config = Config()
    except Exception:
        return

    # Opt-in: só aprende se habilitado explicitamente
    if not config.get("ai.auto_learn", False):
        return

    prompt = (
        "Analise esta troca e extraia fatos aprendíveis sobre o usuário. "
        "Retorne SOMENTE um JSON (array). Cada item: "
        '{"type":"preference|habit|project|correction|fact","key":"id_curto","content":"frase em português","importance":0.0-1.0} '
        "Retorne [] se não houver nada para aprender.\n\n"
        f"Usuário: {user_input}\nPaçoca: {response}"
    )

    try:
        from core.providers import get_client
        client = get_client(config)
        raw = client.chat(
            [{"role": "user", "content": prompt}],
            system="You extract learnable user facts from conversations. Always reply with valid JSON array only.",
            max_tokens=400,
        )
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return
        items = json.loads(match.group())
        for item in items:
            if isinstance(item, dict) and item.get("key") and item.get("content"):
                save_memory(
                    mem_type=item.get("type", "facts"),
                    key=item["key"],
                    content=item["content"],
                    importance=float(item.get("importance", 0.5)),
                )
    except Exception as e:
        logger.debug("extract_and_learn falhou: %s", e)


# ── Comandos de usuário ────────────────────────────────────────────────

def remember(statement: str) -> str:
    """
    Usuário diz 'lembra que X' — salva como fato/preferência.
    Usa LLM para classificar o tipo e extrair o key.
    """
    try:
        from core.config import Config
        from core.providers import get_client
        client = get_client(Config())
        raw = client.chat(
            [{"role": "user", "content": statement}],
            system='Classify this user statement. Reply JSON only: {"type":"preference|habit|project|correction|fact","key":"short_id","importance":0.5}',
            max_tokens=80,
        )
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            meta = json.loads(m.group())
            save_memory(
                mem_type=meta.get("type", "facts"),
                key=meta.get("key", "user_note"),
                content=statement,
                importance=float(meta.get("importance", 0.7)),
            )
            return f"Memorizado: {statement}"
    except Exception:
        pass

    # Fallback sem LLM
    save_memory("facts", "user_note", statement, importance=0.7)
    return f"Memorizado: {statement}"


def forget(key_or_content: str) -> str:
    """Remove uma memória pelo key ou por match de conteúdo."""
    with _lock:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT type, key FROM memories WHERE key=? OR lower(content) LIKE ?",
                (key_or_content.lower(), f"%{key_or_content.lower()}%"),
            ).fetchall()
            if not rows:
                return f"Não encontrei nenhuma memória sobre '{key_or_content}'."
            for r in rows:
                conn.execute("DELETE FROM memories WHERE type=? AND key=?", (r["type"], r["key"]))
                # Remove do .md
                path = MEM_DIR / f"{r['type']}.md"
                if path.exists():
                    text = path.read_text(encoding="utf-8")
                    pattern = rf"\n## {re.escape(r['key'])}\n.*?(?=\n## |\Z)"
                    text = re.sub(pattern, "", text, flags=re.DOTALL)
                    path.write_text(text, encoding="utf-8")
    keys = ", ".join(r["key"] for r in rows)
    return f"Esqueci: {keys}."


def show_memories(mem_type: str = "") -> str:
    """Retorna um resumo das memórias salvas."""
    entries = get_memories(mem_type or None, min_importance=0.0)
    if not entries:
        return "Nenhuma memória salva ainda."

    by_type: dict[str, list] = {}
    for e in entries:
        by_type.setdefault(e["type"], []).append(e)

    lines = []
    labels = {"preferences": "Preferências", "habits": "Hábitos",
               "projects": "Projetos", "corrections": "Correções", "facts": "Fatos"}
    for t, items in by_type.items():
        lines.append(f"\n**{labels.get(t, t.title())}**")
        for item in items:
            lines.append(f"  [{item['importance']:.1f}] {item['content']}")
    return "\n".join(lines).strip()


def cleanup_old_entries(cutoff_iso: str) -> int:
    """Remove memórias com importância baixa criadas antes de cutoff_iso. Retorna contagem."""
    try:
        with _lock:
            with _connect() as conn:
                cur = conn.execute(
                    "DELETE FROM memories WHERE created_at < ? AND importance < 0.4",
                    (cutoff_iso,),
                )
                return cur.rowcount
    except Exception:
        return 0

