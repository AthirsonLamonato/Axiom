"""
modules/calendar_integration.py — Integração com Google Calendar
Requer: google-api-python-client, google-auth-oauthlib (já em requirements.txt)
Credenciais: coloque credentials.json em core/credentials.json e execute
  'axiom, autoriza calendário' uma vez para gerar o token.
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_PATH = "core/calendar_token.json"
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


# ── Comandos públicos ──────────────────────────────────────────────────

def get_today_events(*_) -> str:
    """Lista os eventos de hoje no Google Calendar."""
    try:
        service = _get_service()
    except (FileNotFoundError, RuntimeError) as e:
        return str(e)
    except Exception as e:
        logger.error("Erro ao conectar Calendar: %s", e, exc_info=True)
        return f"Erro ao conectar com o Google Calendar: {e}"

    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    try:
        result = service.events().list(
            calendarId="primary",
            timeMin=start_of_day,
            timeMax=end_of_day,
            singleEvents=True,
            orderBy="startTime",
            maxResults=10,
        ).execute()
    except Exception as e:
        logger.error("Erro ao listar eventos: %s", e, exc_info=True)
        return f"Erro ao buscar eventos: {e}"

    events = result.get("items", [])
    if not events:
        return "Nenhum evento encontrado para hoje."

    lines = [f"Agenda de hoje ({now.strftime('%d/%m/%Y')}):"]
    for ev in events:
        lines.append(f"  • {_format_event(ev)}")
    return "\n".join(lines)


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


def add_event(raw: str, *_) -> str:
    """Adiciona um evento via linguagem natural.
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

    # Detectar dia
    if re.search(r"\bamanhã\b", raw, re.I):
        base_date = now + timedelta(days=1)
    elif re.search(r"\bhoje\b", raw, re.I):
        base_date = now
    else:
        base_date = now + timedelta(days=1)  # padrão: amanhã

    # Detectar horário
    hour_match = re.search(r"\bàs?\s+(\d{1,2})h(\d{2})?\b", raw, re.I)
    if not hour_match:
        hour_match = re.search(r"\b(\d{1,2}):(\d{2})\b", raw)
    if hour_match:
        hour = int(hour_match.group(1))
        minute = int(hour_match.group(2) or 0)
    else:
        hour, minute = 9, 0

    # Título: remove palavras-chave de data/hora
    title = re.sub(r"\b(amanhã|hoje|às?|sobre)\b", "", raw, flags=re.I)
    title = re.sub(r"\b\d{1,2}h\d{0,2}\b", "", title)
    title = re.sub(r"\b\d{1,2}:\d{2}\b", "", title)
    title = " ".join(title.split()) or "Evento"

    start_dt = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end_dt = start_dt + timedelta(hours=1)

    tz = datetime.now().astimezone().strftime("%Z")
    event_body = {
        "summary": title.capitalize(),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
    }

    try:
        created = service.events().insert(calendarId="primary", body=event_body).execute()
        return (
            f"Evento criado: '{created['summary']}' — "
            f"{start_dt.strftime('%d/%m %H:%M')} a {end_dt.strftime('%H:%M')}"
        )
    except Exception as e:
        logger.error("Erro ao criar evento: %s", e, exc_info=True)
        return f"Erro ao criar evento: {e}"


def auth_calendar(*_) -> str:
    """Abre o fluxo OAuth para autorizar o Google Calendar."""
    try:
        _get_service()
        return "Google Calendar autorizado com sucesso."
    except FileNotFoundError as e:
        return str(e)
    except Exception as e:
        return f"Erro na autorização: {e}"
