"""
Axiom — Assistente pessoal inteligente
Ponto de entrada principal
"""

import argparse
import sys
import signal

# Garante UTF-8 no terminal Windows para o banner e mensagens
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

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
    parser.add_argument(
        "--edit-routines",
        action="store_true",
        help="Abre editor interativo de rotinas",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Inicia o dashboard web em http://127.0.0.1:7755",
    )
    return parser.parse_args()


def shutdown(sig, frame):
    print("\n\n[Axiom] Encerrando... até logo.")
    sys.exit(0)


def _edit_routines(config):
    """Editor interativo de rotinas via CLI."""
    import yaml

    routines = config.get("routines", {})
    print("\n=== Editor de Rotinas ===")
    print("Rotinas existentes:", ", ".join(routines.keys()) or "nenhuma")
    print("\nOpções: [l]istar  [a]dicionar  [r]emover  [s]air\n")

    while True:
        cmd = input("rotinas> ").strip().lower()
        if cmd in ("s", "sair", "exit", "q"):
            break
        elif cmd in ("l", "listar"):
            for name, body in routines.items():
                print(f"\n  [{name}] {body.get('name', '')}")
                for step in body.get("steps", []):
                    print(f"    - {step.get('action')} {step.get('target', '')} {step.get('message', '')}")
        elif cmd in ("a", "adicionar"):
            name = input("  Nome da rotina (sem espaços): ").strip()
            label = input("  Descrição: ").strip()
            steps = []
            print("  Adicione etapas (vazio para terminar). Ações: open_app, notify, set_volume, focus, daily_report")
            while True:
                action = input("    ação: ").strip()
                if not action:
                    break
                target = input("    target/minutos (opcional): ").strip()
                message = input("    mensagem (opcional): ").strip()
                step = {"action": action}
                if target:
                    step["target"] = target
                if message:
                    step["message"] = message
                steps.append(step)
            routines[name] = {"name": label, "steps": steps}
            config.set("routines", routines)
            # Persiste no YAML
            try:
                cfg_path = config._path
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                data["routines"] = routines
                with open(cfg_path, "w", encoding="utf-8") as f:
                    yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                print(f"  Rotina '{name}' salva.")
            except Exception as e:
                print(f"  Erro ao salvar: {e}")
        elif cmd in ("r", "remover"):
            name = input("  Nome da rotina a remover: ").strip()
            if name in routines:
                del routines[name]
                config.set("routines", routines)
                print(f"  Rotina '{name}' removida.")
            else:
                print(f"  Rotina '{name}' não encontrada.")
        else:
            print("  Comando inválido. Use: l, a, r, s")


def main():
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    args = parse_args()

    config = Config()

    # Logging deve ser o primeiro subsistema a iniciar
    setup_logging(config)

    if args.edit_routines:
        _edit_routines(config)
        return

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

  Assistente pessoal inteligente — v0.5.0
  Modo: {mode} | Perfil: {profile}
  Pressione Ctrl+C para encerrar.
""".format(
        mode=args.mode,
        profile=config.get("profile.active", "work"),
    ))

    orchestrator = Orchestrator(config)

    if args.web:
        from modules import web_server
        print(web_server.start())

    notify("Axiom iniciado", f"Modo {args.mode} ativo.")

    if args.mode == "text":
        orchestrator.run_text_loop()
    else:
        orchestrator.run_voice_loop()


if __name__ == "__main__":
    main()
