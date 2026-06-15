"""
modules/intent.py — Interpretação de comandos via function calling (Groq/Ollama)
O modelo decide quais ferramentas chamar — sem schema fixo de ações.
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

# ── Definição das ferramentas disponíveis ─────────────────────────────
# O modelo lê as descrições e decide o que chamar — não precisa de exemplos hardcoded.

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


# ── Parser principal ───────────────────────────────────────────────────

def parse_intent(command: str) -> list[dict]:
    """
    Envia o comando ao LLM com as ferramentas disponíveis.
    O modelo decide quais chamar e com quais parâmetros.
    Retorna lista de {"name": str, "arguments": dict}.
    """
    try:
        import requests
        from core.config import Config
        config = Config()
        provider = config.get("ai.provider", "ollama")

        if provider == "groq":
            return _parse_with_groq(command, config)
        else:
            return _parse_with_ollama_json(command, config)

    except Exception as e:
        resp_obj = getattr(e, "response", None)
        body = getattr(resp_obj, "text", "") or ""
        # tool_use_failed: modelo gerou XML em vez de JSON — tenta sem ferramentas
        if "tool_use_failed" in body:
            logger.warning("tool_use_failed — retornando vazio para fallback IA")
            return []
        logger.warning("Intent parse falhou (%s) %s", e, body[:200] if body else "")
        return []


def _parse_with_groq(command: str, config) -> list[dict]:
    """Usa Groq function calling — chamada única, sem loop agentivo."""
    import requests

    api_key = config.get("ai.groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
    model = os.environ.get("GROQ_MODEL") or config.get("ai.groq_model", "llama-3.3-70b-versatile")

    safe_command = command.encode("utf-8", errors="ignore").decode("utf-8").strip()

    # Injeta contexto da knowledge base no prompt
    try:
        from storage.knowledge_base import build_context
        kb_ctx = build_context(safe_command)
    except Exception:
        kb_ctx = ""

    # Fallback: learner context (stats de uso)
    if not kb_ctx:
        try:
            from modules.learner import get_personalized_context
            kb_ctx = get_personalized_context()
        except Exception:
            kb_ctx = ""

    system_prompt = "You are a desktop assistant. Use the provided tools to execute user requests."
    if kb_ctx:
        system_prompt += f"\n\n{kb_ctx}"

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
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
    print(f"[Intent] {len(tool_calls)} tool(s): {[tc.get('function',{}).get('name') for tc in tool_calls]}")

    result = []
    for tc in tool_calls:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except Exception:
            args = {}
        result.append({"name": fn.get("name", ""), "arguments": args})

    return result


def _parse_with_ollama_json(command: str, config) -> list[dict]:
    """Fallback para Ollama: pede JSON com tool calls manualmente."""
    import requests

    tool_names = "\n".join(
        f"- {t['function']['name']}: {t['function']['description']}"
        for t in TOOLS
    )
    system = (
        "Você é Paçoca, assistente pessoal. "
        "Dado um comando, retorne SOMENTE um JSON com lista de tool calls.\n"
        f"Ferramentas disponíveis:\n{tool_names}\n\n"
        'Formato: [{"name": "nome_da_ferramenta", "arguments": {...}}]\n'
        "Retorne apenas o JSON, sem explicações."
    )

    url = config.get("ai.ollama_url", "http://localhost:11434") + "/api/generate"
    model = config.get("ai.model", "llama3")

    resp = requests.post(
        url,
        json={
            "model": model,
            "system": system,
            "prompt": f'Comando: "{command}"',
            "stream": False,
            "options": {"num_predict": 256, "temperature": 0.1},
        },
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json().get("response", "").strip()

    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        calls = json.loads(match.group())
        # Normaliza para o mesmo formato do Groq
        return [{"name": c.get("name", ""), "arguments": c.get("arguments", {})} for c in calls]

    return []


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
    if op == "status":   return dev_tools.git_status()
    if op == "log":      return dev_tools.git_log()
    if op == "push":     return dev_tools.git_push()
    if op == "pull":     return dev_tools.git_pull()
    if op == "commit":   return dev_tools.git_commit(args.get("message", "update"))
    if op == "branch":   return dev_tools.git_create_branch(args.get("branch_name", ""))
    return "Operação git desconhecida."
