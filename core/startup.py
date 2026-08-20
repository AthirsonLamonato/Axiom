"""Integração opcional com a inicialização do usuário no Windows.

O autostart é instalado como um arquivo ``.cmd`` na pasta Startup do usuário.
A operação é reversível e nunca altera o registro do Windows nem exige privilégios
administrativos.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

STARTUP_FILENAME = "Pacoca Voice Agent.cmd"


def startup_directory() -> Path:
    """Retorna a pasta Startup do usuário atual."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA não está disponível; o Windows não foi detectado corretamente.")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_path() -> Path:
    return startup_directory() / STARTUP_FILENAME


def _entry_command(project_dir: Path | None = None) -> str:
    """Monta o comando de inicialização com quoting compatível com Windows."""
    project_dir = (project_dir or Path(__file__).resolve().parents[1]).resolve()
    python_exe = Path(sys.executable).resolve()
    args = [str(python_exe), str(project_dir / "main.py"), "--mode", "voice"]
    return subprocess.list2cmdline(args)


def install_startup(project_dir: Path | None = None) -> Path:
    """Instala ou atualiza o autostart do usuário sem solicitar elevação."""
    if os.name != "nt":
        raise OSError("O autostart automático está disponível somente no Windows.")
    target = startup_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    project_dir = (project_dir or Path(__file__).resolve().parents[1]).resolve()
    content = (
        "@echo off\n"
        f"cd /d {subprocess.list2cmdline([str(project_dir)])}\n"
        f"start \"\" { _entry_command(project_dir) }\n"
    )
    target.write_text(content, encoding="utf-8", newline="\r\n")
    return target


def remove_startup() -> bool:
    """Remove o autostart do usuário, retornando se havia um arquivo instalado."""
    if os.name != "nt":
        raise OSError("O autostart automático está disponível somente no Windows.")
    target = startup_path()
    if not target.exists():
        return False
    target.unlink()
    return True


def is_installed() -> bool:
    """Informa se o autostart do Paçoca está instalado para o usuário."""
    if os.name != "nt":
        return False
    return startup_path().is_file()


__all__ = [
    "install_startup",
    "remove_startup",
    "is_installed",
    "startup_directory",
    "startup_path",
]
