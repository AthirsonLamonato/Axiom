"""
modules/intent.py — NLU via LLM (Groq function calling / Ollama few-shot JSON)

Funciona como o sistema de Intents da Alexa:
  1. Classifica a intenção (qual ferramenta usar)
  2. Extrai slots (parâmetros: artista, app, volume…)
  3. Mantém contexto de diálogo para comandos de seguimento ("próxima", "para")
  4. Cache de TTL para comandos repetidos (evita round-trip ao LLM)
"""

import json
import logging
import os
import re
import time
from collections import deque
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
]

_VALID_TOOLS = {t["function"]["name"] for t in TOOLS}


# ── Cache de intents (evita round-trip ao LLM para comandos repetidos) ─

_intent_cache: dict[str, tuple[list[dict], float]] = {}
_CACHE_TTL = 300  # segundos


def _cache_get(command: str) -> Optional[list[dict]]:
    entry = _intent_cache.get(command.lower().strip())
    if entry:
        calls, ts = entry
        if time.time() - ts < _CACHE_TTL:
            return calls
    return None


def _cache_set(command: str, calls: list[dict]):
    _intent_cache[command.lower().strip()] = (calls, time.time())


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
]

_NLU_SYSTEM = (
    "Você classifica comandos em ferramentas JSON. "
    "Responda SOMENTE com o array JSON, sem texto adicional, sem markdown.\n"
    "Ferramentas: " + ", ".join(_VALID_TOOLS)
)


# ── Parser principal ───────────────────────────────────────────────────

def parse_intent(command: str) -> list[dict]:
    """
    Retorna lista de {"name": str, "arguments": dict} prontos para execução.
    Fluxo: cache → NLU local (Ollama) ou Groq → validação → atualiza contexto.
    """
    cached = _cache_get(command)
    if cached is not None:
        logger.debug("Intent cache hit: %r", command)
        return cached

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
        resp_obj = getattr(e, "response", None)
        body = getattr(resp_obj, "text", "") or ""
        if "tool_use_failed" in body:
            logger.warning("tool_use_failed — fallback para IA")
            return []
        logger.warning("Intent parse falhou (%s) %s", e, body[:200] if body else "")
        return []


# ── Groq: function calling nativo ─────────────────────────────────────

def _parse_with_groq(command: str, config) -> list[dict]:
    """Usa Groq function calling — chamada única, sem loop agentivo."""
    import requests

    api_key = config.get("ai.groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
    model = os.environ.get("GROQ_MODEL") or config.get("ai.groq_model", "llama-3.3-70b-versatile")

    safe_command = command.encode("utf-8", errors="ignore").decode("utf-8").strip()

    kb_ctx = _build_kb_context(safe_command)
    dialog_ctx = _dialog_context_prompt()

    system_parts = ["You are Paçoca, a desktop assistant. Use the provided tools to execute user requests."]
    if dialog_ctx:
        system_parts.append(dialog_ctx)
    if kb_ctx:
        system_parts.append(kb_ctx)

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "\n\n".join(system_parts)},
                {"role": "user", "content": safe_command},
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
            "max_tokens": 512,
        },
        timeout=10,
    )
    resp.raise_for_status()

    tool_calls = resp.json()["choices"][0]["message"].get("tool_calls") or []
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
    valid = []
    for call in calls:
        name = call.get("name", "")
        if name not in _VALID_TOOLS:
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
    spotify_just_opened = False

    for act in actions:
        name = act.get("name", "")
        args = act.get("arguments", {})
        try:
            if name == "open_application" and args.get("name", "").lower() == "spotify":
                spotify_just_opened = True

            if name == "control_media":
                args = {**args, "_spotify_just_opened": spotify_just_opened}

            result = _execute(name, args)
            if result:
                responses.append(result)
        except Exception as e:
            logger.error("Erro ao executar '%s': %s", name, e)
            responses.append(f"Erro ao executar '{name}': {e}")
    return responses


def _execute(name: str, args: dict) -> str:
    from modules import system_control

    if name == "open_application":
        return system_control.open_app(args.get("name", ""))

    if name == "open_folder":
        return system_control.open_folder(args.get("path", ""))

    if name == "open_browser":
        return system_control.open_browser_with_search(
            args.get("browser", "chrome"), args.get("destination", "")
        )

    if name == "close_application":
        return system_control.close_app(args.get("name", ""))

    if name == "set_volume":
        return system_control.set_volume(str(args.get("level", 50)))

    if name == "web_search":
        from modules.search import search_web
        return search_web(args.get("query", ""))

    if name == "answer_question":
        from modules.summarizer import ask_ai
        return ask_ai(args.get("question", ""))

    if name == "git_operation":
        return _git(args)

    if name == "control_media":
        return _media(args)

    return f"Ferramenta desconhecida: {name}"


def _media(args: dict) -> str:
    from modules import spotify_ctrl
    action = args.get("action", "play")
    query = args.get("query", "")
    just_opened = args.get("_spotify_just_opened", False)
    if action == "play":
        return spotify_ctrl.play_search(query, spotify_just_opened=just_opened)
    if action == "pause":
        return spotify_ctrl.pause()
    if action == "resume":
        return spotify_ctrl.resume()
    if action == "next":
        return spotify_ctrl.next_track()
    if action == "previous":
        return spotify_ctrl.previous_track()
    if action == "current":
        return spotify_ctrl.current_track()
    return "Ação de mídia desconhecida."


def _git(args: dict) -> str:
    from modules import dev_tools
    op = args.get("operation", "status")
    if op == "status":  return dev_tools.git_status()
    if op == "log":     return dev_tools.git_log()
    if op == "push":    return dev_tools.git_push()
    if op == "pull":    return dev_tools.git_pull()
    if op == "commit":  return dev_tools.git_commit(args.get("message", "update"))
    if op == "branch":  return dev_tools.git_create_branch(args.get("branch_name", ""))
    return "Operação git desconhecida."
