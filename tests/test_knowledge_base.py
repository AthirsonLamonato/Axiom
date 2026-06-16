"""
tests/test_knowledge_base.py — Testes para storage/knowledge_base.py

Cobre: migração idempotente do schema, fallback para busca por palavra-chave
quando embeddings não estão disponíveis (guarda de regressão), e ranking
semântico quando embeddings estão disponíveis (mockado — sem rede).
"""

import sqlite3

import pytest

import storage.knowledge_base as kb


@pytest.fixture
def fresh_kb(tmp_path, monkeypatch):
    kb_dir = tmp_path / "kb"
    monkeypatch.setattr(kb, "KB_DIR", kb_dir)
    monkeypatch.setattr(kb, "MEM_DIR", kb_dir / "memories")
    monkeypatch.setattr(kb, "CONV_DIR", kb_dir / "conversations")
    monkeypatch.setattr(kb, "INDEX_DB", kb_dir / "index.sqlite")
    kb.init()
    return kb_dir


def _columns(db_path) -> set:
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(memories)")}
    conn.close()
    return cols


# ── Migração ────────────────────────────────────────────────────────

def test_init_creates_embedding_columns(fresh_kb):
    cols = _columns(kb.INDEX_DB)
    assert "embedding" in cols
    assert "embedding_model" in cols


def test_init_is_idempotent(fresh_kb):
    kb.init()  # segunda chamada não deve levantar erro
    kb.init()
    cols = _columns(kb.INDEX_DB)
    assert "embedding" in cols
    assert "embedding_model" in cols


def test_migration_on_table_without_embedding_columns(tmp_path, monkeypatch):
    """Simula um banco pré-existente (de antes desta funcionalidade)."""
    kb_dir = tmp_path / "kb_old"
    monkeypatch.setattr(kb, "KB_DIR", kb_dir)
    monkeypatch.setattr(kb, "MEM_DIR", kb_dir / "memories")
    monkeypatch.setattr(kb, "CONV_DIR", kb_dir / "conversations")
    monkeypatch.setattr(kb, "INDEX_DB", kb_dir / "index.sqlite")

    kb_dir.mkdir(parents=True)
    conn = sqlite3.connect(kb_dir / "index.sqlite")
    conn.execute("""
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL, key TEXT NOT NULL, content TEXT NOT NULL,
            importance REAL DEFAULT 0.5, updated_at TEXT NOT NULL,
            tags TEXT DEFAULT '[]', UNIQUE(type, key)
        )
    """)
    conn.commit()
    conn.close()

    kb.init()  # deve migrar sem erro
    assert {"embedding", "embedding_model"} <= _columns(kb.INDEX_DB)


# ── Fallback para palavra-chave (sem embeddings configurados) ────────

def test_search_falls_back_to_keyword_when_no_embeddings(fresh_kb, monkeypatch):
    monkeypatch.setattr("core.embeddings.embed_text", lambda text, config=None: None)
    kb.save_memory("preferences", "music_taste", "Prefere rock e jazz", importance=0.8)
    kb.save_memory("facts", "city", "Mora em São Paulo", importance=0.5)

    results = kb.search_memories("jazz")
    assert any(r["key"] == "music_taste" for r in results)


def test_search_keyword_fallback_finds_nothing_for_unrelated_words(fresh_kb, monkeypatch):
    monkeypatch.setattr("core.embeddings.embed_text", lambda text, config=None: None)
    kb.save_memory("preferences", "music_taste", "Prefere rock e jazz", importance=0.8)

    # "ouvir"/"gosto" não aparecem no conteúdo salvo — busca por substring não acha nada
    results = kb.search_memories("o que eu gosto de ouvir")
    assert not any(r["key"] == "music_taste" for r in results)


# ── Busca semântica (embeddings mockados, sem rede) ───────────────────

def _fake_embed_factory(vectors: dict):
    """Mapa texto→vetor; usa um vetor 'neutro' para textos desconhecidos."""
    def _fake(text, config=None):
        for needle, vec in vectors.items():
            if needle in text:
                return vec
        return [0.0, 0.0, 1.0]
    return _fake


def test_search_semantic_finds_related_content_without_shared_words(fresh_kb, monkeypatch):
    vectors = {
        "rock e jazz": [1.0, 0.0, 0.0],
        "São Paulo": [0.0, 1.0, 0.0],
        "ouvir": [0.95, 0.05, 0.0],  # query semanticamente próxima de "rock e jazz"
    }
    monkeypatch.setattr("core.embeddings.embed_text", _fake_embed_factory(vectors))

    kb.save_memory("preferences", "music_taste", "Prefere rock e jazz", importance=0.8)
    kb.save_memory("facts", "city", "Mora em São Paulo", importance=0.5)

    # Busca por palavra-chave não acharia nada (nenhuma palavra em comum)
    results = kb.search_memories("o que eu gosto de ouvir")
    keys = [r["key"] for r in results]
    assert "music_taste" in keys
    assert "city" not in keys


def test_search_semantic_backfills_missing_embeddings(fresh_kb, monkeypatch):
    # Salva sem embeddings disponíveis (simula entrada antiga, pré-feature)
    monkeypatch.setattr("core.embeddings.embed_text", lambda text, config=None: None)
    kb.save_memory("facts", "old_entry", "rock e jazz favoritos", importance=0.9)

    conn = sqlite3.connect(kb.INDEX_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT embedding FROM memories WHERE key='old_entry'").fetchone()
    conn.close()
    assert row["embedding"] is None

    # Agora embeddings "ficam disponíveis" — search deve backfillar a entrada antiga
    vectors = {"rock e jazz": [1.0, 0.0, 0.0], "ouvir rock": [0.99, 0.01, 0.0]}
    monkeypatch.setattr("core.embeddings.embed_text", _fake_embed_factory(vectors))

    results = kb.search_memories("quero ouvir rock")
    assert any(r["key"] == "old_entry" for r in results)

    conn = sqlite3.connect(kb.INDEX_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT embedding FROM memories WHERE key='old_entry'").fetchone()
    conn.close()
    assert row["embedding"] is not None  # foi backfillado


# ── build_context ──────────────────────────────────────────────────

def test_build_context_smoke(fresh_kb, monkeypatch):
    monkeypatch.setattr("core.embeddings.embed_text", lambda text, config=None: None)
    kb.save_memory("preferences", "music_taste", "Prefere rock e jazz", importance=0.9)

    ctx = kb.build_context("jazz")
    assert "Prefere rock e jazz" in ctx
    assert ctx.startswith("[Memória do usuário]")


def test_build_context_empty_without_memories(fresh_kb, monkeypatch):
    monkeypatch.setattr("core.embeddings.embed_text", lambda text, config=None: None)
    assert kb.build_context("qualquer coisa") == ""


# ── cleanup_old_entries ────────────────────────────────────────────
# Regressão: a query antiga filtrava por uma coluna `created_at` que não
# existe na tabela `memories` — levantava sqlite3.OperationalError em toda
# chamada (mascarado por um `except Exception: return 0`), nunca removendo
# nada de fato.

def test_cleanup_old_entries_removes_low_importance_old_memory(fresh_kb, monkeypatch):
    monkeypatch.setattr("core.embeddings.embed_text", lambda text, config=None: None)
    kb.save_memory("facts", "old_low", "fato antigo e pouco importante", importance=0.2)

    removed = kb.cleanup_old_entries("2099-01-01")  # cutoff bem no futuro

    assert removed == 1
    assert kb.get_memories() == []


def test_cleanup_old_entries_keeps_high_importance_memory(fresh_kb, monkeypatch):
    monkeypatch.setattr("core.embeddings.embed_text", lambda text, config=None: None)
    kb.save_memory("facts", "old_high", "fato antigo mas importante", importance=0.9)

    removed = kb.cleanup_old_entries("2099-01-01")

    assert removed == 0
    assert len(kb.get_memories()) == 1


def test_cleanup_old_entries_keeps_recent_memory(fresh_kb, monkeypatch):
    monkeypatch.setattr("core.embeddings.embed_text", lambda text, config=None: None)
    kb.save_memory("facts", "recent_low", "fato recente e pouco importante", importance=0.1)

    removed = kb.cleanup_old_entries("2000-01-01")  # cutoff bem no passado

    assert removed == 0
    assert len(kb.get_memories()) == 1
