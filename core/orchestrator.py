"""
core/orchestrator.py — Roteador central de comandos
Recebe texto (voz ou CLI), identifica a intenção e despacha ao módulo correto.
"""

import re
import logging
from typing import Optional, Callable

from core.config import Config
from core.profiles import init_manager
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

    # Dashboard web (antes de "abre/fecha" genérico)
    (r"(abre|inicia)\s+o\s+dashboard",              "modules.web_server:start",  False),
    (r"(inicia|sobe)\s+(a\s+)?interface\s+web",     "modules.web_server:start",  False),
    (r"(para|fecha)\s+o\s+(servidor\s+web|dashboard)", "modules.web_server:stop", False),

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
    (r"(identifica|diariz[ae])\s+(os\s+)?falantes?",       "modules.transcription:diarize",   False),

    # Obsidian / exportação de notas
    (r"exporta\s+(a\s+)?transcri[çc][aã]o\s+(para\s+o?\s*)?obsidian",
                                                          "modules.obsidian:export_transcription", False),
    (r"exporta\s+(o\s+)?sum[aá]rio\s+(para\s+o?\s*)?obsidian",
                                                          "modules.obsidian:export_summary",       False),
    (r"(cria|atualiza)\s+(a\s+)?nota\s+di[aá]ria",        "modules.obsidian:daily_note",           False),
    (r"exporta\s+(as\s+)?notas\s+(para\s+o?\s*)?obsidian","modules.obsidian:export_notes_plugin",  False),

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

    # Detector de reunião automático
    (r"(ativa|inicia|liga)\s+(o\s+)?detector\s+de\s+reuni[aã]o",
                                                          "modules.meeting_detector:start_monitoring", False),
    (r"(desativa|para|desliga)\s+(o\s+)?detector\s+de\s+reuni[aã]o",
                                                          "modules.meeting_detector:stop_monitoring",  False),
    (r"(status|estado)\s+do\s+detector(\s+de\s+reuni[aã]o)?",
                                                          "modules.meeting_detector:status",           False),

    # Perfis dinâmicos por voz
    (r"(muda|ativa)\s+(para\s+)?perfil\s+(.+)",  "core.profiles:switch_profile",   False),
    (r"perfil\s+(work|casual|focus|foco|meeting|reunião|reuniao|noturno|noite|trabalho)",
                                                  "core.profiles:switch_profile",   False),
    (r"(qual|mostra)\s+(o\s+)?perfil(\s+atual)?", "core.profiles:current_profile",  False),
    (r"(lista|quais)\s+(os\s+)?perfis",           "core.profiles:list_profiles",    False),

    # Google Calendar
    (r"(o\s+que\s+tenho|agenda)\s+(hoje|amanhã|amanha)",
                                                  "modules.calendar_integration:get_today_events", False),
    (r"(próximo|proximo)\s+(evento|compromisso|reunião|reuniao)",
                                                  "modules.calendar_integration:get_next_event",   False),
    (r"(adiciona|marca|cria)\s+(no\s+calendário|no\s+calendario|evento|reunião|reuniao)\s+(.+)",
                                                  "modules.calendar_integration:add_event",        False),
    (r"autoriza\s+(calendário|calendario|google\s+calendar)",
                                                  "modules.calendar_integration:auth_calendar",    False),

    # Calibração de microfone + idioma STT
    (r"(calibra|recalibra)\s+(o\s+)?(microfone|mic|ruído|ruido)",
                                                  "input.stt:calibrar_microfone",                  False),
    (r"(muda|troca|altera)\s+(para\s+)?(inglês|ingles|espanhol|francês|frances|alemão|alemao|português|portugues|italiano|japonês|japones|english|spanish|french|german|italian|japanese)\b",
                                                  "input.stt:switch_language",                     False),
    (r"idioma\s+atual",                           "input.stt:current_language",                    False),

    # Lembretes
    (r"me\s+lembra?\s+.+",                       "modules.reminders:add",                         False),
    (r"(lista|mostra)\s+(os\s+)?lembretes",       "modules.reminders:list_reminders",              False),
    (r"cancela\s+(o\s+)?lembrete[s]?(\s+\d+)?",  "modules.reminders:cancel",                      False),

    # Clipboard
    (r"copia\s+o\s+(último|ultimo)\s+resultado",  "modules.clipboard_tools:copy_last",             False),
    (r"copia\s+(.+)\s+para\s+o\s+clipboard",      "modules.clipboard_tools:copy_text",             False),
    (r"(lê|le|mostra)\s+(a\s+)?área\s+de\s+transfer",
                                                  "modules.clipboard_tools:read_clipboard",        False),
    (r"(lê|le|mostra)\s+(o\s+)?clipboard",        "modules.clipboard_tools:read_clipboard",        False),
    (r"limpa\s+(o\s+)?clipboard",                 "modules.clipboard_tools:clear_clipboard",       False),

    # OCR / leitura de tela
    (r"(lê|le|leia)\s+(o\s+)?texto\s+na\s+tela", "modules.screen_reader:read_screen",             False),
    (r"(lê|le|leia)\s+(a\s+)?tela",               "modules.screen_reader:read_screen",             False),
    (r"(lê|le|leia)\s+(a\s+)?região\s+(central)?","modules.screen_reader:read_region",             False),
    (r"salva\s+(um\s+)?screenshot",               "modules.screen_reader:save_screenshot",         False),

    # Contexto de conversa
    (r"(limpa|apaga)\s+(o\s+)?contexto",          "storage.context:clear",                         False),
    (r"(mostra|exibe)\s+(o\s+)?contexto",         "storage.context:show",                          False),

    # Sumários de sessão e reunião
    (r"(resume|resumo)\s+(a\s+)?reunião",         "modules.summarizer:summarize_meeting",          False),
    (r"(resume|resumo)\s+(a\s+)?sessão",          "modules.summarizer:summarize_session",          False),

    # Plugins
    (r"(lista|mostra)\s+(os\s+)?plugins(\s+carregados)?",
                                                  "core.plugin_loader:list_loaded",                False),
    (r"(recarrega|reload)\s+(os\s+)?plugins",     "core.plugin_loader:reload_all",                 False),

    # Meta
    (r"ajuda|help|\?",                    "core.orchestrator:list_commands",    False),
]

_CHAIN_SEP = re.compile(
    r'\s+(?:e depois|depois disso|em seguida|então|entao)\s+', re.IGNORECASE
)
_CHAIN_AND = re.compile(r'\s+e\s+', re.IGNORECASE)


def list_commands(*_) -> str:
    """Lista todos os comandos disponíveis (built-in + plugins)."""
    try:
        import importlib
        from core.plugin_loader import _registry
        plugin_routes = []
        for info in _registry.values():
            mod = importlib.import_module(info["module"])
            plugin_routes.extend(getattr(mod, "ROUTES", []))
    except Exception:
        plugin_routes = []

    all_routes = list(ROUTES) + plugin_routes
    seen_handlers = {}
    for pattern, handler, _ in all_routes:
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
        self.profiles = init_manager(config)
        self._transcription_module = None  # instância persistente para transcrição
        self._plugin_routes: list = []
        self._all_routes: list = list(ROUTES)
        self._last_profile: str = ""
        self._load_plugins()
        try:
            from modules import web_server
            web_server.set_orc(self)
        except Exception:
            pass

    def _load_plugins(self) -> None:
        if not self.config.get("plugins.enabled", True):
            return
        from core import plugin_loader
        plugins_dir = self.config.get("plugins.directory", "plugins")
        plugin_loader.set_orchestrator(self)
        self._plugin_routes = plugin_loader.load_all(plugins_dir)
        self._all_routes = list(ROUTES) + self._plugin_routes

    def _reload_plugins(self) -> None:
        self._load_plugins()
        logger.info("Plugins recarregados: %d rota(s) de plugins", len(self._plugin_routes))

    # ── Loops principais ───────────────────────────────────────────────

    def run_text_loop(self):
        """Loop interativo via terminal."""
        overlay = _import_module("output.overlay")
        print("[Paçoca] Modo texto ativo. Digite seu comando (ou 'sair' para encerrar).")
        print("         Dica: 'ajuda' lista todos os comandos disponíveis.\n")
        while True:
            try:
                if overlay:
                    overlay.set_state("listening")
                command = input("  > ").strip()
                if not command:
                    continue
                if command.lower() in ("sair", "exit", "quit"):
                    print("[Paçoca] Encerrando.")
                    break
                if overlay:
                    overlay.set_state("processing")
                response = self.dispatch_chain(command)
                if response:
                    print(f"\n  Paçoca: {response}\n")
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
            print("[Paçoca] Módulo STT não disponível. Usando modo texto.")
            print("         Instale as dependências de voz: pip install -r requirements-voice.txt\n")
            self.run_text_loop()
            return

        try:
            voice = stt_module.init_voice(self.config)
        except Exception as e:
            logger.error(f"Falha ao inicializar STT: {e}", exc_info=True)
            print(f"[Paçoca] Erro ao inicializar STT: {e}")
            print("[Paçoca] Usando modo texto como fallback.\n")
            self.run_text_loop()
            return

        mode = voice._mode
        if mode == "push_to_talk":
            print("[Paçoca] Modo push-to-talk ativo. Use Ctrl+Shift+Espaço para falar.\n")
        else:
            keyword = self.config.get("wake_word.keyword", "hey jarvis")
            print(f"[Paçoca] Aguardando wake word '{keyword}'...\n")
        self.tts.speak("Paçoca online.")

        while True:
            if overlay:
                overlay.set_state("listening")
            command = voice.listen_for_command()
            if command:
                logger.info(f"Comando recebido: {command}")
                if overlay:
                    overlay.set_state("processing")
                response = self.dispatch_chain(command)
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
        logger.debug("Despachando: %s", command_lower)

        response: Optional[str] = None

        for pattern, handler_path, needs_confirm in self._all_routes:
            match = re.search(pattern, command_lower)
            if match:
                if needs_confirm and self.config.get("security.confirm_critical"):
                    if not self._confirm(command):
                        return "Ação cancelada."
                response = self._call_handler(handler_path, match)
                break

        if response is None:
            response = self._fallback_ai(command)

        # Registra no contexto e expõe para clipboard
        if response:
            from storage.context import add as _ctx_add
            _ctx_add(command, response)
            try:
                from modules.clipboard_tools import set_last_response
                set_last_response(response)
            except Exception:
                pass

        self._sync_tts_profile()
        return response

    # ── Helpers internos ───────────────────────────────────────────────

    def _call_handler(self, handler_path: str, match: re.Match) -> Optional[str]:
        """Carrega o módulo e chama a função dinamicamente."""
        try:
            module_path, func_name = handler_path.rsplit(":", 1)
            module = _import_module(module_path)
            if module is None:
                return f"Módulo '{module_path}' não está disponível (dependência ausente?)."

            func: Callable = getattr(module, func_name, None)
            if func is None:
                return f"Função '{func_name}' não encontrada em '{module_path}'."

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

    def dispatch_chain(self, command: str) -> Optional[str]:
        """Executa múltiplos comandos encadeados separados por conectores naturais."""
        parts = _CHAIN_SEP.split(command)
        if len(parts) == 1:
            and_parts = _CHAIN_AND.split(command, maxsplit=1)
            if (
                len(and_parts) == 2
                and self._matches_route(and_parts[0])
                and self._matches_route(and_parts[1])
            ):
                parts = and_parts
        if len(parts) == 1:
            return self.dispatch(command)
        responses = []
        for part in parts:
            part = part.strip()
            if part:
                resp = self.dispatch(part)
                if resp:
                    responses.append(resp)
        return " | ".join(responses) if responses else None

    def _matches_route(self, text: str) -> bool:
        t = text.lower().strip()
        for pattern, _, _ in self._all_routes:
            if re.search(pattern, t):
                return True
        return False

    def _sync_tts_profile(self) -> None:
        try:
            from core.profiles import _get_manager
            mgr = _get_manager()
            if mgr.active == self._last_profile:
                return
            self._last_profile = mgr.active
            prof = mgr.PROFILES.get(mgr.active, {})
            if prof.get("tts_rate"):
                self.tts.set_rate(prof["tts_rate"])
            if prof.get("tts_volume"):
                self.tts.set_volume(prof["tts_volume"])
        except Exception:
            pass

    def _confirm(self, action: str) -> bool:
        """Solicita confirmação para ações críticas."""
        print(f"\n  [!] Ação crítica: '{action}'")
        resp = input("      Confirmar? (s/N): ").strip().lower()
        return resp == "s"
