"""
modules/backup.py — Backup automático de transcrições e resumos
Salva localmente e opcionalmente no Google Drive.
"""

import logging
import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from modules.external_actions import live_enabled

logger = logging.getLogger(__name__)

_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
]


def _get_config():
    from core.config import Config
    return Config()


def _file_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _write_manifest(backup_path: Path) -> None:
    manifest = {"version": 1, "files": _file_hashes(backup_path)}
    temp_path = backup_path / "manifest.json.tmp"
    temp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(backup_path / "manifest.json")


def verify_backup(backup_path: str | os.PathLike[str]) -> tuple[bool, str]:
    """Confere manifesto e SHA-256 de todos os arquivos do backup."""
    root = Path(backup_path).resolve()
    manifest_path = root / "manifest.json"
    if not root.is_dir() or not manifest_path.is_file():
        return False, "Backup inválido: diretório ou manifesto ausente."
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = manifest.get("files", {})
    except (OSError, json.JSONDecodeError) as e:
        return False, f"Manifesto de backup inválido: {e}"
    if not isinstance(expected, dict) or expected != _file_hashes(root):
        return False, "Backup corrompido ou alterado: hashes não conferem."
    return True, f"Backup íntegro: {len(expected)} arquivo(s) verificado(s)."


def backup_all(*_, allow_external: bool = False) -> str:
    """Faz backup de todos os arquivos de data/."""
    config = _get_config()
    local_dir = config.get("backup.local_dir", "data/backups")
    os.makedirs(local_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = Path(local_dir) / f"backup_{timestamp}"
    backup_path.mkdir(parents=True, exist_ok=False)

    results = []
    for folder in ("data/transcriptions", "data/summaries"):
        if os.path.exists(folder):
            dest = backup_path / os.path.basename(folder)
            shutil.copytree(folder, dest)
            results.append(folder)

    _write_manifest(backup_path)

    msg = f"Backup local criado em {backup_path}."
    logger.info(msg)

    if config.get("backup.google_drive.enabled", False):
        if allow_external and live_enabled(config):
            drive_result = _upload_to_drive(str(backup_path), config)
            msg += f" {drive_result}"
        else:
            msg += " [SIMULAÇÃO] Upload ao Google Drive não executado."

    return msg


def restore_backup(backup_name: str, destination: str = "") -> str:
    """Restaura em pasta nova, dentro do workspace, sem sobrescrever dados vivos."""
    config = _get_config()
    backup_root = Path(config.get("backup.local_dir", "data/backups")).resolve()
    source = (backup_root / backup_name).resolve()
    try:
        source.relative_to(backup_root)
    except ValueError:
        return "Restauração bloqueada: backup fora do diretório autorizado."

    valid, detail = verify_backup(source)
    if not valid:
        return detail

    workspace = Path.cwd().resolve()
    target = Path(destination).resolve() if destination else (workspace / "data" / "restored" / source.name)
    try:
        target.relative_to(workspace)
    except ValueError:
        return "Restauração bloqueada: destino fora do workspace."
    if target.exists():
        return f"Restauração bloqueada: destino já existe: {target}"

    try:
        shutil.copytree(source, target)
        restored_valid, restored_detail = verify_backup(target)
        if not restored_valid:
            shutil.rmtree(target)
            return f"Restauração falhou na verificação: {restored_detail}"
    except Exception as e:
        if target.exists():
            shutil.rmtree(target)
        logger.error("Falha ao restaurar backup: %s", e, exc_info=True)
        return f"Falha ao restaurar backup: {e}"

    return f"Backup restaurado e verificado em {target}. {detail}"


def _get_drive_service(config):
    """Autentica e retorna o serviço Google Drive, reutilizando token salvo."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError as err:
        raise RuntimeError(
            "Instale: pip install google-api-python-client google-auth-oauthlib"
        ) from err

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
