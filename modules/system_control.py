"""
modules/system_control.py — Controle do sistema operacional
Abre/fecha apps, ajusta volume e brilho, lista processos.
Compatível com Windows e Linux.
"""

import sys
import subprocess
import logging
import platform

logger = logging.getLogger(__name__)
OS = platform.system()  # "Windows" | "Linux" | "Darwin"


# ── Aplicativos ────────────────────────────────────────────────────────

def open_app(name: str) -> str:
    """Abre um aplicativo pelo nome ou comando."""
    name = name.strip()
    try:
        if OS == "Windows":
            subprocess.Popen(name, shell=True)
        else:
            subprocess.Popen(name, shell=True, start_new_session=True)
        logger.info(f"Abrindo: {name}")
        return f"Abrindo {name}."
    except Exception as e:
        logger.error(f"Erro ao abrir '{name}': {e}")
        return f"Não consegui abrir '{name}': {e}"


def close_app(name: str) -> str:
    """Encerra processos cujo nome contenha o argumento."""
    import psutil
    name = name.strip().lower()
    killed = []
    for proc in psutil.process_iter(["name", "pid"]):
        if name in proc.info["name"].lower():
            try:
                proc.terminate()
                killed.append(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    if killed:
        return f"Encerrei: {', '.join(killed)}."
    return f"Nenhum processo '{name}' encontrado."


def list_processes() -> str:
    """Lista os 10 processos com maior uso de CPU."""
    import psutil
    procs = sorted(
        psutil.process_iter(["name", "cpu_percent"]),
        key=lambda p: p.info["cpu_percent"] or 0,
        reverse=True,
    )[:10]
    lines = [f"{p.info['name']} ({p.info['cpu_percent']:.1f}%)" for p in procs]
    return "Top processos:\n" + "\n".join(lines)


# ── Volume ─────────────────────────────────────────────────────────────

def set_volume(level: str) -> str:
    """Define o volume do sistema (0–100)."""
    try:
        lvl = int(level)
        lvl = max(0, min(100, lvl))
    except ValueError:
        return "Volume inválido. Use um número de 0 a 100."

    if OS == "Windows":
        return _set_volume_windows(lvl)
    elif OS == "Linux":
        return _set_volume_linux(lvl)
    return "Controle de volume não suportado neste sistema."


def _set_volume_windows(level: int) -> str:
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100, None)
        return f"Volume ajustado para {level}%."
    except ImportError:
        return "pycaw não instalado (Windows). Rode: pip install pycaw"


def _set_volume_linux(level: int) -> str:
    subprocess.run(["amixer", "-q", "sset", "Master", f"{level}%"])
    return f"Volume ajustado para {level}%."


def mute(*_) -> str:
    """Muta/desmuta o som."""
    if OS == "Windows":
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            current = vol.GetMute()
            vol.SetMute(not current, None)
            return "Som silenciado." if not current else "Som ativado."
        except ImportError:
            return "pycaw não instalado."
    elif OS == "Linux":
        subprocess.run(["amixer", "-q", "sset", "Master", "toggle"])
        return "Som alternado."
    return "Não suportado."


# ── Brilho ─────────────────────────────────────────────────────────────

def brightness_up(*_) -> str:
    return _adjust_brightness(+10)


def brightness_down(*_) -> str:
    return _adjust_brightness(-10)


def _adjust_brightness(delta: int) -> str:
    if OS == "Windows":
        try:
            import wmi
            c = wmi.WMI(namespace="wmi")
            methods = c.WmiMonitorBrightnessMethods()[0]
            current = c.WmiMonitorBrightness()[0].CurrentBrightness
            new_val = max(0, min(100, current + delta))
            methods.WmiSetBrightness(new_val, 0)
            return f"Brilho ajustado para {new_val}%."
        except Exception as e:
            return f"Erro ao ajustar brilho: {e}"
    elif OS == "Linux":
        try:
            result = subprocess.run(
                ["brightnessctl", "get"], capture_output=True, text=True
            )
            current = int(result.stdout.strip())
            new_val = max(0, current + delta * 10)
            subprocess.run(["brightnessctl", "set", str(new_val)])
            return f"Brilho ajustado."
        except FileNotFoundError:
            return "brightnessctl não encontrado. Instale com: sudo apt install brightnessctl"
    return "Controle de brilho não suportado."
