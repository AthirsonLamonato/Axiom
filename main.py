"""
Paçoca — Assistente pessoal inteligente
Ponto de entrada principal
"""

import argparse
import os
import shutil
import sys
import signal
from pathlib import Path

# ── Bootstrap para execução como exe PyInstaller ──────────────────────
if getattr(sys, "frozen", False):
    _EXE_DIR = Path(sys.executable).parent          # dist/Pacoca/
    _MEIPASS  = Path(getattr(sys, "_MEIPASS", _EXE_DIR))  # dist/Pacoca/_internal/

    # 1. CWD = diretório do exe → logs/, data/ ficam acessíveis ao usuário
    os.chdir(_EXE_DIR)

    # 2. Config.yaml: usa o da raiz (editável pelo wizard/usuário);
    #    se não existir, copia do template bundled
    _user_cfg = _EXE_DIR / "core" / "config.yaml"
    if not _user_cfg.exists():
        _user_cfg.parent.mkdir(parents=True, exist_ok=True)
        _bundled_cfg = _MEIPASS / "core" / "config.yaml"
        if _bundled_cfg.exists():
            shutil.copy2(_bundled_cfg, _user_cfg)

    # 3. Sinaliza o caminho do config para core/config.py
    os.environ["PACOCA_CONFIG_PATH"] = str(_user_cfg)

    # 4. Plugins: copia para local editável se ainda não existir
    _user_plugins = _EXE_DIR / "plugins"
    if not _user_plugins.exists():
        _bundled_plugins = _MEIPASS / "plugins"
        if _bundled_plugins.exists():
            shutil.copytree(_bundled_plugins, _user_plugins)

# Garante UTF-8 no terminal Windows para o banner e mensagens
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

def _load_dotenv():
    """Carrega variáveis do .env sem depender de python-dotenv."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

_load_dotenv()

from core.orchestrator import Orchestrator
from core.config import Config
from core.logger import setup_logging
from output.notifier import notify


def parse_args():
    parser = argparse.ArgumentParser(description="Paçoca — Assistente pessoal inteligente")
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
    parser.add_argument(
        "--list-audio-devices",
        action="store_true",
        help="Lista os dispositivos de entrada e saída disponíveis e encerra",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Diagnostica IA local, Ollama, modelos instalados e segurança",
    )
    return parser.parse_args()


def _doctor(config):
    """Exibe diagnóstico local sem iniciar microfone, overlay ou agendadores."""
    import json
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen
    from core.ai_catalog import recommended_config, system_ram_gb

    ram = system_ram_gb()
    recommended = recommended_config(ram)
    provider = config.get("ai.provider", "ollama")
    model = config.get("ai.model", recommended["model"])
    ollama_url = str(config.get("ai.ollama_url", "http://localhost:11434")).rstrip("/")
    installed = []
    status = "indisponível"
    try:
        response = urlopen(Request(f"{ollama_url}/api/tags"), timeout=2)
        payload = json.loads(response.read().decode("utf-8"))
        installed = [item.get("name", "") for item in payload.get("models", []) if item.get("name")]
        status = "disponível"
    except (URLError, HTTPError, TimeoutError, ValueError, OSError):
        pass

    print("Paçoca — diagnóstico local")
    print(f"  RAM detectada: {ram or 'desconhecida'} GB")
    print(f"  Provedor configurado: {provider}")
    print(f"  Modelo configurado: {model}")
    print(f"  Modelo recomendado: {recommended['model']}")
    print(f"  Ollama: {status} ({ollama_url})")
    print(f"  Modelo instalado: {'sim' if model in installed else 'não'}")
    print(f"  Embeddings: {config.get('ai.embeddings_provider', 'ollama')} / {config.get('ai.embeddings_ollama_model', 'nomic-embed-text')}")
    print(f"  Aprovação de planos: {'ativada' if config.get('agent.require_plan_approval', True) else 'desativada'}")
    print(f"  Fallback remoto: {'ativado' if config.get('ai.cloud_first', False) else 'desativado'}")
    if status != "disponível":
        print(f"  Ação: inicie o Ollama e execute `ollama pull {model}`.")
    elif model not in installed:
        print(f"  Ação: execute `ollama pull {model}`.")
    return 0


def _ensure_directories():
    """Cria diretórios de dados necessários caso não existam."""
    for d in ["data", "data/transcriptions", "data/backups", "data/screenshots", "logs", "plugins"]:
        Path(d).mkdir(parents=True, exist_ok=True)


def shutdown(sig, frame):
    print("\n\n[Paçoca] Encerrando... até logo.", flush=True)
    # Com a janela de desktop aberta, a thread principal fica bloqueada
    # dentro do event loop do Qt (C++) — sys.exit() levantado ali dentro
    # (quando o sinal é finalmente verificado pelo interpretador, durante o
    # callback periódico do _poll_timer) é engolido pelo PyQt, e o processo
    # nunca chegaria a pedir a saída. Pede pela mesma fila thread-safe da
    # janela em vez de depender de exceção atravessando o C++ — o
    # encerramento de fato do processo é forçado em main() via os._exit()
    # depois que run_main_loop() retornar (ver comentário lá).
    try:
        from output import overlay
        if overlay._instance:
            overlay.request_quit()
            return
    except Exception:
        pass
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
                try:
                    cfg_path = config._path
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                    data["routines"] = routines
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
                    print(f"  Rotina '{name}' removida.")
                except Exception as e:
                    print(f"  Erro ao salvar remoção: {e}")
            else:
                print(f"  Rotina '{name}' não encontrada.")
        else:
            print("  Comando inválido. Use: l, a, r, s")


def _check_external_data_consent(config) -> None:
    """
    Mostra aviso quando o Paçoca está configurado para enviar dados para serviços externos
    (Groq API). O aviso é mostrado apenas uma vez por sessão, não bloqueia o boot.
    """
    try:
        from core.providers import _resolve_key
        groq_key = _resolve_key("ai.groq_api_key", "GROQ_API_KEY", config)
    except Exception:
        import os
        groq_key = os.environ.get("GROQ_API_KEY", "") or config.get("ai.groq_api_key", "")
    provider  = config.get("ai.provider", "ollama")
    if groq_key and provider in ("groq", "auto"):
        print(
            "\n  [!] Aviso de privacidade: comandos e contexto de conversa serão enviados\n"
            "      para a API do Groq (https://groq.com) para processamento.\n"
            "      Para usar apenas IA local, defina 'ai.provider: ollama' em config.yaml\n"
            "      ou remova a GROQ_API_KEY do ambiente.\n"
        )


def _schedule_data_retention(config) -> None:
    """Agenda limpeza automática de dados antigos em background."""
    retention_days = config.get("privacy.retention_days", 30)
    if not retention_days:
        return
    import threading

    def _cleanup():
        try:
            from storage.db import cleanup_old_data
            result = cleanup_old_data(days=retention_days)
            import logging
            logging.getLogger(__name__).info(result)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Limpeza de dados falhou: %s", e)

    t = threading.Thread(target=_cleanup, daemon=True, name="data-retention")
    t.start()


def main():
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    args = parse_args()

    _ensure_directories()

    config = Config()

    if args.doctor:
        return _doctor(config)

    if args.list_audio_devices:
        from core.audio_devices import list_devices
        try:
            for device in list_devices():
                directions = "/".join(
                    direction for direction, enabled in (
                        ("entrada", device["input"]), ("saída", device["output"])
                    ) if enabled
                )
                print(f"{device['index']}: {device['name']} [{directions}]")
        except Exception as exc:
            print(f"Não foi possível listar dispositivos de áudio: {exc}")
        return

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

    # Inicializa banco de dados SQLite e memória de longo prazo
    from storage import db
    db.init()
    try:
        from storage import memory as _mem
        _mem.init()
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("Memória não inicializada: %s", _e)

    try:
        from storage import knowledge_base as _kb
        _kb.init()
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning("Knowledge base não inicializada: %s", _e)

    # Rastreamento de produtividade em background
    from modules import productivity
    productivity.start_tracking()

    # Agendadores autônomos: rotinas com horário marcado, briefing diário,
    # insights de aprendizado periódicos e detecção de hábitos
    from modules import routines as _routines_mod
    from modules import briefing as _briefing_mod
    from modules import learner as _learner_mod
    from modules import habits as _habits_mod
    _routines_mod.start_scheduler()
    _briefing_mod.start_scheduler()
    _learner_mod.start_scheduler()
    _habits_mod.start_scheduler()

    # Overlay visual (se habilitado)
    _overlay_enabled = config.get("overlay.enabled", True)
    if _overlay_enabled:
        from output import overlay
        overlay.init(config)

    print(
        "\nPaçoca v0.6.0 — Assistente pessoal inteligente\n"
        f"Modo: {args.mode} | Perfil: {config.get('profile.active', 'work')} | Ctrl+C encerra\n"
    )

    # Avisa quando dados serão enviados para serviços externos
    _check_external_data_consent(config)

    # Limpeza automática de dados antigos (executa em background, não bloqueia)
    _schedule_data_retention(config)

    orchestrator = Orchestrator(config)

    if _overlay_enabled:
        from output import overlay as _overlay_mod
        _overlay_mod.set_orchestrator(orchestrator)

    if args.web:
        from modules import web_server
        print(web_server.start())

    notify("Paçoca iniciada", f"Modo {args.mode} ativo. Perfil: {config.get('profile.active', 'work')}")

    import threading

    def _run_orchestrator():
        if args.mode == "text":
            orchestrator.run_text_loop()
        else:
            orchestrator.run_voice_loop()
        # Loop de texto/voz terminou (ex: usuário digitou "sair") — sem isso
        # a janela de desktop manteria o processo vivo indefinidamente.
        if _overlay_enabled:
            from output import overlay as _overlay_mod
            _overlay_mod.request_quit()

    if _overlay_enabled:
        from output import overlay as _overlay_mod
        if _overlay_mod._instance:
            t = threading.Thread(target=_run_orchestrator, daemon=True)
            t.start()
            _overlay_mod.run_main_loop()  # Qt event loop na main thread
            # A finalização normal do interpretador (atexit, GC, destruidor
            # do QApplication) trava depois daqui neste setup Qt/Wayland —
            # confirmado: só restam threads daemon nesse ponto (nada
            # pendente de fato), então pular o teardown normal é seguro.
            os._exit(0)
        else:
            _run_orchestrator()
    else:
        _run_orchestrator()


if __name__ == "__main__":
    main()
