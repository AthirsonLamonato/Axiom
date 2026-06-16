"""
modules/calendar_integration.py — Integração com Google Calendar
Requer: google-api-python-client, google-auth-oauthlib (já em requirements.txt)
Credenciais: coloque credentials.json em core/credentials.json e execute
  'paçoca, autoriza calendário' uma vez para gerar o token.
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
]
TOKEN_PATH = "core/google_token.json"
CREDS_PATH = "core/credentials.json"


def _get_config():
    from core.config import Config
    return Config()


def _get_service():
    """Autentica e retorna o serviço Google Calendar."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError("Instale: pip install google-api-python-client google-auth-oauthlib")

    config = _get_config()
    creds_path = config.get("calendar.credentials_path", CREDS_PATH)
    token_path = config.get("calendar.token_path", TOKEN_PATH)

    creds: Optional[Credentials] = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(
                    f"Arquivo de credenciais não encontrado: {creds_path}\n"
                    "Siga: console.cloud.google.com → Calendar API → credenciais OAuth → baixe credentials.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        try:
            import os as _os
            _os.chmod(token_path, 0o600)
        except Exception:
            pass
        logger.info("Token do Google Calendar salvo em %s", token_path)

    return build("calendar", "v3", credentials=creds)


def _format_event(event: dict) -> str:
    summary = event.get("summary", "(sem título)")
    start = event.get("start", {})
    dt_str = start.get("dateTime") or start.get("date", "")
    if "T" in dt_str:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        time_label = local_dt.strftime("%H:%M")
    else:
        time_label = "dia todo"
    location = event.get("location", "")
    loc_part = f" — {location}" if location else ""
    return f"{time_label}: {summary}{loc_part}"


def _calendar_timezone():
    timezone_name = _get_config().get("calendar.timezone", "America/Sao_Paulo")
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning("Fuso do calendário inválido: %s", timezone_name)
        return datetime.now().astimezone().tzinfo


# ── Comandos públicos ──────────────────────────────────────────────────

def get_day_events(day: str = "hoje", *_) -> str:
    """Lista eventos de hoje ou amanhã no fuso configurado."""
    try:
        service = _get_service()
    except (FileNotFoundError, RuntimeError) as e:
        return str(e)
    except Exception as e:
        logger.error("Erro ao conectar Calendar: %s", e, exc_info=True)
        return f"Erro ao conectar com o Google Calendar: {e}"

    tz = _calendar_timezone()
    now = datetime.now(tz)
    normalized_day = day.strip().lower()
    offset = 1 if normalized_day in ("amanhã", "amanha") else 0
    target = now + timedelta(days=offset)
    start_of_day = target.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    try:
        result = service.events().list(
            calendarId="primary",
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=10,
        ).execute()
    except Exception as e:
        logger.error("Erro ao listar eventos: %s", e, exc_info=True)
        return f"Erro ao buscar eventos: {e}"

    events = result.get("items", [])
    day_label = "amanhã" if offset else "hoje"
    if not events:
        return f"Nenhum evento encontrado para {day_label}."

    lines = [f"Agenda de {day_label} ({target.strftime('%d/%m/%Y')}):"]
    for ev in events:
        lines.append(f"  • {_format_event(ev)}")
    return "\n".join(lines)


def get_today_events(*_) -> str:
    return get_day_events("hoje")


def get_next_event(*_) -> str:
    """Retorna o próximo evento agendado a partir de agora."""
    try:
        service = _get_service()
    except (FileNotFoundError, RuntimeError) as e:
        return str(e)
    except Exception as e:
        return f"Erro ao conectar com o Google Calendar: {e}"

    now = datetime.now(timezone.utc).isoformat()

    try:
        result = service.events().list(
            calendarId="primary",
            timeMin=now,
            singleEvents=True,
            orderBy="startTime",
            maxResults=1,
        ).execute()
    except Exception as e:
        return f"Erro ao buscar próximo evento: {e}"

    events = result.get("items", [])
    if not events:
        return "Nenhum evento futuro encontrado."

    ev = events[0]
    start = ev.get("start", {})
    dt_str = start.get("dateTime") or start.get("date", "")
    if "T" in dt_str:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone()
        delta = dt - datetime.now(dt.tzinfo)
        minutes = int(delta.total_seconds() / 60)
        if minutes < 60:
            when = f"em {minutes} minuto(s)"
        elif minutes < 1440:
            when = f"em {minutes // 60}h{minutes % 60:02d}"
        else:
            when = f"em {minutes // 1440} dia(s)"
        return f"Próximo evento: {ev.get('summary', '(sem título)')} — {dt.strftime('%d/%m %H:%M')} ({when})"
    else:
        return f"Próximo evento: {ev.get('summary', '(sem título)')} — {dt_str}"


EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b")


def _insert_event(
    title: str, start_dt: datetime, timezone_name: str, service,
    attendees: Optional[list[str]] = None,
) -> str:
    """Cria o evento na agenda primária. Helper compartilhado por add_event()
    (parsing por regex, rota direta de voz) e create_event() (args
    estruturados, usado pelo loop agentivo).
    attendees: lista de e-mails a convidar (opcional). Quando presente, o
    Google Calendar envia convite/notificação por e-mail a cada um."""
    end_dt = start_dt + timedelta(hours=1)
    clean_title = title.strip()
    # Só garante 1ª letra maiúscula — .capitalize() forçaria o resto pra
    # minúsculo, destruindo títulos como "[TESTE] Reunião com a Paçoca"
    summary = (clean_title[0].upper() + clean_title[1:]) if clean_title else ""
    event_body = {
        "summary": summary or "Evento",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": timezone_name},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": timezone_name},
    }
    if attendees:
        event_body["attendees"] = [{"email": e} for e in attendees]
    try:
        created = service.events().insert(
            calendarId="primary",
            body=event_body,
            sendUpdates="all" if attendees else "none",
        ).execute()
        suffix = f" — convidados: {', '.join(attendees)}" if attendees else ""
        return (
            f"Evento criado: '{created['summary']}' — "
            f"{start_dt.strftime('%d/%m %H:%M')} a {end_dt.strftime('%H:%M')}{suffix}"
        )
    except Exception as e:
        logger.error("Erro ao criar evento: %s", e, exc_info=True)
        return f"Erro ao criar evento: {e}"


def _resolve_day(day: str, now: datetime) -> datetime:
    day_norm = (day or "amanhã").strip().lower()
    if day_norm in ("amanhã", "amanha"):
        return now + timedelta(days=1)
    if day_norm == "hoje":
        return now
    try:
        return datetime.strptime(day_norm, "%Y-%m-%d")
    except ValueError:
        return now + timedelta(days=1)  # padrão quando não reconhece o formato


def add_event(raw: str, *_) -> str:
    """Adiciona um evento via linguagem natural (rota direta de voz/texto).
    Exemplos: 'reunião amanhã às 14h', 'dentista hoje às 10h30 sobre consulta'
    """
    try:
        service = _get_service()
    except (FileNotFoundError, RuntimeError) as e:
        return str(e)
    except Exception as e:
        return f"Erro ao conectar com o Google Calendar: {e}"

    raw = raw.strip()
    now = datetime.now()

    # E-mails mencionados no comando → convidados (ex: "reunião com x@y.com")
    attendees = EMAIL_RE.findall(raw)
    raw_sem_emails = EMAIL_RE.sub("", raw) if attendees else raw

    # Detectar dia
    if re.search(r"\bamanhã\b", raw_sem_emails, re.I):
        base_date = now + timedelta(days=1)
    elif re.search(r"\bhoje\b", raw_sem_emails, re.I):
        base_date = now
    else:
        base_date = now + timedelta(days=1)  # padrão: amanhã

    # Detectar horário
    hour_match = re.search(r"\bàs?\s+(\d{1,2})h(\d{2})?\b", raw_sem_emails, re.I)
    if not hour_match:
        hour_match = re.search(r"\b(\d{1,2}):(\d{2})\b", raw_sem_emails)
    if hour_match:
        hour = int(hour_match.group(1))
        minute = int(hour_match.group(2) or 0)
    else:
        hour, minute = 9, 0

    # Título: remove palavras-chave de data/hora
    title = re.sub(r"\b(amanhã|hoje|às?|sobre|com)\b", "", raw_sem_emails, flags=re.I)
    title = re.sub(r"\b\d{1,2}h\d{0,2}\b", "", title)
    title = re.sub(r"\b\d{1,2}:\d{2}\b", "", title)
    title = " ".join(title.split()) or "Evento"

    start_dt = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    timezone_name = _get_config().get("calendar.timezone", "America/Sao_Paulo")
    return _insert_event(title, start_dt, timezone_name, service, attendees=attendees or None)


def create_event(
    title: str, day: str = "amanhã", time: str = "09:00",
    attendees: Optional[list[str]] = None, *_,
) -> str:
    """Cria evento com campos estruturados — usado pelo loop agentivo (Groq),
    que já normaliza data/hora melhor do que o parser por regex de add_event().

    day:       'hoje' | 'amanhã' | data no formato AAAA-MM-DD
    time:      horário no formato HH:MM
    attendees: e-mails a convidar (opcional) — Google envia convite por e-mail
    """
    try:
        service = _get_service()
    except (FileNotFoundError, RuntimeError) as e:
        return str(e)
    except Exception as e:
        return f"Erro ao conectar com o Google Calendar: {e}"

    base_date = _resolve_day(day, datetime.now())
    try:
        hour, minute = (int(x) for x in (time or "09:00").strip().split(":"))
    except (ValueError, AttributeError):
        hour, minute = 9, 0

    start_dt = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    timezone_name = _get_config().get("calendar.timezone", "America/Sao_Paulo")
    return _insert_event(title or "Evento", start_dt, timezone_name, service, attendees=attendees)


def delete_event(title: str, day: str = "", *_) -> str:
    """Apaga um evento pelo título (busca por trecho, sem diferenciar
    maiúsculas/minúsculas). 'day' (hoje/amanhã, opcional) restringe a busca a
    um dia; sem 'day', busca nos próximos 60 dias. Nunca apaga se houver mais
    de um evento correspondente — lista as opções e pede para ser específico."""
    if not title or not title.strip():
        return "Preciso do título (ou parte dele) do evento a apagar."

    try:
        service = _get_service()
    except (FileNotFoundError, RuntimeError) as e:
        return str(e)
    except Exception as e:
        return f"Erro ao conectar com o Google Calendar: {e}"

    tz = _calendar_timezone()
    now = datetime.now(tz)
    day_norm = day.strip().lower()
    if day_norm in ("hoje", "amanhã", "amanha"):
        offset = 1 if day_norm in ("amanhã", "amanha") else 0
        target = now + timedelta(days=offset)
        time_min = target.replace(hour=0, minute=0, second=0, microsecond=0)
        time_max = time_min + timedelta(days=1)
    else:
        time_min = now - timedelta(days=1)
        time_max = now + timedelta(days=60)

    try:
        result = service.events().list(
            calendarId="primary",
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        ).execute()
    except Exception as e:
        logger.error("Erro ao buscar eventos para apagar: %s", e, exc_info=True)
        return f"Erro ao buscar eventos: {e}"

    needle = title.strip().lower()
    matches = [ev for ev in result.get("items", []) if needle in ev.get("summary", "").lower()]

    if not matches:
        return f"Não encontrei nenhum evento com '{title}' no período buscado."
    if len(matches) > 1:
        lines = [f"Encontrei {len(matches)} eventos com '{title}' — seja mais específico:"]
        lines += [f"  • {_format_event(ev)}" for ev in matches]
        return "\n".join(lines)

    ev = matches[0]
    try:
        service.events().delete(
            calendarId="primary",
            eventId=ev["id"],
            sendUpdates="all" if ev.get("attendees") else "none",
        ).execute()
        return f"Evento '{ev.get('summary', '(sem título)')}' apagado."
    except Exception as e:
        logger.error("Erro ao apagar evento: %s", e, exc_info=True)
        return f"Erro ao apagar evento: {e}"


def auth_calendar(*_) -> str:
    """Abre o fluxo OAuth para autorizar o Google Calendar."""
    try:
        _get_service()
        return "Google Calendar autorizado com sucesso."
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Erro na autorização: {e}"
