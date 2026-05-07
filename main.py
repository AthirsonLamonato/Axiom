"""
Axiom — Assistente pessoal inteligente
Ponto de entrada principal
"""

import argparse
import sys
import signal

from core.orchestrator import Orchestrator
from core.config import Config
from core.logger import setup_logging
from output.notifier import notify


def parse_args():
    parser = argparse.ArgumentParser(description="Axiom — Assistente pessoal inteligente")
    parser.add_argument(
        "--mode",
        choices=["voice", "text"],
        default="voice",
        help="Modo de entrada: voice (padrão) ou text",
    )
    parser.add_argument(
        "--profile",
        choices=["work", "casual"],
        default=None,
        help="Perfil inicial: work ou casual",
    )
    parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Desativa resposta por voz",
    )
    parser.add_argument(
        "--no-overlay",
        action="store_true",
        help="Desativa overlay visual",
    )
    return parser.parse_args()


def shutdown(sig, frame):
    print("\n\n[Axiom] Encerrando... até logo.")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    args = parse_args()

    config = Config()

    # Logging deve ser o primeiro subsistema a iniciar
    setup_logging(config)

    # Sobrescreve config com flags da linha de comando
    if args.no_tts:
        config.set("tts.enabled", False)
    if args.no_overlay:
        config.set("overlay.enabled", False)
    if args.profile:
        config.set("profile.active", args.profile)

    # Inicializa banco de dados SQLite
    from storage import db
    db.init()

    # Rastreamento de produtividade em background
    from modules import productivity
    productivity.start_tracking()

    # Overlay visual (se habilitado)
    if config.get("overlay.enabled", True):
        from output import overlay
        overlay.init(config)

    print("""
 █████╗ ██╗  ██╗██╗ ██████╗ ███╗   ███╗
██╔══██╗╚██╗██╔╝██║██╔═══██╗████╗ ████║
███████║ ╚███╔╝ ██║██║   ██║██╔████╔██║
██╔══██║ ██╔██╗ ██║██║   ██║██║╚██╔╝██║
██║  ██║██╔╝ ██╗██║╚██████╔╝██║ ╚═╝ ██║
╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝     ╚═╝

  Assistente pessoal inteligente — v0.1.0-alpha
  Modo: {mode} | Perfil: {profile}
  Pressione Ctrl+C para encerrar.
""".format(
        mode=args.mode,
        profile=config.get("profile.active", "work"),
    ))

    orchestrator = Orchestrator(config)

    notify("Axiom iniciado", f"Modo {args.mode} ativo.")

    if args.mode == "text":
        orchestrator.run_text_loop()
    else:
        orchestrator.run_voice_loop()


if __name__ == "__main__":
    main()
