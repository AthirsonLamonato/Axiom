"""
modules/backup.py — Backup automático de transcrições e resumos
Salva localmente e opcionalmente no Google Drive.
"""

import logging
import os
import shutil
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_config():
    from core.config import Config
    return Config()


def backup_all(*_) -> str:
    """Faz backup de todos os arquivos de data/."""
    config = _get_config()
    local_dir = config.get("backup.local_dir", "data/backups")
    os.makedirs(local_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(local_dir, f"backup_{timestamp}")
    os.makedirs(backup_path, exist_ok=True)

    results = []

    for folder in ("data/transcriptions", "data/summaries"):
        if os.path.exists(folder):
            dest = os.path.join(backup_path, os.path.basename(folder))
            shutil.copytree(folder, dest)
            results.append(folder)

    msg = f"Backup local criado em {backup_path}."
    logger.info(msg)

    # Google Drive (se habilitado)
    if config.get("backup.google_drive.enabled", False):
        drive_result = _upload_to_drive(backup_path, config)
        msg += f" {drive_result}"

    return msg


def _upload_to_drive(local_path: str, config) -> str:
    creds_path = config.get("backup.google_drive.credentials_path", "")
    folder_name = config.get("backup.google_drive.folder_name", "Axiom Backups")

    if not os.path.exists(creds_path):
        return "Credenciais do Google Drive não encontradas."

    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        SCOPES = ["https://www.googleapis.com/auth/drive.file"]

        flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
        creds = flow.run_local_server(port=0)
        service = build("drive", "v3", credentials=creds)

        # Cria pasta no Drive se não existir
        folder_id = _get_or_create_drive_folder(service, folder_name)

        # Upload de cada arquivo do backup
        uploaded = 0
        for root, _, files in os.walk(local_path):
            for fname in files:
                fpath = os.path.join(root, fname)
                media = MediaFileUpload(fpath)
                service.files().create(
                    body={"name": fname, "parents": [folder_id]},
                    media_body=media,
                ).execute()
                uploaded += 1

        return f"Google Drive: {uploaded} arquivos enviados para '{folder_name}'."

    except ImportError:
        return "Bibliotecas do Google não instaladas."
    except Exception as e:
        logger.error(f"Erro no upload Drive: {e}")
        return f"Erro no Drive: {e}"


def _get_or_create_drive_folder(service, folder_name: str) -> str:
    results = service.files().list(
        q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'",
        fields="files(id)",
    ).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    folder = service.files().create(
        body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return folder["id"]
