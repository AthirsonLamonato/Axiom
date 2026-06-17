"""
input/cli.py — Interface de linha de comando interativa
Usado em modo --mode text ou como fallback do modo voz.
"""

import logging

try:
    import readline  # habilita histórico e navegação no Linux/Mac (não disponível no Windows)
except ImportError:
    pass

logger = logging.getLogger(__name__)

BANNER = """
╭────────────────────────────────────────────╮
│ Paçoca                                     │
│ Assistente pessoal · modo texto            │
├────────────────────────────────────────────┤
│ ajuda  mostra comandos e exemplos          │
│ sair   encerra a sessão                    │
╰────────────────────────────────────────────╯
"""

HELP_TEXT = """
Use "ajuda" para ver a lista completa de comandos disponíveis.

Atalhos úteis:
  abre o VS Code
  lista processos
  foco por 25 min
  briefing
  relatório de produtividade
"""


def get_command(prompt: str = "paçoca > ") -> str:
    """Lê um comando da entrada padrão."""
    return input(prompt).strip()


def print_banner():
    print(BANNER)


def print_help():
    print(HELP_TEXT)


def print_response(text: str):
    print(f"\nPaçoca\n{text}\n")


def print_status(mode: str, profile: str, overlay: bool, tts: bool):
    overlay_label = "on" if overlay else "off"
    tts_label = "on" if tts else "off"
    print(f"Modo: {mode} · Perfil: {profile} · Overlay: {overlay_label} · TTS: {tts_label}\n")


def is_exit(command: str) -> bool:
    return command.lower() in ("sair", "exit", "quit", "q")


def is_help(command: str) -> bool:
    return command.lower() in ("ajuda", "help", "?")
