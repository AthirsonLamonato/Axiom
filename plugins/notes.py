"""
plugins/notes.py — Anotações rápidas por voz
Plugin de exemplo funcional que acompanha o Axiom.
"""

import os
from datetime import datetime

NAME        = "notes"
VERSION     = "1.0.0"
DESCRIPTION = "Anotações rápidas salvas em data/notes.md"

NOTES_FILE = "data/notes.md"

ROUTES = [
    (r"anota\s+(.+)",                                   "plugins.notes:add_note",   False),
    (r"(minhas|últimas|ultimas)\s+anota[çc][õo]es",    "plugins.notes:show_notes", False),
    (r"(busca|pesquisa)\s+na[s]?\s+anota[çc][õo]es\s+(.+)", "plugins.notes:search_notes", False),
    (r"limpa\s+anota[çc][õo]es",                       "plugins.notes:clear_notes", True),
]


def add_note(text: str, *_) -> str:
    os.makedirs("data", exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"- [{timestamp}] {text.strip()}\n"
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    return f"Anotado: {text.strip()}"


def show_notes(*_) -> str:
    if not os.path.exists(NOTES_FILE):
        return "Nenhuma anotação encontrada."
    with open(NOTES_FILE, encoding="utf-8") as f:
        lines = [l for l in f.readlines() if l.strip()]
    if not lines:
        return "Nenhuma anotação encontrada."
    recent = lines[-10:]
    header = f"Últimas {len(recent)} anotação(ões):"
    return header + "\n" + "".join(recent).strip()


def search_notes(query: str, *_) -> str:
    if not os.path.exists(NOTES_FILE):
        return "Nenhuma anotação encontrada."
    with open(NOTES_FILE, encoding="utf-8") as f:
        lines = f.readlines()
    matches = [l.strip() for l in lines if query.lower() in l.lower()]
    if not matches:
        return f"Nenhuma anotação contém '{query}'."
    return f"Anotações com '{query}':\n" + "\n".join(matches)


def clear_notes(*_) -> str:
    if os.path.exists(NOTES_FILE):
        os.remove(NOTES_FILE)
        return "Todas as anotações foram apagadas."
    return "Nenhuma anotação para apagar."
