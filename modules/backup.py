"""
modules/backup.py — Backup automático de transcrições e resumos
Salva localmente e opcionalmente no Google Drive.
"""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
]


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
    # Dados úteis para recuperação; credenciais, perfil do navegador e downloads
    # ficam deliberadamente fora do backup automático.
    for folder in ("data/transcriptions", "data/summaries", "data/kb"):
        if os.path.exists(folder):
            dest = os.path.join(backup_path, os.path.basename(folder))
            shutil.copytree(folder, dest, dirs_exist_ok=True)
            results.append(folder)
    for file_path in ("data/task-plans.json",):
        if os.path.isfile(file_path):
            shutil.copy2(file_path, os.path.join(backup_path, os.path.basename(file_path)))
            results.append(file_path)

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "items": results,
        "excluded": ["browser-profile", "downloads", "credentials", "tokens"],
    }
    with open(os.path.join(backup_path, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    _apply_retention(local_dir, int(config.get("backup.keep", 10)))

    msg = f"Backup local criado em {backup_path}."
    logger.info(msg)

    if config.get("backup.google_drive.enabled", False):
        drive_result = _upload_to_drive(backup_path, config)
        msg += f" {drive_result}"

    return msg


def list_backups() -> list[dict]:
    """Lista backups locais sem expor conteúdo sensível."""
    local_dir = _get_config().get("backup.local_dir", "data/backups")
    root = Path(local_dir)
    if not root.exists():
        return []
    result = []
    for path in sorted(root.glob("backup_*"), reverse=True):
        if path.is_dir():
            manifest = path / "manifest.json"
            data = {}
            if manifest.exists():
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            result.append({"path": str(path), "created_at": data.get("created_at", path.name), "items": data.get("items", [])})
    return result


def restore_backup(backup_path: str) -> str:
    """Restaura somente os dados suportados de um backup local conhecido."""
    config = _get_config()
    root = Path(config.get("backup.local_dir", "data/backups")).resolve()
    source = Path(backup_path).resolve()
    if root not in source.parents or not source.is_dir() or not source.name.startswith("backup_"):
        raise ValueError("Backup inválido: o caminho precisa estar dentro do diretório de backups.")
    allowed = {"transcriptions", "summaries", "kb", "task-plans.json"}
    restored = []
    for child in source.iterdir():
        if child.name == "manifest.json":
            continue
        if child.name not in allowed:
            continue
        target = Path("data") / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)
        restored.append(child.name)
    return f"Backup restaurado: {', '.join(restored) if restored else 'nenhum dado encontrado'}."


def _apply_retention(local_dir: str, keep: int):
    if keep <= 0:
        return
    root = Path(local_dir)
    backups = sorted((p for p in root.glob("backup_*") if p.is_dir()), reverse=True)
    for old in backups[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def _get_drive_service(config):
    """Autentica e retorna o serviço Google Drive, reutilizando token salvo."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError("Instale: pip install google-api-python-client google-auth-oauthlib")

    creds_path = config.get("backup.google_drive.credentials_path", "core/credentials.json")
    token_path = config.get("backup.google_drive.token_path", "core/google_token.json")

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, _DRIVE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(
                    f"Credenciais Google não encontradas: {creds_path}\n"
                    "Execute o setup wizard para autorizar sua conta Google."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, _DRIVE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        logger.info("Token Google Drive salvo em %s", token_path)

    return build("drive", "v3", credentials=creds)


def _upload_to_drive(local_path: str, config) -> str:
    try:
        from googleapiclient.http import MediaFileUpload
        service = _get_drive_service(config)
    except (FileNotFoundError, RuntimeError) as e:
        return str(e)
    except Exception as e:
        logger.error("Erro ao conectar Drive: %s", e, exc_info=True)
        return f"Erro ao conectar com o Google Drive: {e}"

    folder_name = config.get("backup.google_drive.folder_name", "Paçoca Backups")

    try:
        folder_id = _get_or_create_drive_folder(service, folder_name)
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
    except Exception as e:
        logger.error("Erro no upload Drive: %s", e)
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
