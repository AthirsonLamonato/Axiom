"""
core/orchestrator.py — Roteador central de comandos
Recebe texto (voz ou CLI), identifica a intenção e despacha ao módulo correto.
"""

import re
import logging
from typing import Optional, Callable

from core.config import Config
from core.profiles import ProfileManager
from output.tts import TTS
from output.notifier import notify


logger = logging.getLogger(__name__)


# ── Importações lazy (evita falha se dependência ausente) ──────────────
def _import_module(name: str):
    try:
        import importlib
        return importlib.import_module(name)
    except ImportError as e:
        logger.warning(f"Módulo {name} não disponível: {e}")
        return None


# ── Tabela de rotas ────────────────────────────────────────────────────
# (padrão regex, handler, requer_confirmação)
ROUTES: list[tuple[str, str, bool]] = [
    # Dev tools específicos (antes das rotas genéricas de "abre/fecha")
    (r"abre\s+o\s+(vs\s?code|vscode|editor)", "modules.dev_tools:open_vscode",  False),
    (r"abre\s+o\s+arquivo\s+(.+)",        "modules.dev_tools:open_file",        False),
    (r"abre\s+o\s+file\s+(.+)",           "modules.dev_tools:open_file",        False),
    (r"vai\s+para\s+a?\s*linha\s+(\d+)",  "modules.dev_tools:goto_line",        False),
    (r"novo\s+terminal",                  "modules.dev_tools:open_terminal",    False),
    (r"cria\s+(arquivo|file)\s+(.+)",     "modules.dev_tools:create_file",      False),
    (r"explica\s+o\s+(arquivo|file)\s+(.+)", "modules.dev_tools:explain_file",  False),
    # Git
    (r"commit\s+[\"']?(.+)[\"']?",        "modules.dev_tools:git_commit",       True),
    (r"git\s+push",                       "modules.dev_tools:git_push",         True),
    (r"git\s+pull",                       "modules.dev_tools:git_pull",         False),
    (r"(o\s+que\s+mudou|git\s+status)",   "modules.dev_tools:git_status",        False),
    (r"git\s+log|últimos?\s+commits?|mostra.{0,20}commits?|ultimos\s+commits?",
                                          "modules.dev_tools:git_log",          False),
    (r"cria\s+branch\s+(.+)",             "modules.dev_tools:git_create_branch", False),
    (r"(branch|ramo)\s+atual",            "modules.dev_tools:git_branch_current",False),
    (r"(roda|executa)\s+(os\s+)?testes",  "modules.dev_tools:run_tests",        False),

    # Overlay específico (antes de "abre/fecha" genérico)
    (r"abre\s+o\s+overlay",               "output.overlay:show",                False),
    (r"fecha\s+o\s+overlay",              "output.overlay:hide",                False),

    # Sistema (rotas genéricas por último)
    (r"volume\s+(\d+)",                   "modules.system_control:set_volume",  False),
    (r"(aumenta|sobe)\s+o\s+brilho",      "modules.system_control:brightness_up",   False),
    (r"(diminui|baixa)\s+o\s+brilho",     "modules.system_control:brightness_down", False),
    (r"(muta|silencia)\s+o?\s*(som|áudio)","modules.system_control:mute",       False),
    (r"(lista|mostra)\s+processos",       "modules.system_control:list_processes", False),
    (r"abre?\s+(.+)",                     "modules.system_control:open_app",    False),
    (r"fecha?\s+(.+)",                    "modules.system_control:close_app",   True),

    # Transcrição
    (r"(começa|inicia|start)\s+transcri(.+)?",   "modules.transcription:start",    False),
    (r"(para|stop)\s+transcri",                  "modules.transcription:stop",     False),
    (r"mostra\s+(o\s+que\s+foi\s+falado|a\s+transcrição)", "modules.transcription:show_last", False),

    # Resumo / IA
    (r"(resume|resumo)\s+(o\s+que\s+foi\s+falado|a\s+reunião|a\s+transcrição)", "modules.summarizer:summarize_last", False),
    (r"resumo\s+detalhado",               "modules.summarizer:summarize_detailed", False),
    (r"(explica?|o\s+que\s+é)\s+(.+)",   "modules.summarizer:explain",         False),

    # Pesquisa
    (r"(pesquisa|busca\s+na\s+internet)\s+(.+)", "modules.search:route",       False),
    (r"busca\s+por\s+ia\s+(.+)",          "modules.search:search_ai",           False),

    # Rotinas
    (r"modo\s+trabalho",                  "modules.routines:work_mode",         False),
    (r"modo\s+foco",                      "modules.routines:focus_mode",        False),
    (r"fim\s+do\s+dia",                   "modules.routines:end_of_day",        False),
    (r"executa\s+rotina\s+(.+)",          "modules.routines:run",               False),

    # Produtividade
    (r"(mostra|exibe)\s+(o\s+)?tempo\s+(de\s+uso|no\s+pc)", "modules.productivity:show_usage", False),
    (r"relatório\s+de\s+produtividade",   "modules.productivity:report",        False),
    (r"relatório\s+diário",               "modules.productivity:daily_report",  False),

    # Pomodoro / foco
    (r"foco\s+por\s+(\d+)\s*min",         "modules.productivity:focus_start",   False),
    (r"foco\s+por\s+(\d+)\s*h",           "modules.productivity:focus_start",   False),
    (r"(cancela|para)\s+o\s+timer",       "modules.productivity:focus_stop",    False),
    (r"(quanto\s+tempo|status)\s+(do\s+)?timer", "modules.productivity:focus_status", False),

    # Meta
    (r"ajuda|help|\?",                    "core.orchestrator:list_commands",    False),
]


def list_commands(*_) -> str:
    """Lista todos os comandos disponíveis dinamicamente a partir de ROUTES."""
    seen_handlers = {}
    for pattern, handler, _ in ROUTES:
        if handler not in seen_handlers:
            seen_handlers[handler] = pattern

    lines = ["Comandos disponíveis:\n"]
    current_group = ""
    for handler, pattern in seen_handlers.items():
        group = handler.split(".")[0] if "." in handler else handler
        if group != current_group:
            current_group = group
            group_label = {
                "modules": handler.split(":")[0].replace("modules.", ""),
                "output": "overlay",
                "core": "sistema",
            }.get(handler.split(".")[0], group)
            lines.append(f"\n  [{group_label.upper()}]")
        # Simplifica o padrão para leitura humana
        readable = (
            pattern.replace(r"\s+", " ")
                   .replace(r"\s*", "")
                   .replace("?", "")
                   .replace("(", "").replace(")", "")
                   .replace("|", "/")
                   .strip()
        )
        lines.append(f"    {readable}")

    return "\n".join(lines)


class Orchestrator:
    def __init__(self, config: Config):
        self.config = config
        self.tts = TTS(config)
        self.profiles = ProfileManager(config)
        self._transcription_module = None  # instância persistente para transcrição

    # ── Loops principais ───────────────────────────────────────────────

    def run_text_loop(self):
        """Loop interativo via terminal."""
        overlay = _import_module("output.overlay")
        print("[Axiom] Modo texto ativo. Digite seu comando (ou 'sair' para encerrar):\n")
        while True:
            try:
                if overlay:
                    overlay.set_state("listening")
                command = input("  > ").strip()
                if not command:
                    continue
                if command.lower() in ("sair", "exit", "quit"):
                    print("[Axiom] Encerrando.")
                    break
                if overlay:
                    overlay.set_state("processing")
                response = self.dispatch(command)
                if response:
                    print(f"\n  Axiom: {response}\n")
                    if overlay:
                        overlay.show_message(response)
                        overlay.set_state("speaking")
                    self.tts.speak(response)
                if overlay:
                    overlay.set_state("idle")
            except (EOFError, KeyboardInterrupt):
                break

    def run_voice_loop(self):
        """Loop de escuta contínua com wake word ou push-to-talk."""
        overlay = _import_module("output.overlay")
        stt_module = _import_module("input.stt")
        if not stt_module:
            print("[Axiom] Módulo STT não disponível. Usando modo texto.")
            self.run_text_loop()
            return

        try:
            voice = stt_module.VoiceInput(self.config)
        except Exception as e:
            logger.error(f"Falha ao inicializar STT: {e}", exc_info=True)
            print(f"[Axiom] Erro ao inicializar STT: {e}\n[Axiom] Usando modo texto.")
            self.run_text_loop()
            return

        mode = voice._mode
        if mode == "push_to_talk":
            print("[Axiom] Modo push-to-talk ativo. Use ctrl+shift+space para falar.\n")
        else:
            print(f"[Axiom] Aguardando wake word '{self.config.get('wake_word.keyword')}'...\n")
        self.tts.speak("Axiom online.")

        while True:
            if overlay:
                overlay.set_state("listening")
            command = voice.listen_for_command()
            if command:
                logger.info(f"Comando recebido: {command}")
                if overlay:
                    overlay.set_state("processing")
                response = self.dispatch(command)
                if response:
                    if overlay:
                        overlay.show_message(response)
                        overlay.set_state("speaking")
                    self.tts.speak(response)
                if overlay:
                    overlay.set_state("idle")

    # ── Despachante central ────────────────────────────────────────────

    def dispatch(self, command: str) -> Optional[str]:
        command_lower = command.lower().strip()
        logger.debug(f"Despachando: {command_lower}")

        for pattern, handler_path, needs_confirm in ROUTES:
            match = re.search(pattern, command_lower)
            if match:
                # Verificar se precisa de confirmação
                if needs_confirm and self.config.get("security.confirm_critical"):
                    if not self._confirm(command):
                        return "Ação cancelada."

                # Resolver e chamar o handler
                return self._call_handler(handler_path, match)

        # Nenhuma rota bateu → fallback para IA
        return self._fallback_ai(command)

    # ── Helpers internos ───────────────────────────────────────────────

    def _call_handler(self, handler_path: str, match: re.Match) -> Optional[str]:
        """Carrega o módulo e chama a função dinamicamente."""
        try:
            module_path, func_name = handler_path.rsplit(":", 1)
            module = _import_module(module_path)
            if module is None:
                return f"[Axiom] Módulo '{module_path}' não está disponível."

            func: Callable = getattr(module, func_name, None)
            if func is None:
                return f"[Axiom] Função '{func_name}' não encontrada em '{module_path}'."

            # Passa o primeiro grupo capturado, se houver
            args = [g for g in match.groups() if g is not None]
            if args:
                return func(*args)
            return func()

        except Exception as e:
            logger.error(f"Erro ao executar '{handler_path}': {e}", exc_info=True)
            return f"Erro ao executar o comando: {e}"

    def _fallback_ai(self, command: str) -> str:
        """Repassa ao LLM quando nenhuma rota bate."""
        summarizer = _import_module("modules.summarizer")
        if summarizer:
            return summarizer.ask_ai(command)
        return "Não entendi o comando. Tente novamente."

    def _confirm(self, action: str) -> bool:
        """Solicita confirmação para ações críticas."""
        print(f"\n  [!] Ação crítica: '{action}'")
        resp = input("      Confirmar? (s/N): ").strip().lower()
        return resp == "s"
