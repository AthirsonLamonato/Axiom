"""
storage/file_store.py — Persistência de transcrições, resumos e arquivos gerais
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

TRANSCRIPTION_DIR = "data/transcriptions"
SUMMARY_DIR = "data/summaries"


def save_transcription(text: str, start_time: datetime = None) -> str:
    """Salva uma transcrição em arquivo Markdown."""
    os.makedirs(TRANSCRIPTION_DIR, exist_ok=True)
    ts = (start_time or datetime.now()).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(TRANSCRIPTION_DIR, f"transcricao_{ts}.md")

    header = f"# Transcrição — {(start_time or datetime.now()).strftime('%d/%m/%Y %H:%M')}\n\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + text)

    logger.info(f"Transcrição salva: {path}")
    return path


def load_last_transcription() -> str:
    """Carrega a transcrição mais recente."""
    if not os.path.exists(TRANSCRIPTION_DIR):
        return ""
    files = sorted(
        [f for f in os.listdir(TRANSCRIPTION_DIR) if f.endswith(".md")],
        reverse=True,
    )
    if not files:
        return ""
    path = os.path.join(TRANSCRIPTION_DIR, files[0])
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_summary(text: str, title: str = "resumo") -> str:
    """Salva um resumo em arquivo Markdown."""
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SUMMARY_DIR, f"{title}_{ts}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {title.capitalize()} — {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n")
        f.write(text)
    logger.info(f"Resumo salvo: {path}")
    return path


def save_text(text: str, prefix: str = "file", ext: str = "txt") -> str:
    """Salva texto genérico em data/."""
    os.makedirs("data", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join("data", f"{prefix}_{ts}.{ext}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def save_all_pending() -> str:
    """Stub — garante que arquivos pendentes sejam persistidos."""
    return "Arquivos salvos."
