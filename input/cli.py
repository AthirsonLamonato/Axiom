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
┌─────────────────────────────────────────┐
│  Axiom — Modo texto                     │
│  Digite um comando ou 'ajuda' para      │
│  ver os exemplos disponíveis.           │
│  'sair' para encerrar.                  │
└─────────────────────────────────────────┘
"""

HELP_TEXT = """
Exemplos de comandos:
  abre o VS Code
  fecha o Chrome
  volume 70
  começa a transcrever a reunião
  resume o que foi falado
  pesquisa como funciona decorators em Python
  commit "feat: adiciona módulo de backup"
  modo trabalho
  fim do dia
  relatório de produtividade
"""


def get_command(prompt: str = "  > ") -> str:
    """Lê um comando da entrada padrão."""
    return input(prompt).strip()


def print_banner():
    print(BANNER)


def print_help():
    print(HELP_TEXT)


def print_response(text: str):
    print(f"\n  Axiom › {text}\n")


def is_exit(command: str) -> bool:
    return command.lower() in ("sair", "exit", "quit", "q")


def is_help(command: str) -> bool:
    return command.lower() in ("ajuda", "help", "?")
