"""
modules/obsidian.py — Exportação para Obsidian / qualquer vault Markdown
Exporta notas, transcrições e sumários para o vault configurado.
Config: obsidian.vault_path  (ex: C:/Users/user/Documents/Obsidian/Axiom)
"""

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _get_config():
    from core.config import Config
    return Config()


def _vault_path() -> str:
    config = _get_config()
    path = config.get("obsidian.vault_path", "")
    if not path:
        return ""
    return os.path.expanduser(path)


def _ensure_vault(subdir: str = "") -> Optional[str]:
    vault = _vault_path()
    if not vault:
        return None
    full = os.path.join(vault, subdir) if subdir else vault
    os.makedirs(full, exist_ok=True)
    return full


def _write_note(filepath: str, content: str) -> str:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


# ── Exportações ───────────────────────────────────────────────────────

def export_transcription(*_) -> str:
    """Exporta a última transcrição para o vault do Obsidian."""
    vault_dir = _ensure_vault("Transcrições")
    if not vault_dir:
        return (
            "Vault do Obsidian não configurado.\n"
            "Defina em config.yaml: obsidian.vault_path: /caminho/para/vault"
        )

    from storage.file_store import load_last_transcription
    text = load_last_transcription()
    if not text:
        return "Nenhuma transcrição disponível para exportar."

    ts = datetime.now()
    filename = f"Transcrição {ts.strftime('%Y-%m-%d %H-%M')}.md"
    filepath = os.path.join(vault_dir, filename)

    frontmatter = (
        f"---\n"
        f"date: {ts.strftime('%Y-%m-%d')}\n"
        f"time: {ts.strftime('%H:%M')}\n"
        f"tags: [axiom, transcrição]\n"
        f"---\n\n"
    )
    _write_note(filepath, frontmatter + text)
    logger.info("Transcrição exportada: %s", filepath)
    return f"Transcrição exportada para: {filepath}"


def export_summary(*_) -> str:
    """Gera e exporta o sumário da última reunião para o vault."""
    vault_dir = _ensure_vault("Reuniões")
    if not vault_dir:
        return "Vault do Obsidian não configurado. Defina obsidian.vault_path em config.yaml."

    from modules.summarizer import summarize_meeting
    summary = summarize_meeting()
    if summary.startswith("Nenhuma transcrição"):
        return summary

    ts = datetime.now()
    filename = f"Reunião {ts.strftime('%Y-%m-%d %H-%M')}.md"
    filepath = os.path.join(vault_dir, filename)

    frontmatter = (
        f"---\n"
        f"date: {ts.strftime('%Y-%m-%d')}\n"
        f"time: {ts.strftime('%H:%M')}\n"
        f"tags: [axiom, reunião, sumário]\n"
        f"---\n\n"
    )
    _write_note(filepath, frontmatter + summary)
    logger.info("Sumário exportado: %s", filepath)
    return f"Sumário da reunião exportado para: {filepath}"


def daily_note(*_) -> str:
    """Cria ou atualiza a nota diária com o histórico de comandos do dia."""
    vault_dir = _ensure_vault("Notas Diárias")
    if not vault_dir:
        return "Vault do Obsidian não configurado. Defina obsidian.vault_path em config.yaml."

    today = datetime.now()
    filename = f"{today.strftime('%Y-%m-%d')}.md"
    filepath = os.path.join(vault_dir, filename)

    from storage.db import get_history
    rows = get_history(limit=50)
    today_str = today.strftime("%Y-%m-%d")
    today_rows = [r for r in rows if r["ts"].startswith(today_str)]

    lines = [
        f"---\ndate: {today_str}\ntags: [axiom, diário]\n---\n",
        f"# {today.strftime('%d/%m/%Y')} — Nota Diária Axiom\n",
    ]

    if today_rows:
        lines.append("\n## Comandos do dia\n")
        for row in reversed(today_rows):
            ts = row["ts"][11:16]
            lines.append(f"- `{ts}` {row['command']}")
    else:
        lines.append("\n*Nenhum comando registrado hoje.*")

    _write_note(filepath, "\n".join(lines))
    logger.info("Nota diária: %s", filepath)
    return f"Nota diária criada/atualizada: {filepath}"


def export_notes_plugin(*_) -> str:
    """Exporta as anotações do plugin notes.py para o vault."""
    vault_dir = _ensure_vault("Notas")
    if not vault_dir:
        return "Vault do Obsidian não configurado. Defina obsidian.vault_path em config.yaml."

    notes_file = "data/notes.md"
    if not os.path.exists(notes_file):
        return "Nenhuma nota encontrada. Use 'anota [texto]' para criar notas."

    with open(notes_file, encoding="utf-8") as f:
        content = f.read()

    ts = datetime.now()
    filename = f"Notas Axiom {ts.strftime('%Y-%m-%d')}.md"
    filepath = os.path.join(vault_dir, filename)

    frontmatter = f"---\ndate: {ts.strftime('%Y-%m-%d')}\ntags: [axiom, notas]\n---\n\n"
    _write_note(filepath, frontmatter + content)
    return f"Notas exportadas para: {filepath}"
