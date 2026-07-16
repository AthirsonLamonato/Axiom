"""
core/orchestrator.py — Roteador central de comandos
Recebe texto (voz ou CLI), identifica a intenção e despacha ao módulo correto.
"""

import re
import logging
import threading
from typing import NamedTuple, Optional, Callable

from core.config import Config
from core.profiles import init_manager
from output.tts import TTS
from output.notifier import notify


logger = logging.getLogger(__name__)


class IntentResult(NamedTuple):
    """Resultado do pipeline NLU de 3 camadas (_intent_dispatch)."""
    response: Optional[str]
    provider: str
    tool: str
    fallback_used: bool


_EMPTY_INTENT_RESULT = IntentResult(None, "", "", False)

_VOICE_EXIT_COMMANDS = {
    "sair",
    "encerrar",
    "desligar",
    "desligar paçoca",
    "paçoca desligar",
}


def _is_voice_exit(command: str) -> bool:
    return command.lower().strip() in _VOICE_EXIT_COMMANDS


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
    # Informacoes locais basicas: nunca delegar ao LLM, que nao conhece o relogio.
    (r"^(?:que\s+horas(?:\s+s[ãa]o)?|qual\s+[ée]\s+a\s+hora|me\s+diga\s+as\s+horas|horas)$",
                                                "modules.local_info:current_time", False),
    (r"^(?:que\s+dia\s+[ée]\s+hoje|qual\s+[ée]\s+a\s+data(?:\s+de\s+hoje)?|data\s+de\s+hoje)$",
                                                "modules.local_info:current_date", False),
    # Spotify — rotas diretas (não passam pelo LLM)
    (r"autoriza\w*.*spotify",                             "modules.spotify_ctrl:authorize",      False),
    (r"toca?\s+(?:a\s+)?playlist\s+(.+)",                 "modules.spotify_ctrl:play_playlist",  False),
    (r"toca?\s+(?:a\s+)?m[úu]sica\s+(.+)",               "modules.spotify_ctrl:play_search",    False),
    (r"toca?\s+(?:o\s+artista\s+)?(.+)\s+no\s+spotify",  "modules.spotify_ctrl:play_search",    False),
    # Rota genérica: exclui palavras que claramente não são música (resumo, reunião, etc.)
    (r"to(?:ca?|qu?e?)\s+(?!(?:o\s+|a\s+)?(?:resumo|relat[oó]rio|transcri[çc][aã]o|sess[aã]o|reuni[aã]o|resultado|backup|config)\b)(.+)",
                                                           "modules.spotify_ctrl:play_search",    False),
    (r"play\s+(?!(?:o\s+|a\s+)?(?:resumo|relat[oó]rio|transcri[çc][aã]o|sess[aã]o|reuni[aã]o)\b)(.+)",
                                                           "modules.spotify_ctrl:play_search",    False),
    (r"(pausa|para|silencia)\s*(?:a\s+)?m[úu]sica",      "modules.spotify_ctrl:pause",          False),
    (r"(pausa|para)\s*(?:o\s+)?spotify",                  "modules.spotify_ctrl:pause",          False),
    (r"(retoma|continua|play)\s*(?:a\s+)?m[úu]sica",     "modules.spotify_ctrl:resume",         False),
    (r"pr[oó]xima\s*(?:m[úu]sica|faixa)?",               "modules.spotify_ctrl:next_track",     False),
    (r"(anterior|volta)\s*(?:m[úu]sica|faixa)?",         "modules.spotify_ctrl:previous_track", False),
    (r"o\s+que\s+(est[áa]\s+tocando|toca\s+agora)",      "modules.spotify_ctrl:current_track",  False),
    (r"que\s+m[úu]sica\s+[ée]\s+essa",                   "modules.spotify_ctrl:current_track",  False),
    # Browser + pesquisa combinado (deve vir antes das rotas genéricas de "abre")
    (r"abr[ae]\s+(?:o\s+)?(\w+)\s+(?:e\s+(?:pesquisa|busca|vai\s+(?:para|pro|pra))|no|na|em|n[oa]\s+(?:site|página|pagina)\s+(?:do|da|de)?)\s+(.+)",
                                              "modules.system_control:open_browser_with_search", False),
    # Dev tools específicos (antes das rotas genéricas de "abre/fecha")
    (r"abr[ae]\s+o\s+(vs\s?code|vscode|editor)", "modules.dev_tools:open_vscode",  False),
    (r"abr[ae]\s+o\s+arquivo\s+(.+)",        "modules.dev_tools:open_file",        False),
    (r"abr[ae]\s+o\s+file\s+(.+)",           "modules.dev_tools:open_file",        False),
    (r"vai\s+para\s+a?\s*linha\s+(\d+)",  "modules.dev_tools:goto_line",        False),
    (r"novo\s+terminal",                  "modules.dev_tools:open_terminal",    False),
    (r"cria\s+(arquivo|file)\s+(.+)",     "modules.dev_tools:create_file",      False),
    (r"explica\s+o\s+(?:arquivo|file)\s+(.+)", "modules.dev_tools:explain_file", False),
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
    (r"formata(?:r)?\s+(?:o\s+)?c[óo]digo", "modules.dev_tools:format_code",    False),

    # Overlay específico (antes de "abre/fecha" genérico)
    (r"abr[ae]\s+o\s+overlay",               "output.overlay:show",                False),
    (r"fecha\s+o\s+overlay",              "output.overlay:hide",                False),

    # Dashboard web (antes de "abre/fecha" genérico)
    (r"(abre|inicia)\s+o\s+dashboard",              "modules.web_server:start",  False),
    (r"(inicia|sobe)\s+(a\s+)?interface\s+web",     "modules.web_server:start",  False),
    (r"(para|fecha)\s+o\s+(servidor\s+web|dashboard)", "modules.web_server:stop", False),

    # Pastas
    (r"abr[ae]?\s+(?:a\s+)?pasta\s+(?:de\s+)?(.+)",  "modules.system_control:open_folder", False),
    (r"abr[ae]?\s+(?:o\s+)?explorador(?:\s+(?:de\s+)?(.+))?", "modules.system_control:open_folder", False),

    # Sistema (rotas genéricas por último)
    (r"volume\s+(\d+)",                   "modules.system_control:set_volume",  False),
    (r"(aumenta|sobe)\s+o\s+brilho",      "modules.system_control:brightness_up",   False),
    (r"(diminui|baixa)\s+o\s+brilho",     "modules.system_control:brightness_down", False),
    (r"(muta|silencia)\s+o?\s*(som|áudio)","modules.system_control:mute",       False),
    (r"(lista|mostra)\s+processos",       "modules.system_control:list_processes", False),
    (r"abr[ae]?\s+(https?://\S+)",        "modules.system_control:open_url",    False),
    (r"abr[ae]?\s+(.+)",                     "modules.system_control:open_app",    False),
    (r"fech[ae]?\s+(.+)",                    "modules.system_control:close_app",   True),

    # Transcrição
    (r"(?:começa|inicia|start)\s+transcri(?:ção|cao|crever)?(?:\s+(.*))?", "modules.transcription:start", False),
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
    (r"(?:explica?|o\s+que\s+é)\s+(.+)", "modules.summarizer:explain",         False),

    # Cotações financeiras
    (r"(?:qual\s+(?:é\s+)?(?:o\s+)?(?:valor|cotação|preço|cotacao)\s+(?:do|da|de)\s+|quanto\s+(?:está?|custa?|vale)\s+(?:o\s+|a\s+)?)(.+?)(?:\s+(?:hoje|agora|atualmente))?$",
                                          "modules.finance:get_quote",           False),
    (r"converte?\s+(.+)",                 "modules.finance:convert",             False),
    (r"([\d]+(?:[.,]\d+)?\s*(?:dólar(?:es)?|dolar(?:es)?|euro[s]?|bitcoin|btc|usd|eur)(?:\s+em\s+reais?)?)",
                                          "modules.finance:convert",             False),

    # Clima
    (r"(?:como\s+(?:está|ta|tá)\s+o\s+(?:clima|tempo)|previsão\s+(?:do\s+)?tempo|que\s+tempo\s+(?:faz|está))\s+(?:em\s+|n[ao]\s+)?(.+)",
                                          "modules.weather:get_weather",         False),
    (r"(?:como\s+(?:está|ta|tá)\s+o\s+(?:clima|tempo)|previsão\s+(?:do\s+)?tempo)$",
                                          "modules.weather:get_weather",         False),

    # Pesquisa / abrir URL direta
    (r"pesquis[ae]\w*\s+(.+)",             "modules.system_control:open_search", False),
    (r"busca\w*\s+(.+)",                  "modules.system_control:open_search", False),
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
    (r"foco\s+por\s+(\d+)\s*h",           "modules.productivity:focus_start_hours", False),
    (r"(cancela|para)\s+o\s+timer",       "modules.productivity:focus_stop",    False),
    (r"(quanto\s+tempo|status)\s+(do\s+)?timer", "modules.productivity:focus_status", False),
    (r"(tomei|fiz)\s+uma\s+pausa",        "modules.productivity:take_break",    False),

    # Briefing diário proativo
    (r"(bom\s+dia|resumo\s+do\s+dia|briefing)", "modules.briefing:generate",    False),

    # Hábitos e sugestões de automação
    (r"(sugest[õo]es|o\s+que\s+voc[êe]\s+sugere|algum\s+padr[ãa]o|detecta\s+h[áa]bitos|meus\s+h[áa]bitos)",
                                                          "modules.habits:suggest",  False),

    # Confiança aprendida para confirmações
    (r"(n[íi]vel\s+de\s+confian[çc]a|o\s+que\s+voc[êe]\s+confia|confian[çc]a\s+aprendida)",
                                                          "modules.trust:status",    False),
    (r"(reseta|zera|limpa)\s+(a\s+)?confian[çc]a",        "modules.trust:reset",     False),

    # Cache semântico de roteamento
    (r"(status|estat[íi]sticas?)\s+do\s+cache\s+sem[âa]ntico", "modules.semantic_router:stats", False),
    (r"limpa\s+(o\s+)?cache\s+sem[âa]ntico",              "modules.semantic_router:clear", False),

    # WhatsApp (sintaxe explícita; pedidos em linguagem livre caem no loop agentivo)
    (r"(?:manda|envia)\s+(?:uma\s+)?mensagem\s+(?:no\s+whatsapp\s+)?(?:para|pra)\s+(.+?)\s+dizendo\s+(.+)",
                                                          "modules.whatsapp:send",  True),

    # Detector de reunião automático
    (r"(ativa|inicia|liga)\s+(o\s+)?detector\s+de\s+reuni[aã]o",
                                                          "modules.meeting_detector:start_monitoring", False),
    (r"(desativa|para|desliga)\s+(o\s+)?detector\s+de\s+reuni[aã]o",
                                                          "modules.meeting_detector:stop_monitoring",  False),
    (r"(status|estado)\s+do\s+detector(\s+de\s+reuni[aã]o)?",
                                                          "modules.meeting_detector:status",           False),

    # Perfis dinâmicos por voz
    (r"(?:muda|ativa)\s+(?:para\s+)?perfil\s+(.+)", "core.profiles:switch_profile", False),
    (r"perfil\s+(work|casual|focus|foco|meeting|reunião|reuniao|noturno|noite|trabalho)",
                                                  "core.profiles:switch_profile",   False),
    (r"(qual|mostra)\s+(o\s+)?perfil(\s+atual)?", "core.profiles:current_profile",  False),
    (r"(lista|quais)\s+(os\s+)?perfis",           "core.profiles:list_profiles",    False),

    # Google Calendar
    (r"(?:o\s+que\s+tenho|agenda)\s+(hoje|amanhã|amanha)",
                                                  "modules.calendar_integration:get_day_events", False),
    (r"(próximo|proximo)\s+(evento|compromisso|reunião|reuniao)",
                                                  "modules.calendar_integration:get_next_event",   False),
    (r"(?:adiciona|marca|cria)\s+(?:no\s+calendário|no\s+calendario|evento|reunião|reuniao)\s+(.+)",
                                                  "modules.calendar_integration:add_event",        False),
    (r"(?:apaga|cancela|remove)\s+(?:o\s+)?(?:evento|reunião|reuniao)\s+(.+)",
                                                  "modules.calendar_integration:delete_event",     True),
    (r"autoriza\s+(calendário|calendario|google\s+calendar)",
                                                  "modules.calendar_integration:auth_calendar",    False),

    # Calibração de microfone + idioma STT
    (r"(calibra|recalibra)\s+(o\s+)?(microfone|mic|ruído|ruido)",
                                                  "input.stt:calibrar_microfone",                  False),
    (r"(?:muda|troca|altera)\s+(?:para\s+)?(inglês|ingles|espanhol|francês|frances|alemão|alemao|português|portugues|italiano|japonês|japones|english|spanish|french|german|italian|japanese)\b",
                                                  "input.stt:switch_language",                     False),
    (r"idioma\s+atual",                           "input.stt:current_language",                    False),

    # Lembretes
    (r"(me\s+lembra?\s+.+)",                     "modules.reminders:add",                         False),
    (r"(lista|mostra)\s+(os\s+)?lembretes",       "modules.reminders:list_reminders",              False),
    (r"cancela\s+(?:o\s+)?lembrete[s]?(?:\s+(\d+))?", "modules.reminders:cancel",                  False),

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

    # Memória / knowledge base
    (r"lembra\s+que\s+(.+)",              "core.orchestrator:kb_remember",       False),
    (r"esquece?\s+(?:que\s+)?(.+)",       "core.orchestrator:kb_forget",         False),
    (r"o\s+que\s+você\s+(sabe|lembra|conhece)\s+(sobre\s+)?mim",
                                          "core.orchestrator:kb_show",           False),
    (r"mostra\s+(?:as\s+)?memórias?",     "core.orchestrator:kb_show",           False),
    (r"mostra\s+(?:as\s+)?prefer[eê]ncias?","core.orchestrator:kb_show_prefs",   False),

    # Vocabulário e aprendizado
    (r"aprende\s+que\s+(.+?)\s+(?:significa|é|quer dizer)\s+(.+)",
                                          "core.orchestrator:teach_vocabulary",  False),
    (r"(relatório|relatorio)\s+de\s+aprendizado", "core.orchestrator:learning_report", False),
    (r"o\s+que\s+você\s+(aprendeu|sabe)",  "core.orchestrator:learning_report",  False),

    # Backup
    (r"(?:faz?|faz\s+um?|executa)\s+backup",  "modules.backup:backup_all",          False),
    (r"backup\s+(?:agora|local|drive)",        "modules.backup:backup_all",          False),

    # Integrações e manutenção
    (r"(status|estado)\s+das?\s+integra[çc][oõ]es?", "core.orchestrator:integration_status", False),
    (r"(testa|verifica)\s+(as?\s+)?integra[çc][oõ]es?", "core.orchestrator:integration_status", False),
    (r"limpa\s+(os\s+)?dados\s+antigos",               "core.orchestrator:cleanup_old_data",   False),

    # Meta
    (r"^(?:ajuda|help|\?)(?:\s+(.+))?$",   "core.orchestrator:list_commands",    False),
]

_CHAIN_SEP = re.compile(
    r'\s+(?:e depois|depois disso|em seguida|então|entao)\s+', re.IGNORECASE
)
_CHAIN_AND = re.compile(r'\s+e\s+', re.IGNORECASE)


COMMAND_HELP: list[tuple[str, list[str]]] = [
    ("Sistema e apps", [
        "abre o VS Code",
        "abre a pasta projetos",
        "abre https://example.com",
        "fecha o Chrome",
        "volume 70",
        "lista processos",
    ]),
    ("Produtividade", [
        "modo trabalho",
        "modo foco",
        "fim do dia",
        "foco por 25 min",
        "relatório de produtividade",
        "briefing",
        "sugestões",
    ]),
    ("Reuniões e notas", [
        "começa transcrição",
        "para transcrição",
        "mostra o que foi falado",
        "resume a reunião",
        "exporta transcrição para obsidian",
        "salva screenshot",
    ]),
    ("Dev e git", [
        "abre o arquivo main.py",
        "vai para linha 42",
        "o que mudou",
        'commit "fix: corrige inicialização"',
        "git log",
        "roda os testes",
    ]),
    ("Agenda, lembretes e mensagens", [
        "agenda hoje",
        "próximo evento",
        "adiciona evento dentista amanhã às 10h30",
        "me lembra em 30 minutos de fazer backup",
        "lista lembretes",
        "manda mensagem para Maria dizendo chego em 10 minutos",
    ]),
    ("Conhecimento e IA", [
        "pesquisa decorators em Python",
        "busca por ia melhores práticas de pytest",
        "explica closures",
        "lembra que prefiro respostas curtas",
        "mostra memórias",
        "relatório de aprendizado",
    ]),
    ("Integrações e manutenção", [
        "status das integrações",
        "lista plugins",
        "recarrega plugins",
        "faz backup",
        "limpa dados antigos",
        "status do cache semântico",
    ]),
]

COMMAND_HELP_ALIASES: dict[str, str] = {
    "app": "Sistema e apps",
    "apps": "Sistema e apps",
    "sistema": "Sistema e apps",
    "processos": "Sistema e apps",
    "produtividade": "Produtividade",
    "foco": "Produtividade",
    "pomodoro": "Produtividade",
    "reuniao": "Reuniões e notas",
    "reunião": "Reuniões e notas",
    "reunioes": "Reuniões e notas",
    "reuniões": "Reuniões e notas",
    "notas": "Reuniões e notas",
    "transcricao": "Reuniões e notas",
    "transcrição": "Reuniões e notas",
    "dev": "Dev e git",
    "git": "Dev e git",
    "codigo": "Dev e git",
    "código": "Dev e git",
    "agenda": "Agenda, lembretes e mensagens",
    "calendario": "Agenda, lembretes e mensagens",
    "calendário": "Agenda, lembretes e mensagens",
    "lembretes": "Agenda, lembretes e mensagens",
    "whatsapp": "Agenda, lembretes e mensagens",
    "mensagens": "Agenda, lembretes e mensagens",
    "ia": "Conhecimento e IA",
    "pesquisa": "Conhecimento e IA",
    "memoria": "Conhecimento e IA",
    "memória": "Conhecimento e IA",
    "conhecimento": "Conhecimento e IA",
    "integracoes": "Integrações e manutenção",
    "integrações": "Integrações e manutenção",
    "plugins": "Integrações e manutenção",
    "backup": "Integrações e manutenção",
    "manutencao": "Integrações e manutenção",
    "manutenção": "Integrações e manutenção",
}

COMMAND_DETAIL_HELP: dict[str, dict[str, object]] = {
    "commit": {
        "title": "commit",
        "description": "Cria um commit Git com a mensagem informada. Pode pedir confirmação.",
        "examples": [
            'commit "fix: corrige inicialização"',
            'commit "feat: adiciona lembretes"',
        ],
        "aliases": ["git commit"],
    },
    "lembrete": {
        "title": "lembretes",
        "description": "Cria, lista ou cancela lembretes locais.",
        "examples": [
            "me lembra em 30 minutos de fazer backup",
            "lista lembretes",
            "cancela lembrete 2",
        ],
        "aliases": ["lembretes", "reminder", "reminders"],
    },
    "volume": {
        "title": "volume",
        "description": "Ajusta o volume do sistema para um valor de 0 a 100.",
        "examples": ["volume 30", "volume 70"],
        "aliases": ["som", "audio", "áudio"],
    },
    "transcricao": {
        "title": "transcrição",
        "description": "Controla captura, visualização e resumo de transcrições.",
        "examples": [
            "começa transcrição",
            "mostra o que foi falado",
            "resume a reunião",
            "para transcrição",
        ],
        "aliases": ["transcrição", "reuniao", "reunião"],
    },
    "evento": {
        "title": "agenda",
        "description": "Consulta e gerencia eventos do calendário.",
        "examples": [
            "agenda hoje",
            "próximo evento",
            "adiciona evento dentista amanhã às 10h30",
        ],
        "aliases": ["agenda", "calendario", "calendário"],
    },
    "whatsapp": {
        "title": "whatsapp",
        "description": "Envia mensagem para contato configurado ou número informado. Pede confirmação.",
        "examples": ["manda mensagem para Maria dizendo chego em 10 minutos"],
        "aliases": ["mensagem", "mensagens"],
    },
    "backup": {
        "title": "backup",
        "description": "Executa backup local ou integração configurada.",
        "examples": ["faz backup", "backup agora"],
        "aliases": ["backups"],
    },
    "teste": {
        "title": "testes",
        "description": "Executa a suíte de testes configurada para o projeto.",
        "examples": ["roda os testes", "executa os testes"],
        "aliases": ["testes", "pytest"],
    },
}


def kb_remember(statement: str) -> str:
    try:
        from storage.knowledge_base import remember
        return remember(statement.strip())
    except Exception as e:
        return f"Erro ao memorizar: {e}"


def kb_forget(key: str) -> str:
    try:
        from storage.knowledge_base import forget
        return forget(key.strip())
    except Exception as e:
        return f"Erro ao esquecer: {e}"


def kb_show(*_) -> str:
    try:
        from storage.knowledge_base import show_memories
        return show_memories()
    except Exception as e:
        return f"Erro ao listar memórias: {e}"


def kb_show_prefs(*_) -> str:
    try:
        from storage.knowledge_base import show_memories
        return show_memories("preferences")
    except Exception as e:
        return f"Erro: {e}"


def teach_vocabulary(heard: str, intended: str) -> str:
    """Ensina o Paçoca que `heard` deve ser interpretado como `intended`."""
    try:
        from modules.learner import learn_vocabulary_from_correction
        learn_vocabulary_from_correction(heard.strip(), intended.strip())
        return f"Entendido! Quando eu escutar '{heard}', vou interpretar como '{intended}'."
    except Exception as e:
        return f"Erro ao aprender vocabulário: {e}"


def learning_report(*_) -> str:
    """Retorna relatório de aprendizado acumulado."""
    try:
        from modules.learner import analyze_and_optimize
        return analyze_and_optimize()
    except Exception as e:
        return f"Erro ao gerar relatório: {e}"


def cleanup_old_data(*_) -> str:
    """Remove dados de histórico antigos conforme política de retenção."""
    try:
        from core.config import Config
        from storage.db import cleanup_old_data as _cleanup
        days = Config().get("privacy.retention_days", 30)
        return _cleanup(days=days)
    except Exception as e:
        return f"Erro na limpeza: {e}"


def integration_status(*_) -> str:
    """Verifica e retorna o status de todas as integrações configuradas."""
    try:
        from web.app import _check_integrations
        integrations = _check_integrations()
        lines = ["Status das integrações:"]
        for name, info in integrations.items():
            mark = "✓" if info.get("ok") else "✗"
            detail = info.get("detail", "")
            lines.append(f"  {mark} {name}: {detail}")
        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao verificar integrações: {e}"


def _help_topic_label(topic: str) -> str:
    normalized = topic.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized in COMMAND_HELP_ALIASES:
        return COMMAND_HELP_ALIASES[normalized]
    for title, _examples in COMMAND_HELP:
        if normalized == title.lower() or normalized in title.lower():
            return title
    return ""


def _help_detail(topic: str) -> dict[str, object] | None:
    normalized = topic.lower().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    for key, info in COMMAND_DETAIL_HELP.items():
        aliases = [key, *info.get("aliases", [])]
        if normalized in aliases:
            return info
    for key, info in COMMAND_DETAIL_HELP.items():
        aliases = [key, *info.get("aliases", [])]
        if any(alias in normalized for alias in aliases):
            return info
    return None


def _format_command_detail(info: dict[str, object]) -> str:
    examples = info.get("examples", [])
    lines = [
        f"Ajuda: {info.get('title', 'comando')}",
        str(info.get("description", "")),
        "",
        "Exemplos:",
    ]
    lines.extend(f"  - {example}" for example in examples)
    lines.append("\nUse 'ajuda' para ver todos os tópicos.")
    return "\n".join(lines)


def _format_help_section(title: str, examples: list[str]) -> list[str]:
    return [f"\n[{title}]", *(f"  - {example}" for example in examples)]


def list_commands(topic: str = "") -> str:
    """Lista comandos disponíveis em formato amigável."""
    try:
        import importlib
        from core.plugin_loader import _registry
        plugin_count = 0
        for info in _registry.values():
            mod = importlib.import_module(info["module"])
            plugin_count += len(getattr(mod, "ROUTES", []))
    except Exception:
        plugin_count = 0

    route_count = len(ROUTES) + plugin_count

    if topic:
        detail = _help_detail(topic)
        if detail:
            return _format_command_detail(detail)
        label = _help_topic_label(topic)
        if not label:
            available = ", ".join(title for title, _examples in COMMAND_HELP)
            return (
                f"Não encontrei ajuda para '{topic}'.\n"
                f"Tópicos disponíveis: {available}."
            )
        for title, examples in COMMAND_HELP:
            if title == label:
                lines = [f"Ajuda: {title}"]
                lines.extend(_format_help_section(title, examples))
                lines.append("\nUse 'ajuda' para ver todos os tópicos.")
                return "\n".join(lines)

    lines = [
        "Comandos disponíveis",
        f"{route_count} rotas carregadas. Exemplos por categoria:",
    ]

    for title, examples in COMMAND_HELP:
        lines.extend(_format_help_section(title, examples))

    lines.extend([
        "\nDicas:",
        "  - Você pode encadear ações com 'e depois'.",
        "  - Use linguagem natural quando não lembrar o comando exato.",
        "  - Comandos de risco, como fechar apps ou enviar mensagens, podem pedir confirmação.",
    ])

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
        self._tts_done = False  # True quando _fallback_ai fez TTS via streaming
        self._dispatch_lock = threading.RLock()
        self._load_plugins()
        try:
            from modules import web_server
            web_server.set_orc(self)
        except Exception:
            pass
        self._start_backup_scheduler()

    def _start_backup_scheduler(self) -> None:
        """Agenda backup automático diário se habilitado na config."""
        if not self.config.get("backup.auto_schedule", True):
            return
        backup_time = self.config.get("backup.daily_time", "23:30")
        try:
            import schedule
            import threading
            import time as _time

            schedule.every().day.at(backup_time).do(self._run_scheduled_backup)

            def _scheduler_loop():
                while True:
                    schedule.run_pending()
                    _time.sleep(60)

            t = threading.Thread(target=_scheduler_loop, daemon=True, name="backup-scheduler")
            t.start()
            logger.info("Backup automático agendado para %s diariamente.", backup_time)
        except Exception as e:
            logger.warning("Agendamento de backup falhou: %s", e)

    def _run_scheduled_backup(self) -> None:
        try:
            from modules.backup import backup_all
            result = backup_all()
            logger.info("Backup automático: %s", result)
            notify("Paçoca", result)
        except Exception as e:
            logger.error("Backup automático falhou: %s", e)

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
        cli = _import_module("input.cli")
        if cli:
            cli.print_banner()
            cli.print_status(
                mode="text",
                profile=self.config.get("profile.active", "work"),
                overlay=bool(self.config.get("overlay.enabled", True)),
                tts=bool(self.config.get("tts.enabled", True)),
            )
        else:
            print("[Paçoca] Modo texto ativo. Digite seu comando (ou 'sair' para encerrar).")
        while True:
            try:
                if overlay:
                    overlay.set_state("listening")
                command = cli.get_command() if cli else input("  > ").strip()
                if not command:
                    continue
                if (cli and cli.is_exit(command)) or (not cli and command.lower() in ("sair", "exit", "quit")):
                    print("Paçoca encerrada.")
                    break
                if overlay:
                    overlay.set_state("processing")

                learner = _import_module("modules.learner")
                corrected = learner.correct_transcription(command) if learner else command

                self._tts_done = False
                response = self.dispatch_chain(corrected)
                if response:
                    if cli:
                        cli.print_response(response)
                    else:
                        print(f"\n  Paçoca: {response}\n")
                    if overlay:
                        overlay.show_message(response)
                        overlay.set_state("speaking")
                    if not self._tts_done:
                        self.tts.speak(response)

                if learner:
                    success = bool(response and "não entendi" not in response.lower()
                                   and "não consegui" not in response.lower())
                    learner.record(command, response or "", resolved=corrected, source="text",
                                   success=success)

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

        # Atalhos globais: PTT e controle de transcrição.
        hotkeys = None
        try:
            from input.hotkeys import HotkeyManager
            hotkeys = HotkeyManager(self.config, self.process_external_command)
            voice.enable_push_to_talk_hotkey(hotkeys.start())
        except Exception as e:
            logger.warning("Hotkeys não inicializadas: %s", e)
            voice.enable_push_to_talk_hotkey(False)

        # Registra confirmação por voz para ações críticas
        try:
            stt_module.register_voice_confirmation_callback(voice, self.tts.speak)
        except Exception as e:
            logger.warning("Callback de confirmação por voz não registrado: %s", e)

        mode = voice._mode
        if mode == "push_to_talk":
            trigger = "Ctrl+Shift+Space" if hotkeys and hotkeys._active else "Enter"
            print(f"[Paçoca] Modo push-to-talk ativo. Pressione {trigger} para falar.\n")
        else:
            keyword = self.config.get("wake_word.keyword", "paçoca")
            print(f"[Paçoca] Aguardando wake word '{keyword}'...\n")
        self.tts.speak("Paçoca online.")

        try:
            while True:
                if overlay:
                    overlay.set_state("listening")
                command = voice.listen_for_command()
                if command and _is_voice_exit(command):
                    self.tts.speak("Até logo.")
                    print("[Paçoca] Encerrando modo voz.")
                    break
                if command:
                    logger.info(f"Comando recebido: {command}")
                    if overlay:
                        overlay.set_state("processing")

                    learner = _import_module("modules.learner")
                    corrected = learner.correct_transcription(command) if learner else command

                    self._tts_done = False
                    response = self.dispatch_chain(corrected)
                    if response:
                        print(f"\n  Paçoca: {response}\n")
                        if overlay:
                            overlay.show_message(response)
                            overlay.set_state("speaking")
                        if not self._tts_done:
                            self.tts.speak(response)

                    if learner:
                        success = bool(response and "não entendi" not in response.lower()
                                       and "não consegui" not in response.lower())
                        learner.record(command, response or "", resolved=corrected, source="voice",
                                       success=success)

                    if overlay:
                        overlay.set_state("idle")
        finally:
            if hotkeys:
                hotkeys.stop()
            voice.close()

    def process_external_command(self, command: str) -> Optional[str]:
        """Executa um comando vindo de hotkey e entrega a resposta ao usuário."""
        overlay = _import_module("output.overlay")
        if overlay:
            overlay.set_state_detail("processing", "Executando atalho")
        self._tts_done = False
        response = self.dispatch_chain(command)
        if response:
            print(f"\n  Paçoca: {response}\n")
            if overlay:
                overlay.show_message(response)
                overlay.set_state("speaking")
            if not self._tts_done:
                self.tts.speak(response)
        if overlay:
            overlay.set_state("idle")
        return response

    # ── Despachante central ────────────────────────────────────────────

    def dispatch(self, command: str) -> Optional[str]:
        import time as _time

        # Resolve seguimento/anáfora usando o turno anterior ("de novo",
        # "fecha ele", "e amanhã?") antes de rotear.
        try:
            from modules import anaphora
            resolved_cmd = anaphora.resolve(command)
            if resolved_cmd and resolved_cmd != command:
                logger.info("Anáfora resolvida: %r → %r", command, resolved_cmd)
                command = resolved_cmd
        except Exception:
            pass

        command_lower = command.lower().strip()
        logger.debug("Despachando: %s", command_lower)

        _t0 = _time.monotonic()
        _route_matched = ""
        _provider = ""
        _tool = ""
        _fallback_used = False
        response: Optional[str] = None

        overlay = _import_module("output.overlay")

        for pattern, handler_path, needs_confirm in self._all_routes:
            match = re.search(pattern, command_lower)
            if match:
                if needs_confirm and self.config.get("security.confirm_critical"):
                    if overlay:
                        overlay.set_state_detail("processing", "Aguardando confirmação")
                    if not self._confirm(command):
                        return "Ação cancelada."
                _route_matched = handler_path
                _provider = "local"
                _tool = handler_path.split(":")[-1]
                # Overlay: label descritivo baseado no módulo
                if overlay:
                    _mod = handler_path.split(":")[0].replace("modules.", "").replace("_", " ")
                    overlay.set_state_detail("processing", f"Executando {_mod}")
                response = self._call_handler(handler_path, match)
                break

        if response is None:
            if overlay:
                overlay.set_state_detail("processing", "Analisando comando")
            result = self._intent_dispatch(command)
            response, _provider, _tool, _fallback_used = result
            if response:
                _route_matched = "intent"

        if response is None:
            if overlay:
                try:
                    from core.providers import _circuit_is_open
                    _lbl = "Usando IA local" if _circuit_is_open() else "Consultando Groq"
                except Exception:
                    _lbl = "Consultando IA"
                overlay.set_state_detail("processing", _lbl)
            response = self._fallback_ai(command)
            if response:
                _route_matched = "fallback_ai"
                _fallback_used = True
                try:
                    from core.providers import _circuit_is_open
                    _provider = "ollama" if _circuit_is_open() else "groq"
                except Exception:
                    _provider = "groq"

        # Telemetria
        try:
            from core.telemetry import record_command
            record_command(
                command=command,
                route=_route_matched,
                tool=_tool,
                provider=_provider,
                latency_s=_time.monotonic() - _t0,
                success=bool(response and "Erro" not in (response or "")[:20]),
                fallback_used=_fallback_used,
            )
        except Exception:
            pass

        # Registra no contexto e expõe para clipboard
        if response:
            from storage.context import add as _ctx_add
            _ctx_add(command, response)
            try:
                from modules.clipboard_tools import set_last_response
                set_last_response(response)
            except Exception:
                pass

        # Log na KB e extração de aprendizado em background
        try:
            from storage.knowledge_base import log_conversation, extract_and_learn
            log_conversation(command, response or "")
            if response:
                extract_and_learn(command, response)
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

    def _intent_dispatch(self, command: str) -> IntentResult:
        """
        Interpreta o comando via NLU e executa ações.
        Ordem de prioridade:
          1. TF-IDF local (<5ms, sem rede) — se confiante, executa diretamente.
          2. Loop agentivo Groq — se provider in (groq, auto) e chave configurada.
          3. Ollama few-shot — fallback local sem internet.
        O registro de contexto é feito por dispatch() depois que este método retorna.
        """
        intent = _import_module("modules.intent")
        if not intent:
            return _EMPTY_INTENT_RESULT

        # 1. Classificador local (cache + TF-IDF) — sem chamada de rede
        local_calls = intent.classify_local(command)
        if local_calls:
            responses = intent.execute_actions(local_calls)
            # classify_local retorna dicts com chave "name" (não "intent")
            first = local_calls[0] if local_calls else {}
            tool = first.get("name") or first.get("intent", "")
            return IntentResult(
                " | ".join(responses) if responses else None, "local", tool, False
            )

        # 1.5 Cache semântico — paráfrases de comandos já resolvidos pelo LLM
        # são servidas localmente (custa só um embedding, não o loop agentivo).
        try:
            from modules import semantic_router
            sem_calls = semantic_router.recall(command)
            if sem_calls:
                responses = intent.execute_actions(sem_calls)
                tool = sem_calls[0].get("name", "") if sem_calls else ""
                return IntentResult(
                    " | ".join(responses) if responses else None, "semantic", tool, False
                )
        except Exception as e:
            logger.debug("semantic_router.recall falhou: %s", e)

        # 2. Loop agentivo Groq — executa e produz resposta natural
        provider = self.config.get("ai.provider", "ollama")
        try:
            from core.providers import _resolve_key
            api_key = _resolve_key("ai.groq_api_key", "GROQ_API_KEY", self.config)
        except Exception:
            import os as _os
            api_key = self.config.get("ai.groq_api_key", "") or _os.environ.get("GROQ_API_KEY", "")
        if provider in ("groq", "auto") and api_key:
            _ov = _import_module("output.overlay")
            if _ov:
                _ov.set_state_detail("processing", "Consultando Groq")
            try:
                response = intent.run_agentic_loop(command)
                if response:
                    return IntentResult(response, "groq", "agentic_loop", False)
            except Exception as e:
                logger.warning("run_agentic_loop falhou, usando Ollama: %s", e)

        # 3. Pipeline Ollama — usa parse_intent_ollama para não chamar Groq novamente
        _ov = _import_module("output.overlay")
        if _ov:
            _ov.set_state_detail("processing", "Usando IA local")
        parse_fn = getattr(intent, "parse_intent_ollama", intent.parse_intent)
        actions = parse_fn(command)
        if not actions:
            return _EMPTY_INTENT_RESULT
        # Memoriza para o cache semântico aprender com resoluções do Ollama
        try:
            from modules import semantic_router
            semantic_router.remember(command, actions)
        except Exception:
            pass
        responses = intent.execute_actions(actions)
        first_action = actions[0] if actions else {}
        tool = first_action.get("name") or first_action.get("intent", "")
        return IntentResult(
            " | ".join(responses) if responses else None, "ollama", tool, True
        )

    def _fallback_ai(self, command: str) -> str:
        """
        Repassa ao LLM quando nenhuma rota bate.
        Usa streaming se TTS estiver ativo — fala frase por frase enquanto o LLM gera,
        e sinaliza _tts_done para que o loop de voz/texto não duplique a fala.
        """
        summarizer = _import_module("modules.summarizer")
        if not summarizer:
            return "Não entendi o comando. Tente novamente."

        ask_stream = getattr(summarizer, "ask_ai_stream", None)
        if ask_stream and self.tts.enabled:
            try:
                gen = ask_stream(command)
                # Fala frase por frase (bloqueante neste thread) e coleta o texto completo
                full_text = self._stream_and_collect(gen)
                if full_text:
                    self._tts_done = True
                    return full_text
            except Exception as e:
                logger.warning("ask_ai_stream falhou, usando ask_ai: %s", e)

        return summarizer.ask_ai(command)

    def _stream_and_collect(self, gen) -> str:
        """Fala um gerador de chunks frase por frase e retorna o texto completo."""
        import re as _re
        sent_end = _re.compile(r'(?<=[.!?])\s+')
        buffer = ""
        full = ""
        for chunk in gen:
            full += chunk
            buffer += chunk
            parts = sent_end.split(buffer)
            if len(parts) > 1:
                for sentence in parts[:-1]:
                    s = sentence.strip()
                    if s:
                        self.tts._speak_sync(s)
                buffer = parts[-1]
        if buffer.strip():
            self.tts._speak_sync(buffer.strip())
        return full.strip()

    def dispatch_chain(self, command: str) -> Optional[str]:
        """Serializa comandos vindos de voz, overlay, web e hotkeys."""
        with self._dispatch_lock:
            return self._dispatch_chain_unlocked(command)

    def _dispatch_chain_unlocked(self, command: str) -> Optional[str]:
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
            if not part:
                continue
            self._tts_done = False
            resp = self.dispatch(part)
            if resp:
                responses.append(resp)
                if not self._tts_done:
                    self.tts.speak(resp)
        # Cada parte já foi falada (streaming ou speak() acima) — sinaliza ao
        # chamador para não falar o texto combinado de novo.
        self._tts_done = True
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
        """Solicita confirmação para ações críticas. Nega automaticamente fora do terminal."""
        import sys
        if not sys.stdin.isatty():
            logger.warning("Ação crítica '%s' bloqueada fora do modo texto.", action)
            return False
        print(f"\n  [!] Ação crítica: '{action}'")
        resp = input("      Confirmar? (s/N): ").strip().lower()
        return resp == "s"
