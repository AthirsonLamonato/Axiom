"""
modules/tools.py — Registro central de ferramentas do Paçoca

Cada ferramenta declara em um único lugar:
  - Modelo Pydantic para validação de args em runtime
  - Função executora (lazy import — não quebra o boot)
  - Nível de risco (low | medium | high)
  - Se requer confirmação explícita do usuário

O orchestrator e o loop agentivo usam `validate()` e `execute()`
em vez de cadeias if/elif espalhadas pelo intent.py.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional, Type

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


# ── Modelos de argumentos (Pydantic v2) ───────────────────────────────

class OpenApplicationArgs(BaseModel):
    name: str = Field(..., min_length=1, description="Nome do app a abrir")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class CloseApplicationArgs(BaseModel):
    name: str = Field(..., min_length=1, description="Nome do processo a fechar")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class OpenBrowserArgs(BaseModel):
    browser: Literal["chrome", "firefox", "brave", "edge"] = "chrome"
    destination: str = Field(..., min_length=1, description="Site ou termo de busca")

    @field_validator("destination", mode="before")
    @classmethod
    def strip_dest(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class OpenFolderArgs(BaseModel):
    path: str = Field(..., min_length=1, description="Pasta a abrir")

    @field_validator("path", mode="before")
    @classmethod
    def strip_path(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class SetVolumeArgs(BaseModel):
    level: int = Field(..., ge=0, le=100, description="Volume 0-100")


class WebSearchArgs(BaseModel):
    query: str = Field(..., min_length=1, description="Termo de busca")

    @field_validator("query", mode="before")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class AnswerQuestionArgs(BaseModel):
    question: str = Field(..., min_length=1, description="Pergunta ou assunto")

    @field_validator("question", mode="before")
    @classmethod
    def strip_q(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class ControlMediaArgs(BaseModel):
    model_config = {"extra": "ignore"}  # ignora campos extras como _spotify_just_opened

    action: Literal["play", "pause", "resume", "next", "previous", "current"]
    query: Optional[str] = Field(None, description="Música/artista/playlist (só para action=play)")

    @field_validator("query", mode="before")
    @classmethod
    def strip_q(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def query_required_for_play(self) -> "ControlMediaArgs":
        if self.action == "play" and not self.query:
            raise ValueError("query é obrigatória quando action='play'")
        return self


class GitOperationArgs(BaseModel):
    operation: Literal["status", "log", "push", "pull", "commit", "branch"]
    message: Optional[str] = Field(None, description="Mensagem de commit")
    branch_name: Optional[str] = Field(None, description="Nome da branch")

    @model_validator(mode="after")
    def conditional_required(self) -> "GitOperationArgs":
        if self.operation == "commit" and not self.message:
            raise ValueError("message é obrigatória para operation='commit'")
        if self.operation == "branch" and not self.branch_name:
            raise ValueError("branch_name é obrigatório para operation='branch'")
        return self


class RememberArgs(BaseModel):
    statement: str = Field(..., min_length=1, description="Fato a memorizar")

    @field_validator("statement", mode="before")
    @classmethod
    def strip_s(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class ForgetArgs(BaseModel):
    topic: str = Field(..., min_length=1, description="Tópico a esquecer")

    @field_validator("topic", mode="before")
    @classmethod
    def strip_t(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class ListMemoriesArgs(BaseModel):
    filter: str = Field("", description="Filtro opcional: preferences | habits | projects | facts")


class GetCalendarEventsArgs(BaseModel):
    day: Literal["hoje", "amanhã"] = "hoje"


class GetNextCalendarEventArgs(BaseModel):
    pass


class CreateCalendarEventArgs(BaseModel):
    title: str = Field(..., min_length=1, description="Título/assunto do evento")
    day: str = Field("amanhã", description="'hoje', 'amanhã', ou data no formato AAAA-MM-DD")
    time: str = Field("09:00", description="Horário no formato HH:MM (24h)")
    attendees: list[str] = Field(default_factory=list, description="E-mails dos convidados (opcional)")

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("attendees", mode="before")
    @classmethod
    def normalize_attendees(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [e.strip() for e in v.split(",") if e.strip()]
        return v


class DeleteCalendarEventArgs(BaseModel):
    title: str = Field(..., min_length=1, description="Título (ou parte dele) do evento a apagar")
    day: str = Field("", description="Opcional: 'hoje' ou 'amanhã', pra restringir a busca")

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


# ── Executores (lazy imports) ─────────────────────────────────────────

def _exec_open_application(a: OpenApplicationArgs) -> str:
    from modules import system_control
    return system_control.open_app(a.name)


def _exec_close_application(a: CloseApplicationArgs) -> str:
    from modules import system_control
    return system_control.close_app(a.name)


def _exec_open_browser(a: OpenBrowserArgs) -> str:
    from modules import system_control
    return system_control.open_browser_with_search(a.browser, a.destination)


def _exec_open_folder(a: OpenFolderArgs) -> str:
    from modules import system_control
    return system_control.open_folder(a.path)


def _exec_set_volume(a: SetVolumeArgs) -> str:
    from modules import system_control
    return system_control.set_volume(str(a.level))


def _exec_web_search(a: WebSearchArgs) -> str:
    from modules.search import search_web
    return search_web(a.query)


def _exec_answer_question(a: AnswerQuestionArgs) -> str:
    from modules.summarizer import ask_ai
    return ask_ai(a.question)


def _exec_control_media(a: ControlMediaArgs) -> str:
    from modules import spotify_ctrl
    if a.action == "play":
        return spotify_ctrl.play_search(a.query or "")
    if a.action == "pause":
        return spotify_ctrl.pause()
    if a.action == "resume":
        return spotify_ctrl.resume()
    if a.action == "next":
        return spotify_ctrl.next_track()
    if a.action == "previous":
        return spotify_ctrl.previous_track()
    if a.action == "current":
        return spotify_ctrl.current_track()
    return "Ação de mídia desconhecida."


def _exec_git_operation(a: GitOperationArgs) -> str:
    from modules import dev_tools
    if a.operation == "status":  return dev_tools.git_status()
    if a.operation == "log":     return dev_tools.git_log()
    if a.operation == "push":    return dev_tools.git_push()
    if a.operation == "pull":    return dev_tools.git_pull()
    if a.operation == "commit":  return dev_tools.git_commit(a.message or "update")
    if a.operation == "branch":  return dev_tools.git_create_branch(a.branch_name or "")
    return "Operação git desconhecida."


def _exec_remember(a: RememberArgs) -> str:
    from storage.knowledge_base import remember
    return remember(a.statement)


def _exec_forget(a: ForgetArgs) -> str:
    from storage.knowledge_base import forget
    return forget(a.topic)


def _exec_list_memories(a: ListMemoriesArgs) -> str:
    from storage.knowledge_base import show_memories
    return show_memories(a.filter)


def _exec_get_calendar_events(a: GetCalendarEventsArgs) -> str:
    from modules import calendar_integration
    return calendar_integration.get_day_events(a.day)


def _exec_get_next_calendar_event(a: GetNextCalendarEventArgs) -> str:
    from modules import calendar_integration
    return calendar_integration.get_next_event()


def _exec_create_calendar_event(a: CreateCalendarEventArgs) -> str:
    from modules import calendar_integration
    return calendar_integration.create_event(a.title, a.day, a.time, a.attendees or None)


def _exec_delete_calendar_event(a: DeleteCalendarEventArgs) -> str:
    from modules import calendar_integration
    return calendar_integration.delete_event(a.title, a.day)


# ── Definição de ferramenta ───────────────────────────────────────────

@dataclass
class ToolDef:
    schema_model: Type[BaseModel]
    executor: Callable[[BaseModel], str]
    risk: Literal["low", "medium", "high"] = "low"
    requires_confirmation: bool = False


# ── Registro central ──────────────────────────────────────────────────

REGISTRY: dict[str, ToolDef] = {
    "open_application": ToolDef(
        schema_model=OpenApplicationArgs,
        executor=_exec_open_application,
        risk="low",
    ),
    "close_application": ToolDef(
        schema_model=CloseApplicationArgs,
        executor=_exec_close_application,
        risk="high",
        requires_confirmation=True,
    ),
    "open_browser": ToolDef(
        schema_model=OpenBrowserArgs,
        executor=_exec_open_browser,
        risk="low",
    ),
    "open_folder": ToolDef(
        schema_model=OpenFolderArgs,
        executor=_exec_open_folder,
        risk="low",
    ),
    "set_volume": ToolDef(
        schema_model=SetVolumeArgs,
        executor=_exec_set_volume,
        risk="low",
    ),
    "web_search": ToolDef(
        schema_model=WebSearchArgs,
        executor=_exec_web_search,
        risk="low",
    ),
    "answer_question": ToolDef(
        schema_model=AnswerQuestionArgs,
        executor=_exec_answer_question,
        risk="low",
    ),
    "control_media": ToolDef(
        schema_model=ControlMediaArgs,
        executor=_exec_control_media,
        risk="low",
    ),
    "git_operation": ToolDef(
        schema_model=GitOperationArgs,
        executor=_exec_git_operation,
        risk="medium",
        requires_confirmation=False,  # push/commit tratados por _needs_confirmation em intent.py
    ),
    "remember": ToolDef(
        schema_model=RememberArgs,
        executor=_exec_remember,
        risk="low",
    ),
    "forget": ToolDef(
        schema_model=ForgetArgs,
        executor=_exec_forget,
        risk="medium",
        requires_confirmation=True,
    ),
    "list_memories": ToolDef(
        schema_model=ListMemoriesArgs,
        executor=_exec_list_memories,
        risk="low",
    ),
    "get_calendar_events": ToolDef(
        schema_model=GetCalendarEventsArgs,
        executor=_exec_get_calendar_events,
        risk="low",
    ),
    "get_next_calendar_event": ToolDef(
        schema_model=GetNextCalendarEventArgs,
        executor=_exec_get_next_calendar_event,
        risk="low",
    ),
    "create_calendar_event": ToolDef(
        schema_model=CreateCalendarEventArgs,
        executor=_exec_create_calendar_event,
        risk="low",  # mesmo nível da rota direta de voz (add_event não exige confirmação)
    ),
    "delete_calendar_event": ToolDef(
        schema_model=DeleteCalendarEventArgs,
        executor=_exec_delete_calendar_event,
        risk="high",
        requires_confirmation=True,  # destrutivo e irreversível
    ),
}


# ── API pública ───────────────────────────────────────────────────────

def validate(name: str, raw_args: dict) -> tuple[Optional[BaseModel], str]:
    """
    Valida raw_args contra o schema Pydantic da ferramenta.
    Retorna (model_instance, "") em caso de sucesso.
    Retorna (None, mensagem_de_erro) em caso de falha.
    """
    tool = REGISTRY.get(name)
    if not tool:
        return None, f"Ferramenta desconhecida: '{name}'"
    try:
        model = tool.schema_model(**raw_args)
        return model, ""
    except Exception as e:
        # Pydantic v2 detalha os erros de campo
        details = "; ".join(
            f"{err['loc'][-1] if err.get('loc') else '?'}: {err['msg']}"
            for err in getattr(e, "errors", lambda: [])()
        ) if hasattr(e, "errors") else str(e)
        return None, f"Args inválidos para '{name}': {details}. Ação não executada."


def execute(name: str, validated: BaseModel) -> str:
    """Executa a ferramenta com args já validados."""
    tool = REGISTRY.get(name)
    if not tool:
        return f"Ferramenta desconhecida: '{name}'"
    return tool.executor(validated)


def needs_confirmation(name: str) -> bool:
    """Retorna True se a ferramenta requer confirmação explícita."""
    tool = REGISTRY.get(name)
    return bool(tool and tool.requires_confirmation)


def get_risk(name: str) -> str:
    """Retorna o nível de risco da ferramenta."""
    tool = REGISTRY.get(name)
    return tool.risk if tool else "unknown"


def known_tools() -> set[str]:
    """Conjunto de nomes de ferramentas registradas."""
    return set(REGISTRY.keys())
