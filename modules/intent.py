"""
modules/intent.py — Pipeline de NLU em 3 camadas

  Camada 1 (orchestrator.py) — Regex          <1ms   padrões fixos e previsíveis
  Camada 2 (este módulo)     — TF-IDF clf     <5ms   intent + slots para comandos variáveis
  Camada 3 (este módulo)     — LLM fallback   1-3s   perguntas abertas e casos ambíguos

A Camada 2 funciona como o NLU da Alexa: normaliza o texto (remove valores de slot),
classifica por similaridade de cosseno, e extrai os slots com regex focado por intent.
O LLM só entra quando a confiança do classificador fica abaixo do limiar.
"""

import json
import logging
import os
import re
import sys
from collections import deque
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ── Ferramentas disponíveis (schema do LLM) ────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Abre qualquer aplicativo, ferramenta do sistema ou configuração do Windows pelo nome. Inclui apps instalados, ferramentas como regedit, gerenciador de dispositivos, painel de controle, gerenciador de tarefas, msconfig, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nome do app (ex: spotify, discord, brave, notepad)"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_browser",
            "description": "Abre um navegador em um site específico ou com uma busca no Google.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {"type": "string", "description": "Nome do navegador (brave, chrome, firefox, edge)"},
                    "destination": {"type": "string", "description": "Nome do site (youtube, github) ou termo de busca"},
                },
                "required": ["browser", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_start",
            "description": "Inicia uma sessão local supervisionada do navegador. Não use para ações externas; apenas prepara a sessão.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL autorizada ou about:blank"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navega para uma URL dentro dos domínios autorizados no Paçoca.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL http(s) autorizada"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_inspect",
            "description": "Lê o título, URL e texto visível da página atual.",
            "parameters": {
                "type": "object",
                "properties": {"max_chars": {"type": "integer", "description": "Máximo de caracteres"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Clica em um elemento da página usando um seletor CSS.",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string", "description": "Seletor CSS do elemento"}},
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Preenche um campo de formulário. O envio final de dados exige confirmação.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Seletor CSS do campo"},
                    "value": {"type": "string", "description": "Valor a preencher"},
                },
                "required": ["selector", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Salva uma captura da página atual para inspeção.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Caminho do arquivo"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "Encerra a sessão local do navegador.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_media",
            "description": "Controla reprodução de mídia no Spotify: tocar música ou playlist, pausar, próxima, anterior, ver o que está tocando.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "resume", "next", "previous", "current"],
                        "description": "Ação a executar",
                    },
                    "query": {
                        "type": "string",
                        "description": "Nome da música, artista ou playlist (somente para action=play)",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_application",
            "description": "Fecha/encerra um aplicativo em execução.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nome do processo ou app a fechar"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Ajusta o volume do sistema para um valor entre 0 e 100.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "integer", "description": "Nível de volume (0-100)"}
                },
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Pesquisa algo na internet e retorna um resumo dos resultados.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termo ou pergunta a pesquisar"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_operation",
            "description": "Executa operações Git: status, log, push, pull, commit, criar branch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["status", "log", "push", "pull", "commit", "branch"],
                    },
                    "message": {"type": "string", "description": "Mensagem de commit (somente para operation=commit)"},
                    "branch_name": {"type": "string", "description": "Nome da branch (somente para operation=branch)"},
                },
                "required": ["operation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_folder",
            "description": "Abre uma pasta no explorador de arquivos. Aceita nome comum (downloads, documentos, desktop, imagens) ou caminho absoluto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Nome da pasta (downloads, documentos, desktop) ou caminho completo"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "answer_question",
            "description": "Responde perguntas gerais, explica conceitos, ou conversa livremente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "A pergunta ou assunto"}
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Memoriza um fato, preferência ou hábito que o usuário quer que o assistente lembre. Use quando o usuário disser 'lembra que', 'guarda que', 'não esquece que', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "statement": {"type": "string", "description": "O que deve ser memorizado, em linguagem natural"}
                },
                "required": ["statement"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget",
            "description": "Remove uma memória específica. Use quando o usuário disser 'esquece que', 'apaga a memória sobre', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "O tópico ou frase a esquecer"}
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memories",
            "description": "Lista o que o assistente tem memorizado sobre o usuário.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "description": "Filtro opcional (preferences, habits, projects, facts)"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Lista os eventos da agenda do Google Calendar para hoje ou amanhã.",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {"type": "string", "enum": ["hoje", "amanhã"], "description": "Dia a consultar"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_next_calendar_event",
            "description": "Retorna o próximo evento agendado a partir de agora no Google Calendar.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Cria um evento/reunião no Google Calendar. Use quando o usuário pedir para marcar, agendar ou criar uma reunião/evento/compromisso.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Título/assunto do evento"},
                    "day": {"type": "string", "description": "'hoje', 'amanhã', ou data no formato AAAA-MM-DD"},
                    "time": {"type": "string", "description": "Horário no formato HH:MM (24h)"},
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "E-mails dos convidados (opcional) — só inclua e-mails que o usuário mencionou explicitamente",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": "Apaga/cancela um evento do Google Calendar pelo título. Use quando o usuário pedir para apagar, cancelar ou remover uma reunião/evento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Título (ou parte dele) do evento a apagar"},
                    "day": {"type": "string", "description": "Opcional: 'hoje' ou 'amanhã', pra restringir a busca"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_whatsapp_message",
            "description": (
                "Envia uma mensagem de WhatsApp para um contato. Use quando o usuário "
                "pedir para mandar mensagem, perguntar algo para alguém ou avisar alguém "
                "via WhatsApp. Componha o texto da mensagem de forma natural a partir do "
                "pedido (ex: 'pede pro fulano o que ele está fazendo' → mensagem tipo "
                "'Oi! O que você está fazendo?'). Por segurança, o envio só é concluído "
                "se o número resolvido estiver na whitelist do usuário."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contact": {"type": "string", "description": "Nome do contato (cadastrado em whatsapp.contacts) ou número"},
                    "message": {"type": "string", "description": "Texto da mensagem, composto de forma natural"},
                },
                "required": ["contact", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_calendar_event",
            "description": "Remarca (data/hora) ou renomeia um evento existente do Google Calendar, encontrado por título. Use quando o usuário pedir para mudar, remarcar, adiar ou renomear uma reunião/evento. Informe ao menos um de new_day/new_time/new_title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Título (ou parte dele) do evento a alterar"},
                    "new_day": {"type": "string", "description": "Novo dia ('hoje', 'amanhã' ou AAAA-MM-DD), opcional"},
                    "new_time": {"type": "string", "description": "Novo horário HH:MM (24h), opcional"},
                    "new_title": {"type": "string", "description": "Novo título, opcional"},
                    "day": {"type": "string", "description": "Opcional: 'hoje' ou 'amanhã', pra restringir a busca pelo evento original"},
                },
                "required": ["title"],
            },
        },
    },
]

_VALID_TOOLS = {t["function"]["name"] for t in TOOLS}


# ── Cache de intents (evita round-trip ao LLM para comandos repetidos) ─
# Reusa o _TTLCache genérico de core/providers.py (mesmo usado por clima,
# finanças e busca) em vez de reimplementar o controle de expiração aqui.

_CACHE_TTL = 300  # segundos
_intent_cache = None  # _TTLCache — inicializado lazy na 1ª chamada


def _get_intent_cache():
    global _intent_cache
    if _intent_cache is None:
        from core.providers import _TTLCache
        _intent_cache = _TTLCache(ttl=_CACHE_TTL)
    return _intent_cache


def _cache_get(command: str) -> Optional[list[dict]]:
    return _get_intent_cache().get(command.lower().strip())


def _cache_set(command: str, calls: list[dict]):
    if not calls:  # não cacheia falhas — permite nova tentativa
        return
    _get_intent_cache().set(command.lower().strip(), calls)


# ── Callback de confirmação (por canal: texto, voz, dashboard) ────────
# Assinatura: (action_name: str, detail: str) -> bool
# None = usa input() no terminal se estiver em TTY.
_confirmation_callback = None


def set_confirmation_callback(fn):
    """
    Registra uma função para solicitar confirmação via o canal ativo.
    Exemplo: overlay.ask_confirm, ou uma fila de resposta no módulo de voz.
    """
    global _confirmation_callback
    _confirmation_callback = fn


# ── Contexto de diálogo (últimas N intents para seguimento) ───────────

_dialog_ctx: deque[dict] = deque(maxlen=5)


def _update_dialog_ctx(command: str, calls: list[dict]):
    if calls:
        _dialog_ctx.append({
            "command": command,
            "intent": calls[0]["name"],
            "args": calls[0].get("arguments", {}),
        })


def _dialog_context_prompt() -> str:
    if not _dialog_ctx:
        return ""
    lines = [f'"{item["command"]}" → {item["intent"]}' for item in list(_dialog_ctx)[-3:]]
    return "Contexto recente (use para ambiguidades):\n" + "\n".join(lines)


# ── Few-shot examples para NLU local ──────────────────────────────────
# Passados como turnos user/assistant no /api/chat do Ollama.
# O modelo aprende por padrão, não por lógica — exemplos valem mais que descrições.

_FEW_SHOT: list[tuple[str, str]] = [
    # Música — play
    ('toca Linkin Park',
     '[{"name":"control_media","arguments":{"action":"play","query":"Linkin Park"}}]'),
    ('bota uma música do Eminem',
     '[{"name":"control_media","arguments":{"action":"play","query":"Eminem"}}]'),
    ('coloca Rap God do Eminem',
     '[{"name":"control_media","arguments":{"action":"play","query":"Rap God Eminem"}}]'),
    ('quero ouvir rock clássico',
     '[{"name":"control_media","arguments":{"action":"play","query":"rock clássico"}}]'),
    ('toca a playlist de trabalho',
     '[{"name":"control_media","arguments":{"action":"play","query":"trabalho"}}]'),
    ('play Coldplay',
     '[{"name":"control_media","arguments":{"action":"play","query":"Coldplay"}}]'),
    ('quero escutar Queen',
     '[{"name":"control_media","arguments":{"action":"play","query":"Queen"}}]'),
    ('escuta Daft Punk',
     '[{"name":"control_media","arguments":{"action":"play","query":"Daft Punk"}}]'),
    # Música — controle
    ('para a música',
     '[{"name":"control_media","arguments":{"action":"pause"}}]'),
    ('pausa',
     '[{"name":"control_media","arguments":{"action":"pause"}}]'),
    ('silencia o spotify',
     '[{"name":"control_media","arguments":{"action":"pause"}}]'),
    ('continua',
     '[{"name":"control_media","arguments":{"action":"resume"}}]'),
    ('retoma a música',
     '[{"name":"control_media","arguments":{"action":"resume"}}]'),
    ('próxima música',
     '[{"name":"control_media","arguments":{"action":"next"}}]'),
    ('próxima',
     '[{"name":"control_media","arguments":{"action":"next"}}]'),
    ('volta a música',
     '[{"name":"control_media","arguments":{"action":"previous"}}]'),
    ('música anterior',
     '[{"name":"control_media","arguments":{"action":"previous"}}]'),
    ('que música é essa',
     '[{"name":"control_media","arguments":{"action":"current"}}]'),
    ('o que está tocando',
     '[{"name":"control_media","arguments":{"action":"current"}}]'),
    # Apps
    ('abre o chrome',
     '[{"name":"open_application","arguments":{"name":"chrome"}}]'),
    ('abre o spotify',
     '[{"name":"open_application","arguments":{"name":"spotify"}}]'),
    ('abre o discord',
     '[{"name":"open_application","arguments":{"name":"discord"}}]'),
    ('fecha o discord',
     '[{"name":"close_application","arguments":{"name":"discord"}}]'),
    ('encerra o notepad',
     '[{"name":"close_application","arguments":{"name":"notepad"}}]'),
    ('encerre o chrome',
     '[{"name":"close_application","arguments":{"name":"chrome"}}]'),
    ('mata o processo discord',
     '[{"name":"close_application","arguments":{"name":"discord"}}]'),
    # Volume
    ('volume 60',
     '[{"name":"set_volume","arguments":{"level":60}}]'),
    ('aumenta o volume para 80',
     '[{"name":"set_volume","arguments":{"level":80}}]'),
    ('coloca o volume em 30',
     '[{"name":"set_volume","arguments":{"level":30}}]'),
    # Browser
    ('abre o youtube no chrome',
     '[{"name":"open_browser","arguments":{"browser":"chrome","destination":"youtube"}}]'),
    ('pesquisa python no firefox',
     '[{"name":"open_browser","arguments":{"browser":"firefox","destination":"python"}}]'),
    # Pastas
    ('abre a pasta de downloads',
     '[{"name":"open_folder","arguments":{"path":"downloads"}}]'),
    ('abre meus documentos',
     '[{"name":"open_folder","arguments":{"path":"documentos"}}]'),
    ('abre o desktop',
     '[{"name":"open_folder","arguments":{"path":"desktop"}}]'),
    # Apps multi-word
    ('abre o gerenciador de tarefas',
     '[{"name":"open_application","arguments":{"name":"gerenciador de tarefas"}}]'),
    ('abre o bloco de notas',
     '[{"name":"open_application","arguments":{"name":"bloco de notas"}}]'),
    # Busca web
    ('pesquisa sobre machine learning',
     '[{"name":"web_search","arguments":{"query":"machine learning"}}]'),
    ('busca notícias de tecnologia',
     '[{"name":"web_search","arguments":{"query":"notícias tecnologia"}}]'),
    # Git
    ('git status',
     '[{"name":"git_operation","arguments":{"operation":"status"}}]'),
    ('o que mudou no repositório',
     '[{"name":"git_operation","arguments":{"operation":"status"}}]'),
    ('git push',
     '[{"name":"git_operation","arguments":{"operation":"push"}}]'),
    ('faz commit com a mensagem atualiza readme',
     '[{"name":"git_operation","arguments":{"operation":"commit","message":"atualiza readme"}}]'),
    ('cria branch feature/login',
     '[{"name":"git_operation","arguments":{"operation":"branch","branch_name":"feature/login"}}]'),
    # Perguntas gerais
    ('o que é machine learning',
     '[{"name":"answer_question","arguments":{"question":"o que é machine learning"}}]'),
    ('me explica como funciona o docker',
     '[{"name":"answer_question","arguments":{"question":"como funciona o docker"}}]'),
    # WhatsApp
    ('pede pro fulano o que ele está fazendo no whatsapp',
     '[{"name":"send_whatsapp_message","arguments":{"contact":"fulano","message":"Oi! O que você está fazendo?"}}]'),
    ('manda mensagem pro joão perguntando se ele já almoçou',
     '[{"name":"send_whatsapp_message","arguments":{"contact":"joão","message":"Oi! Você já almoçou?"}}]'),
]

_NLU_SYSTEM = (
    "Você classifica comandos em ferramentas JSON. "
    "Responda SOMENTE com o array JSON, sem texto adicional, sem markdown.\n"
    "Ferramentas: " + ", ".join(_VALID_TOOLS)
)


# ── Camada 2: Classificador TF-IDF local ──────────────────────────────

_CONFIDENCE_THRESHOLD = 0.70  # abaixo disso → cai para LLM
_clf_state: dict = {}         # singleton lazy

# Ações que requerem confirmação mesmo vindas do NLU
_NEEDS_CONFIRM: set[tuple] = {
    ('close_application',),
    ('git_operation', 'push'),
    ('git_operation', 'commit'),
}


def _needs_confirmation(name: str, args: dict) -> bool:
    """
    Verifica se a ação requer confirmação.
    Combina a flag do ToolRegistry com a lista de operações específicas
    (ex: git push/commit são destrutivos mas git status não é).
    """
    try:
        from modules.tools import needs_confirmation as registry_needs_confirm
        if registry_needs_confirm(name):
            return True
    except Exception:
        pass
    # Operações git destrutivas (push/commit) requerem confirmação mesmo sem flag no registry
    operation = args.get('operation')
    return (name, operation) in _NEEDS_CONFIRM


def _confirm_action(name: str, args: dict) -> bool:
    """
    Pede confirmação para ações críticas.
    Prioridade de canal: callback registrado → TTY input() → bloqueia.
    """
    try:
        from core.config import Config
        if not Config().get("security.confirm_critical", True):
            return True
    except Exception:
        pass

    # Confiança aprendida: ações de risco MÉDIO já aprovadas N vezes seguidas
    # passam direto. Risco alto nunca é elegível (ver modules/trust.py).
    try:
        from modules import trust
        if trust.auto_approve(name):
            logger.info("Confirmação auto-aprovada por confiança aprendida: %s", name)
            return True
    except Exception:
        pass

    op     = args.get('operation') or args.get('action') or ''
    target = args.get('name') or args.get('message') or args.get('branch_name') or ''
    detail = f"{op} {target}".strip()

    decision: Optional[bool] = None

    # Canal 1: callback registrado (voz, dashboard, overlay)
    if _confirmation_callback is not None:
        try:
            decision = bool(_confirmation_callback(name, detail))
        except Exception as e:
            logger.warning("Callback de confirmação falhou: %s", e)
            return False
    # Canal 2: terminal interativo
    elif sys.stdin.isatty():
        try:
            resp = input(f"\n  [!] Confirmar: {name}({detail})? (s/N): ").strip().lower()
            decision = (resp == "s")
        except (EOFError, KeyboardInterrupt):
            return False

    if decision is not None:
        # Aprende com a decisão real do usuário (só ações elegíveis são contadas)
        try:
            from modules import trust
            trust.record(name, decision)
        except Exception:
            pass
        return decision

    # Canal 3: nenhum canal disponível → bloqueia por segurança
    logger.warning(
        "Ação crítica '%s(%s)' bloqueada: sem canal de confirmação disponível. "
        "Registre set_confirmation_callback() ou use modo texto.",
        name, detail,
    )
    return False


def _normalize_for_clf(text: str) -> str:
    """
    Remove valores de slot antes de vetorizar, mantendo só a estrutura do comando.
      'bota uma música do Eminem' → 'bota [QUERY]'
      'volume 60'                 → 'volume [NUM]'
      'abre o chrome'             → 'abre o [APP]'
      'pesquisa X no firefox'     → 'pesquisa [QUERY] no [BROWSER]'
      'pesquisa sobre X'          → 'pesquisa [QUERY]'

    Ordem importa: padrões específicos antes dos genéricos.
    """
    t = text.lower().strip()

    # 1. Números
    t = re.sub(r'\b\d+(?:[.,]\d+)?\b', '[NUM]', t)

    # 2. Volume/som: detecta ANTES do padrão de play
    if re.search(r'\b(volume|som)\b', t):
        t = re.sub(r'\b(volume|som)\s+.+', r'volume [NUM]', t)
        return t

    # 3. Navegador: mantém token [BROWSER] para distinguir open_browser de web_search
    t = re.sub(r'\bno\s+(chrome|firefox|brave|edge)\b', 'no [BROWSER]', t)

    # 4. Verbo de play + conteúdo → [QUERY]  (só se não há "volume" — já tratado acima)
    t = re.sub(
        r'^(bota[r]?|coloca[r]?|toca[r]?|play|quero\s+(?:ouvir|escutar)|escuta[r]?)'
        r'(?:\s+(?:uma?\s+)?(?:m[úu]sica|faixa|playlist|artista|banda))?'
        r'(?:\s+(?:do|da|de))?\s*.+$',
        r'\1 [QUERY]', t, flags=re.I,
    )

    # 5a. Pasta conhecida → [FOLDER] (antes de [APP] para o classificador distinguir open_folder)
    _FOLDER_KW = r'(downloads?|documentos?|desktop|imagens?|m[úu]sicas?|v[íi]deos?|[aá]rea\s+de\s+trabalho)'
    if re.search(_FOLDER_KW, t):
        t = re.sub(r'\b(abre[a]?|abrir|pasta)\s+.+', r'\1 [FOLDER]', t)
        return t

    # 5b. App name após "abre/fecha/encerra/encerre o/a" — captura também multi-word apps
    #     mas para antes de "no [BROWSER]" para não engolir padrão open_browser
    t = re.sub(r'\b(abre[a]?|fecha[r]?|encerr[ae][r]?|mata[r]?(?:\s+o\s+processo)?)\s+(o|a)\s+(?!.*\[BROWSER\]).+', r'\1 \2 [APP]', t)

    # 6. Pesquisa/busca (depois de tratar [BROWSER])
    t = re.sub(r'^(pesquisa[r]?|busca[r]?(?:\s+por)?)\s+(?:sobre\s+)?.+?(\s+no\s+\[BROWSER\])?$',
               lambda m: f'{m.group(1)} [QUERY]{m.group(2) or ""}', t)

    # 7. "do/da/de X" no final → slot de artista/destino
    t = re.sub(r'\b(do|da|de|pelo|pela|por)\s+\S+(?:\s+\S+)?$', r'\1 [SLOT]', t)

    # 8. Git — branch e mensagem
    t = re.sub(r'\b(branch|ramo)\s+\S+', r'\1 [SLOT]', t)
    t = re.sub(r'mensagem\s+.+', 'mensagem [SLOT]', t)

    # 9. Perguntas abertas
    t = re.sub(r'^(o\s+que\s+[ée]|me\s+explica|como\s+funciona[m]?|explica)\s+.+', r'\1 [SLOT]', t)

    return t


def _build_classifier() -> None:
    """Treina o vetorizador TF-IDF nos _FEW_SHOT (lazy, uma vez por processo)."""
    if 'vectorizer' in _clf_state or 'unavailable' in _clf_state:
        return
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        texts, labels = [], []
        for user_text, assistant_json in _FEW_SHOT:
            try:
                calls = json.loads(assistant_json)
                if calls:
                    texts.append(_normalize_for_clf(user_text))
                    labels.append((calls[0]['name'], calls[0].get('arguments', {})))
            except Exception:
                continue

        vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4), min_df=1)
        X = vec.fit_transform(texts)

        _clf_state['vectorizer'] = vec
        _clf_state['X'] = X
        _clf_state['labels'] = labels
        logger.debug("Classificador NLU treinado: %d exemplos", len(texts))

    except ImportError:
        _clf_state['unavailable'] = True
        logger.warning("scikit-learn não instalado — camada 2 desabilitada.")


def _parse_with_classifier(command: str) -> tuple[list[dict], float]:
    """
    Classifica o comando via similaridade de cosseno TF-IDF (<5ms).
    Retorna (tool_calls, confidence). Retorna ([], 0.0) se indisponível ou
    confiança abaixo do limiar.
    """
    _build_classifier()
    if _clf_state.get('unavailable'):
        return [], 0.0

    try:
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        norm = _normalize_for_clf(command)
        X_q = _clf_state['vectorizer'].transform([norm])
        sims = cosine_similarity(X_q, _clf_state['X'])[0]
        best_idx = int(np.argmax(sims))
        confidence = float(sims[best_idx])

        if confidence < _CONFIDENCE_THRESHOLD:
            logger.debug("Classificador baixa confiança (%.2f) para %r", confidence, command)
            return [], confidence

        intent_name, _ = _clf_state['labels'][best_idx]
        slots = _extract_slots(command, intent_name)
        logger.debug("Classificador (conf=%.2f): %s %s", confidence, intent_name, slots)
        return [{'name': intent_name, 'arguments': slots}], confidence

    except Exception as e:
        logger.warning("Erro no classificador NLU: %s", e)
        return [], 0.0


def _extract_slots(command: str, intent: str) -> dict:
    """Extrai valores de slot do texto original, sabendo o intent."""
    cmd_lower = command.lower().strip()

    if intent == 'control_media':
        if re.search(r'\b(pausa|silencia|para\s+(?:a\s+)?m[úu]sica|para\s+o\s+spotify)\b', cmd_lower):
            return {'action': 'pause'}
        if re.search(r'\b(continua|retoma|resume)\b', cmd_lower):
            return {'action': 'resume'}
        if re.search(r'\b(pr[oó]xima|pula|avan[çc]a)\b', cmd_lower):
            return {'action': 'next'}
        if re.search(r'\b(anterior|volta)\b', cmd_lower):
            return {'action': 'previous'}
        if re.search(r'\b(que\s+m[úu]sica|que\s+artista|tocando|est[aá]\s+tocando)\b', cmd_lower):
            return {'action': 'current'}
        # play: remove o prefixo verbal e retorna a query limpa
        query = re.sub(
            r'^(?:bota[r]?|coloca[r]?|toca[r]?|play|quero\s+(?:ouvir|escutar)|escuta[r]?)\s+',
            '', command, flags=re.I,
        ).strip()
        query = re.sub(
            r'^(?:uma?\s+)?(?:m[úu]sica|faixa|playlist|artista|banda)\s+(?:do|da|de)?\s*',
            '', query, flags=re.I,
        ).strip()
        return {'action': 'play', 'query': query}

    if intent == 'open_application':
        m = re.search(r'(?:abre[a]?|abrir)\s+(?:o\s+|a\s+)?(.+)', cmd_lower)
        if m:
            return {'name': m.group(1).strip()}
        return {'name': command}

    if intent == 'close_application':
        m = re.search(
            r'(?:fecha[r]?|encerr[ae][r]?|mata[r]?(?:\s+o\s+processo)?)\s+(?:o\s+|a\s+)?(.+)',
            cmd_lower,
        )
        return {'name': m.group(1).strip() if m else command}

    if intent == 'set_volume':
        m = re.search(r'\b(\d+)\b', cmd_lower)
        base = int(m.group(1)) if m else 50
        if 'aumenta' in cmd_lower or 'sobe' in cmd_lower:
            return {'level': min(100, base + 20) if m else 75}
        if 'diminui' in cmd_lower or 'baixa' in cmd_lower:
            return {'level': max(0, base - 20) if m else 30}
        return {'level': base}

    if intent == 'open_folder':
        # "abre o desktop" / "abre o X" onde X é nome de pasta conhecida
        known_folders = {'desktop', 'downloads', 'documentos', 'imagens', 'músicas', 'videos', 'área de trabalho'}
        m = re.search(r'(?:pasta\s+(?:de\s+)?|meus?\s+)(.+)', cmd_lower)
        if m:
            return {'path': m.group(1).strip()}
        m2 = re.search(r'(?:abre[a]?|abrir)\s+(?:o\s+|a\s+)?(.+)', cmd_lower)
        if m2:
            candidate = m2.group(1).strip()
            if candidate in known_folders:
                return {'path': candidate}
        return {'path': cmd_lower}

    if intent == 'open_browser':
        browser_m = re.search(r'\b(chrome|firefox|brave|edge)\b', cmd_lower)
        browser = browser_m.group(1) if browser_m else 'chrome'
        # Remove o nome do browser e "no/em/na" do final para extrair destino limpo
        dest = re.sub(r'\s+(?:no|em|na)\s+(?:chrome|firefox|brave|edge)\b.*$', '', cmd_lower, flags=re.I).strip()
        dest = re.sub(r'^(?:pesquisa[r]?|busca[r]?|abre[a]?|abrir)\s+(?:o\s+|a\s+)?(?:site\s+)?', '', dest, flags=re.I).strip()
        return {'browser': browser, 'destination': dest or 'google'}

    if intent == 'web_search':
        m = re.search(r'(?:pesquisa[r]?|busca[r]?(?:\s+por)?)\s+(?:sobre\s+)?(.+)', cmd_lower)
        return {'query': m.group(1).strip() if m else command}

    if intent == 'answer_question':
        m = re.search(r'(?:o\s+que\s+[ée]|me\s+explica|como\s+funciona[m]?|explica)\s+(.+)', cmd_lower)
        return {'question': m.group(1).strip() if m else command}

    if intent == 'git_operation':
        if re.search(r'\b(status|mudou|alterou)\b', cmd_lower):
            return {'operation': 'status'}
        if 'push' in cmd_lower:
            return {'operation': 'push'}
        if 'pull' in cmd_lower:
            return {'operation': 'pull'}
        if 'commit' in cmd_lower:
            m = re.search(r'mensagem\s+(.+)', cmd_lower)
            return {'operation': 'commit', 'message': m.group(1).strip() if m else 'update'}
        if re.search(r'\b(log|hist[oó]rico)\b', cmd_lower) and 'login' not in cmd_lower:
            return {'operation': 'log'}
        if re.search(r'\b(branch|ramo)\b', cmd_lower):
            m = re.search(r'(?:branch|ramo)\s+(\S+)', cmd_lower)
            return {'operation': 'branch', 'branch_name': m.group(1) if m else ''}
        return {'operation': 'status'}

    return {}


# ── Parser principal ───────────────────────────────────────────────────

def classify_local(command: str) -> list[dict]:
    """
    Roda apenas cache + TF-IDF (sem LLM). Retorna lista de tool calls se
    a confiança estiver acima do limiar, lista vazia caso contrário.
    Chamado pelo orchestrator para verificar se o LLM é necessário.
    """
    cached = _cache_get(command)
    if cached is not None:
        return cached
    calls, _ = _parse_with_classifier(command)
    if calls:
        calls = _validate(calls)
        _cache_set(command, calls)
        _update_dialog_ctx(command, calls)
    return calls


def parse_intent(command: str) -> list[dict]:
    """
    Pipeline de NLU em 3 camadas:
      1. Cache TTL         — retorno imediato se comando já foi visto
      2. Classificador     — TF-IDF local <5ms para intents com alta confiança
      3. LLM fallback      — Groq/Ollama para perguntas abertas e casos ambíguos
    """
    # Camada 0: cache
    cached = _cache_get(command)
    if cached is not None:
        logger.debug("Cache hit: %r", command)
        return cached

    # Camada 2: classificador TF-IDF local
    calls, confidence = _parse_with_classifier(command)
    if calls:
        calls = _validate(calls)
        _cache_set(command, calls)
        _update_dialog_ctx(command, calls)
        return calls

    # Camada 3: LLM (Groq function calling ou Ollama few-shot)
    try:
        from core.config import Config
        config = Config()
        provider = config.get("ai.provider", "ollama")

        if provider == "groq":
            calls = _parse_with_groq(command, config)
        else:
            calls = _parse_with_ollama_nlu(command, config)

        calls = _validate(calls)
        _cache_set(command, calls)
        _update_dialog_ctx(command, calls)
        return calls

    except Exception as e:
        from core.providers import _is_tool_use_failed
        if _is_tool_use_failed(e):
            logger.warning("tool_use_failed — fallback para IA")
            return []
        resp_obj = getattr(e, "response", None)
        body = getattr(resp_obj, "text", "") or ""
        logger.warning("Intent parse falhou (%s) %s", e, body[:200] if body else "")
        return []


def parse_intent_ollama(command: str) -> list[dict]:
    """
    Força o pipeline Ollama independente do ai.provider configurado.
    Usado pelo orchestrator como fallback real quando Groq falha,
    evitando que parse_intent() chame Groq novamente.
    """
    cached = _cache_get(command)
    if cached is not None:
        return cached
    calls, _ = _parse_with_classifier(command)
    if calls:
        calls = _validate(calls)
        _cache_set(command, calls)
        _update_dialog_ctx(command, calls)
        return calls
    try:
        from core.config import Config
        config = Config()
        calls = _parse_with_ollama_nlu(command, config)
        calls = _validate(calls)
        _cache_set(command, calls)
        _update_dialog_ctx(command, calls)
        return calls
    except Exception as e:
        logger.warning("parse_intent_ollama falhou: %s", e)
        return []


# ── Groq: loop agentivo completo ──────────────────────────────────────

_MAX_AGENTIC_TURNS = 4  # proteção contra loop infinito
_TOOL_CALL_RETRY_ATTEMPTS = 3  # "tool_use_failed" é falha de amostragem do
# modelo, não indisponibilidade real do Groq — repetir o mesmo request
# costuma resolver em poucas tentativas (medido empiricamente)


def _groq_messages_base(command: str, config) -> tuple[str, str, list[dict]]:
    """
    Monta api_key, model e lista de messages iniciais para o Groq.
    api_key e model são retornados para compatibilidade, mas o envio
    real agora é feito via core.providers._groq_call().
    """
    from core.providers import _resolve_key
    api_key = _resolve_key("ai.groq_api_key", "GROQ_API_KEY", config)
    model = os.environ.get("GROQ_MODEL") or config.get("ai.groq_model", "llama-3.3-70b-versatile")

    safe_cmd = command.encode("utf-8", errors="ignore").decode("utf-8").strip()

    kb_ctx = _build_kb_context(safe_cmd)
    dialog_ctx = _dialog_context_prompt()
    today_str = datetime.now().strftime("%Y-%m-%d (%A)")

    system_parts = [
        "You are Paçoca, a helpful personal desktop assistant. "
        "Reply in the same language the user used. "
        "Use the provided tools to execute requests. "
        "After executing a tool, produce a natural, concise response in the user's language. "
        "IMPORTANT: ground your response strictly in the actual tool result content. "
        "If a tool result indicates an error or failure (e.g., starts with 'Erro', "
        "mentions a missing dependency/credential/configuration, or otherwise did not "
        "complete the request), you MUST tell the user it failed and why — never claim "
        "an action succeeded ('marcado', 'feito', 'concluído', etc.) when the tool "
        "result says it did not. "
        f"Today's date is {today_str}. For any tool parameter expecting a relative day "
        "(e.g. calendar 'day' field), compute and pass an exact AAAA-MM-DD date for "
        "anything other than literally 'today'/'tomorrow' — never pass ambiguous phrases "
        "like 'depois de amanhã' or weekday names as-is, they will not be understood."
    ]
    if dialog_ctx:
        system_parts.append(dialog_ctx)
    if kb_ctx:
        system_parts.append(kb_ctx)

    messages: list[dict] = [{"role": "system", "content": "\n\n".join(system_parts)}]
    try:
        from storage.context import get_turns
        for user_turn, assistant_turn in get_turns()[-3:]:
            messages.append({"role": "user",      "content": user_turn})
            messages.append({"role": "assistant", "content": assistant_turn})
    except Exception:
        pass
    messages.append({"role": "user", "content": safe_cmd})

    return api_key, model, messages


def _groq_call(api_key: str, model: str, messages: list[dict], tool_choice="auto") -> dict:
    """Chama a API Groq via cliente central e retorna o JSON parsed da resposta."""
    from core.providers import get_client
    from core.config import Config
    client = get_client(Config())
    return client.chat_raw(
        messages,
        tools=TOOLS,
        tool_choice=tool_choice,
        max_tokens=512,
    )


def _parse_with_groq(command: str, config) -> list[dict]:
    """
    Classifica o comando via Groq — retorna lista de tool calls para o pipeline
    de classificação (parse_intent). Não executa, não produz resposta final.
    """
    api_key, model, messages = _groq_messages_base(command, config)
    data = _groq_call(api_key, model, messages)

    tool_calls = data["choices"][0]["message"].get("tool_calls") or []
    logger.debug("Groq NLU: %d tool(s) → %s",
                 len(tool_calls), [tc.get("function", {}).get("name") for tc in tool_calls])

    result = []
    for tc in tool_calls:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except Exception:
            args = {}
        result.append({"name": fn.get("name", ""), "arguments": args})

    return result


def _defer_tool_calls_to_dashboard(tool_calls: list[dict], command: str) -> str:
    """Cria um plano pendente para aprovação no dashboard, sem executar ferramentas."""
    try:
        from modules import task_store
        from modules.task_agent import plan_from_tool_calls
        steps = plan_from_tool_calls(tool_calls)
        task = task_store.create([
            {
                "tool": step.tool,
                "args": step.args,
                "description": step.description,
                "verify_contains": step.verify_contains,
            }
            for step in steps
        ])
        try:
            from web.app import push_event
            push_event("task_created", f"Plano criado pelo agente: {task['id']}")
        except Exception:
            pass
        return (
            f"Preparei o plano {task['id']} com {len(steps)} etapa(s), mas ainda não executei nada. "
            "Revise e aprove o plano no dashboard do Paçoca."
        )
    except Exception as exc:
        logger.error("Não foi possível criar plano pendente: %s", exc)
        return f"Não consegui preparar o plano para aprovação: {exc}"


def run_agentic_loop(command: str) -> str:
    """
    Loop agentivo completo com Groq:
      1. LLM seleciona ferramenta(s)
      2. Python executa cada ferramenta
      3. Resultados voltam ao LLM como tool messages
      4. LLM produz resposta final em linguagem natural
    Repete até _MAX_AGENTIC_TURNS ou até o LLM parar de chamar ferramentas.
    Retorna a resposta final em texto.
    """
    try:
        from core.config import Config
        config = Config()
    except Exception:
        return ""

    # Loop agentivo é exclusivo do Groq (provider=groq ou auto)
    if config.get("ai.provider", "groq") not in ("groq", "auto"):
        return ""

    from core.providers import _resolve_key, _circuit_is_open
    api_key = _resolve_key("ai.groq_api_key", "GROQ_API_KEY", config)
    if not api_key:
        logger.warning("run_agentic_loop: GROQ_API_KEY não configurado — loop agentivo desabilitado")
        return ""
    if _circuit_is_open():
        logger.info("run_agentic_loop: circuit breaker aberto — pulando Groq")
        return ""

    api_key, model, messages = _groq_messages_base(command, config)
    from core.providers import _is_tool_use_failed
    any_tool_executed = False
    executed_calls: list[dict] = []  # p/ o cache semântico aprender (frase → ferramenta)

    for turn in range(_MAX_AGENTIC_TURNS):
        data = None
        last_exc: Exception | None = None
        for attempt in range(_TOOL_CALL_RETRY_ATTEMPTS):
            try:
                data = _groq_call(api_key, model, messages)
                break
            except Exception as e:
                last_exc = e
                if not _is_tool_use_failed(e):
                    break  # erro real (rede, 401, etc.) — retry não ajuda
                logger.debug(
                    "run_agentic_loop: tool_use_failed (tentativa %d/%d) — retentando",
                    attempt + 1, _TOOL_CALL_RETRY_ATTEMPTS,
                )
        if data is None:
            # _groq_raw() já registrou a falha real no circuit breaker (se não
            # foi tool_use_failed) — não duplicar
            logger.warning("run_agentic_loop: chamada Groq falhou (turn %d): %s", turn, last_exc)
            break

        choice = data["choices"][0]
        msg    = choice["message"]
        finish = choice.get("finish_reason", "")

        # Nenhuma ferramenta chamada → resposta final em texto
        if finish != "tool_calls" or not msg.get("tool_calls"):
            final = (msg.get("content") or "").strip()
            logger.debug("run_agentic_loop: resposta final após %d turn(s)", turn + 1)
            _remember_semantic(command, executed_calls)
            return final

        # Modo supervisionado: o primeiro conjunto de ações vira um plano
        # pendente no dashboard, sem executar ferramentas diretamente.
        if bool(config.get("agent.require_plan_approval", False)):
            return _defer_tool_calls_to_dashboard(msg["tool_calls"], command)

        # Adiciona a mensagem do assistente (com as tool_calls) ao histórico
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": msg["tool_calls"]})

        # Executa cada ferramenta e adiciona resultado como tool message
        for tc in msg["tool_calls"]:
            fn   = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except Exception:
                args = {}
                logger.warning("run_agentic_loop: JSON inválido em '%s' — args zerados; abortando execução", name)
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                 "content": f"Erro: argumentos inválidos para '{name}'. Ação não executada."})
                continue

            # Valida args obrigatórios antes de executar (evita close_app(""))
            arg_error = _check_required_args(name, args)
            if arg_error:
                logger.warning("run_agentic_loop: %s", arg_error)
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                 "content": arg_error})
                continue

            # Confirmação para ações destrutivas
            if _needs_confirmation(name, args) and not _confirm_action(name, args):
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                 "content": f"Ação '{name}' cancelada pelo usuário."})
                continue

            tool_result = _execute_tool(name, args)
            any_tool_executed = True
            if not tool_result.startswith("Erro") and "não executada" not in tool_result:
                executed_calls.append({"name": name, "arguments": args})
            logger.debug("run_agentic_loop: %s(%s) → %r", name, args, tool_result[:80])

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.get("id", ""),
                "content":      tool_result,
            })

    # Se chegou ao limite de turns ou a chamada falhou sem nenhuma ferramenta
    # ter sido executada, pede resposta final sem ferramentas — mas avisa o
    # modelo para não fingir que completou algo que não foi feito.
    if not any_tool_executed:
        messages.append({
            "role": "system",
            "content": (
                "Nenhuma ação foi executada com sucesso até agora. "
                "Não afirme que algo foi feito/concluído. Se faltar informação "
                "para executar o pedido, peça-a ao usuário; caso contrário, "
                "explique que não foi possível completar a ação agora."
            ),
        })
    _remember_semantic(command, executed_calls)
    try:
        data = _groq_call(api_key, model, messages, tool_choice="none")
        return (data["choices"][0]["message"].get("content") or "").strip()
    except Exception:
        return ""


def _remember_semantic(command: str, calls: list[dict]) -> None:
    """Alimenta o cache semântico com o que o LLM acabou de resolver."""
    if not calls:
        return
    try:
        from modules import semantic_router
        semantic_router.remember(command, calls)
    except Exception:
        pass


# ── Ollama: NLU few-shot via /api/chat ────────────────────────────────

def _parse_with_ollama_nlu(command: str, config) -> list[dict]:
    """
    NLU local usando Ollama com few-shot como turnos user/assistant.
    Mais confiável que prompt único: o modelo aprende por padrão, não descrição.
    """
    import requests

    url = config.get("ai.ollama_url", "http://localhost:11434") + "/api/chat"
    model = config.get("ai.model", "llama3")

    # Monta mensagens: sistema + pares de few-shot + contexto de diálogo + comando
    messages: list[dict] = [{"role": "system", "content": _NLU_SYSTEM}]

    for user_ex, assistant_ex in _FEW_SHOT:
        messages.append({"role": "user", "content": user_ex})
        messages.append({"role": "assistant", "content": assistant_ex})

    # Injeta contexto de diálogo no último turno do usuário
    ctx = _dialog_context_prompt()
    user_content = f"{ctx}\n\nComando: {command}" if ctx else command
    messages.append({"role": "user", "content": user_content})

    try:
        resp = requests.post(
            url,
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": 128, "temperature": 0.0},
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "").strip()
        logger.debug("Ollama NLU raw: %r", raw[:200])
    except Exception as e:
        logger.warning("Ollama indisponível (%s) — intent retorna vazio", e)
        return []

    calls = _extract_json(raw)
    if calls is None:
        logger.warning("Ollama NLU: JSON inválido na resposta: %r", raw[:200])
        return []

    return calls


# ── Extração robusta de JSON ───────────────────────────────────────────

def _extract_json(raw: str) -> Optional[list[dict]]:
    """
    Tenta extrair uma lista de tool calls do texto do modelo.
    Usa 4 estratégias em cascata para lidar com variações de formatação.
    """
    # 1. Parse direto
    try:
        parsed = json.loads(raw.strip())
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "name" in parsed:
            return [parsed]
    except Exception:
        pass

    # 2. Bloco de código markdown (```json ... ```)
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if m:
        try:
            parsed = json.loads(m.group(1))
            return parsed if isinstance(parsed, list) else [parsed]
        except Exception:
            pass

    # 3. Primeiro array JSON na resposta
    m = re.search(r"\[[\s\S]*?\]", raw)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass

    # 4. Primeiro objeto JSON (tool call sem array)
    m = re.search(r"\{[\s\S]*?\}", raw)
    if m:
        try:
            obj = json.loads(m.group())
            if "name" in obj:
                return [obj]
        except Exception:
            pass

    return None


# ── Validação de tool calls ────────────────────────────────────────────

def _validate(calls: list[dict]) -> list[dict]:
    """Descarta calls com ferramenta desconhecida ou argumentos inválidos."""
    try:
        from modules.tools import known_tools
        valid_names = known_tools()
    except Exception:
        valid_names = _VALID_TOOLS
    valid = []
    for call in calls:
        name = call.get("name", "")
        if name not in valid_names:
            logger.warning("NLU gerou ferramenta desconhecida ignorada: %r", name)
            continue
        args = call.get("arguments", {})
        if not isinstance(args, dict):
            args = {}
        valid.append({"name": name, "arguments": args})
    return valid


# ── Contexto da knowledge base ─────────────────────────────────────────

def _build_kb_context(command: str) -> str:
    try:
        from storage.knowledge_base import build_context
        ctx = build_context(command)
        if ctx:
            return ctx
    except Exception:
        pass
    try:
        from modules.learner import get_personalized_context
        return get_personalized_context()
    except Exception:
        return ""


# ── Executor ──────────────────────────────────────────────────────────

def execute_actions(actions: list[dict]) -> list[str]:
    responses = []
    for act in actions:
        name = act.get("name", "")
        args = act.get("arguments", {})
        try:
            if _needs_confirmation(name, args) and not _confirm_action(name, args):
                responses.append("Ação cancelada.")
                continue
            result = _execute_tool(name, args)
            if result:
                responses.append(result)
        except Exception as e:
            logger.error("Erro ao executar '%s': %s", name, e)
            responses.append(f"Erro ao executar '{name}': {e}")
    return responses


def _check_required_args(name: str, args: dict) -> str:
    """
    Valida args via ToolRegistry (Pydantic).
    Retorna mensagem de erro ou string vazia se OK.
    """
    try:
        from modules.tools import validate
        _, err = validate(name, args)
        return err
    except Exception as e:
        return f"Erro de validação para '{name}': {e}"


def _execute_tool(name: str, args: dict) -> str:
    """
    Valida args via Pydantic e executa a ferramenta via ToolRegistry.
    Ponto único de execução — usado por run_agentic_loop e execute_actions.
    """
    try:
        from modules.tools import validate, execute
        validated, err = validate(name, args)
        if err:
            logger.warning("_execute_tool: %s", err)
            return err
        return execute(name, validated)
    except Exception as e:
        logger.error("_execute_tool '%s' falhou: %s", name, e, exc_info=True)
        return f"Erro ao executar '{name}': {e}"


