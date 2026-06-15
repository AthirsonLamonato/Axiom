"""
modules/system_control.py — Controle do sistema operacional
Abre/fecha apps, pastas e ferramentas do sistema dinamicamente.
Compatível com Windows e Linux (incluindo WSL).
"""

import re
import subprocess
import logging
import platform
import urllib.parse
from pathlib import Path

logger = logging.getLogger(__name__)
OS = platform.system()


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


IS_WSL = OS == "Linux" and _is_wsl()

# ── Cache de apps do Menu Iniciar ─────────────────────────────────────
_wsl_app_cache: dict[str, str] | None = None

_STOP_WORDS = {
    "o", "a", "os", "as", "um", "uma", "pra", "para", "mim", "por", "favor",
    "me", "agora", "já", "ja", "aí", "ai",
}


def _clean_name(name: str) -> str:
    name = re.sub(r"[.,!?]$", "", name.strip())
    words = name.split()
    while words and words[0].lower() in _STOP_WORDS:
        words.pop(0)
    while words and words[-1].lower() in _STOP_WORDS:
        words.pop()
    return " ".join(words)


def _load_wsl_apps() -> dict[str, str]:
    global _wsl_app_cache
    if _wsl_app_cache is not None:
        return _wsl_app_cache
    ps = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "Get-StartApps | ForEach-Object { $_.Name + '||' + $_.AppID }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=10
        )
        output = result.stdout.decode("utf-8-sig", errors="replace")
        apps: dict[str, str] = {}
        for line in output.splitlines():
            if "||" in line:
                name_part, app_id = line.split("||", 1)
                apps[name_part.strip().lower()] = app_id.strip()
        _wsl_app_cache = apps
        logger.info("WSL app cache: %d apps encontrados", len(apps))
    except Exception as e:
        logger.warning("Não foi possível carregar apps do Windows: %s", e)
        _wsl_app_cache = {}
    return _wsl_app_cache


def _find_wsl_app(query: str) -> tuple[str, str] | None:
    from difflib import get_close_matches
    apps = _load_wsl_apps()
    if not apps:
        return None
    q = _clean_name(query).lower()
    if q in apps:
        return q, apps[q]
    partial = [(k, v) for k, v in apps.items() if q in k or k in q]
    if partial:
        partial.sort(key=lambda x: len(x[0]))
        return partial[0]
    candidates = list(apps.keys())
    matches = get_close_matches(q, candidates, n=1, cutoff=0.6)
    if not matches:
        for word in q.split():
            if len(word) > 3:
                matches = get_close_matches(word, candidates, n=1, cutoff=0.7)
                if matches:
                    break
    if matches:
        return matches[0], apps[matches[0]]
    return None


# ── Resolução dinâmica via IA (com cache) ─────────────────────────────

def _cached_command(name: str) -> str:
    """Retorna comando cacheado ou '' se não houver."""
    try:
        from storage.memory import get_preference
        return get_preference(f"win_cmd:{name.lower()}", "")
    except Exception:
        return ""


def _cache_command(name: str, cmd: str):
    try:
        from storage.memory import set_preference
        set_preference(f"win_cmd:{name.lower()}", cmd)
    except Exception:
        pass


def _resolve_with_ai(name: str) -> str:
    """
    Pergunta ao LLM qual comando Windows abre `name`.
    Salva o resultado em memory.db para não perguntar de novo.
    Retorna o comando ou '' se não souber.
    """
    cached = _cached_command(name)
    if cached:
        return cached

    try:
        import os, requests
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return ""
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You resolve Windows application/tool names to their executable commands. "
                            "Reply with ONLY the executable or .msc file, nothing else. "
                            "Examples: devmgmt.msc, regedit.exe, taskmgr.exe, control.exe, "
                            "msconfig.exe, eventvwr.msc, compmgmt.msc, mstsc.exe"
                        ),
                    },
                    {"role": "user", "content": f"Windows command to open: {name}"},
                ],
                "max_tokens": 30,
                "temperature": 0,
            },
            timeout=8,
        )
        if resp.ok:
            cmd = resp.json()["choices"][0]["message"]["content"].strip().split()[0]
            if cmd and len(cmd) < 50:
                _cache_command(name, cmd)
                logger.info("AI resolveu '%s' → '%s'", name, cmd)
                return cmd
    except Exception as e:
        logger.debug("AI resolution falhou: %s", e)
    return ""


def _run_win(cmd: str) -> bool:
    """Executa um comando Windows via PowerShell. Retorna True se não deu erro."""
    try:
        r = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-Command", f'Start-Process "{cmd}"'],
            start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return True
    except Exception:
        return False


# ── Aplicativos ────────────────────────────────────────────────────────

def open_app(name: str) -> str:
    """
    Abre qualquer aplicativo ou ferramenta do sistema.
    Estratégias (em ordem): VS Code especial → Get-StartApps → Start-Process direto → IA.
    """
    name = _clean_name(name.strip())
    name_lower = name.lower()

    # VS Code tem integração nativa WSL
    if IS_WSL and any(k in name_lower for k in ("vs code", "vscode", "visual studio code")):
        subprocess.Popen("code .", shell=True, start_new_session=True)
        return "Abrindo VS Code."

    if IS_WSL or OS == "Windows":
        # 1. Menu Iniciar (apps instalados)
        match = _find_wsl_app(name)
        if match:
            found_name, app_id = match
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-Command",
                 f'Start-Process "shell:AppsFolder\\{app_id}"'],
                start_new_session=True
            )
            return f"Abrindo {found_name.title()}."

        # 2. Start-Process direto — resolve exes e .msc no PATH do Windows
        _run_win(name)

        # 3. IA: traduz nome natural → comando Windows e tenta de novo
        ai_cmd = _resolve_with_ai(name)
        if ai_cmd and ai_cmd.lower() != name.lower():
            _run_win(ai_cmd)
            return f"Abrindo {name.title()}."

        return f"Abrindo {name.title()}."

    # Linux nativo
    try:
        subprocess.Popen(name.split(), start_new_session=True)
    except Exception as e:
        return f"Não consegui abrir '{name}': {e}"
    return f"Abrindo {name.title()}."


def close_app(name: str) -> str:
    import psutil
    name = _clean_name(name.strip()).lower()
    killed = []
    for proc in psutil.process_iter(["name", "pid"]):
        if name in proc.info["name"].lower():
            try:
                proc.terminate()
                killed.append(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return f"Encerrei: {', '.join(killed)}." if killed else f"Nenhum processo '{name}' encontrado."


# ── Pastas ─────────────────────────────────────────────────────────────

# Mapeamento PT/EN → shell: URI ou subcaminho de %USERPROFILE%
# Apenas nomes estruturais — não é uma lista de conteúdo, é infraestrutura de paths
_FOLDER_MAP: dict[str, str] = {
    "downloads":           r"$env:USERPROFILE\Downloads",
    "documentos":          r"$env:USERPROFILE\Documents",
    "documents":           r"$env:USERPROFILE\Documents",
    "imagens":             r"$env:USERPROFILE\Pictures",
    "pictures":            r"$env:USERPROFILE\Pictures",
    "videos":              r"$env:USERPROFILE\Videos",
    "músicas":             r"$env:USERPROFILE\Music",
    "musicas":             r"$env:USERPROFILE\Music",
    "music":               r"$env:USERPROFILE\Music",
    "desktop":             r"$env:USERPROFILE\Desktop",
    "área de trabalho":    r"$env:USERPROFILE\Desktop",
    "area de trabalho":    r"$env:USERPROFILE\Desktop",
    "temp":                r"$env:TEMP",
    "sistema":             r"$env:SystemRoot\System32",
    "system32":            r"$env:SystemRoot\System32",
    "arquivos de programas": r"$env:ProgramFiles",
    "program files":       r"$env:ProgramFiles",
    "appdata":             r"$env:APPDATA",
    "inicio":              r"$env:APPDATA\Microsoft\Windows\Start Menu",
    "iniciar":             r"$env:APPDATA\Microsoft\Windows\Start Menu",
}


def open_folder(path_or_name: str) -> str:
    """
    Abre uma pasta no Explorer. Aceita:
    - Nome comum em PT/EN: "downloads", "documentos", "desktop"
    - Caminho absoluto: C:\\Users\\Athy\\Projetos
    - Caminho Linux (WSL): /home/athy/Projetos
    """
    path_or_name = _clean_name(path_or_name.strip())
    name_lower = path_or_name.lower().rstrip("s")  # remove plural

    # Busca no mapa (exata ou sem plural)
    folder_path = _FOLDER_MAP.get(path_or_name.lower()) or _FOLDER_MAP.get(name_lower)

    if folder_path:
        if IS_WSL or OS == "Windows":
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-Command",
                 f'Start-Process "explorer.exe" "{folder_path}"'],
                start_new_session=True
            )
        return f"Abrindo pasta {path_or_name.title()}."

    # Caminho absoluto Linux → converte para Windows (WSL)
    p = Path(path_or_name)
    if IS_WSL and path_or_name.startswith("/"):
        win_path = subprocess.run(
            ["wslpath", "-w", path_or_name], capture_output=True, text=True
        ).stdout.strip()
        if win_path:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-Command",
                 f'Start-Process "explorer.exe" "{win_path}"'],
                start_new_session=True
            )
            return f"Abrindo {path_or_name} no Explorer."

    # Caminho Windows direto
    if IS_WSL or OS == "Windows":
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-Command",
             f'Start-Process "explorer.exe" "{path_or_name}"'],
            start_new_session=True
        )
        return f"Abrindo {path_or_name}."

    # Linux nativo
    subprocess.Popen(["xdg-open", path_or_name], start_new_session=True)
    return f"Abrindo {path_or_name}."


# ── Browser ────────────────────────────────────────────────────────────

def open_search(query: str) -> str:
    """Abre uma busca ou URL no navegador padrão."""
    query = _clean_name(query.strip())
    url, label = _destination_to_url(query)
    return _open_url_default(url, label)


def open_url(url: str) -> str:
    """Abre uma URL diretamente no navegador padrão."""
    url = url.strip()
    return _open_url_default(url, url)


def _open_url_default(url: str, label: str) -> str:
    """Abre URL no navegador padrão do sistema."""
    try:
        if IS_WSL or OS == "Windows":
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-Command", f'Start-Process "{url}"'],
                start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(["xdg-open", url], start_new_session=True)
        return f"Abrindo {label}."
    except Exception as e:
        return f"Não consegui abrir {label}: {e}"


def open_browser_with_search(app_name: str, destination: str) -> str:
    """
    Abre um navegador em um site ou com uma busca.
    URL é resolvida dinamicamente — sem lista hardcoded de sites.
    """
    destination = _clean_name(destination.strip())
    url, label = _destination_to_url(destination)
    browser = _clean_name(app_name).lower()

    try:
        if IS_WSL or OS == "Windows":
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-Command",
                 f'Start-Process "{browser}" -ArgumentList "{url}"'],
                start_new_session=True
            )
        else:
            subprocess.Popen([browser, url], start_new_session=True)
        return f"Abrindo {browser.title()} no {label}."
    except Exception as e:
        logger.error("Erro ao abrir browser: %s", e)
        return f"Não consegui abrir {browser}: {e}"


def _destination_to_url(dest: str) -> tuple[str, str]:
    """
    Converte um destino em (url, label) sem lista hardcoded.
    - "youtube"    → https://www.youtube.com | YouTube
    - "pesquisa X" → Google search
    - URL já pronta → passada direto
    """
    dest_lower = dest.lower()

    if dest_lower.startswith(("http://", "https://")):
        return dest, dest

    # Palavra/frase simples sem espaços → trata como nome de site
    if re.match(r"^[\w.-]+$", dest_lower):
        if "." in dest_lower:
            # Já tem TLD (peao.digital, github.com) → usa direto
            return f"https://{dest_lower}", dest
        return f"https://www.{dest_lower}.com", dest.title()

    # Frase com espaços que parece um domínio com TLD: "peao .digital" ou "peão.digital"
    # Normaliza acentos e testa
    import unicodedata
    normalized = unicodedata.normalize("NFKD", dest_lower).encode("ascii", "ignore").decode()
    normalized = normalized.replace(" ", "")
    if re.match(r"^[\w.-]+\.[a-z]{2,}$", normalized):
        return f"https://{normalized}", dest

    # Múltiplas palavras → busca no Google
    return f"https://www.google.com/search?q={urllib.parse.quote(dest)}", f"busca '{dest}'"


# ── Volume ─────────────────────────────────────────────────────────────

def set_volume(level: str) -> str:
    try:
        lvl = max(0, min(100, int(level)))
    except ValueError:
        return "Volume inválido. Use um número de 0 a 100."
    if OS == "Windows":
        return _set_volume_windows(lvl)
    return _set_volume_linux(lvl)


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
        return "pycaw não instalado."


def _set_volume_linux(level: int) -> str:
    subprocess.run(["amixer", "-q", "sset", "Master", f"{level}%"])
    return f"Volume ajustado para {level}%."


def mute(*_) -> str:
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
    subprocess.run(["amixer", "-q", "sset", "Master", "toggle"])
    return "Som alternado."


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
            methods.WmiSetBrightness(max(0, min(100, current + delta)), 0)
            return f"Brilho ajustado."
        except Exception as e:
            return f"Erro ao ajustar brilho: {e}"
    try:
        result = subprocess.run(["brightnessctl", "get"], capture_output=True, text=True)
        new_val = max(0, int(result.stdout.strip()) + delta * 10)
        subprocess.run(["brightnessctl", "set", str(new_val)])
        return "Brilho ajustado."
    except FileNotFoundError:
        return "brightnessctl não encontrado."


# ── Processos ─────────────────────────────────────────────────────────

def list_processes(*_) -> str:
    import psutil
    procs = sorted(
        psutil.process_iter(["name", "cpu_percent"]),
        key=lambda p: p.info["cpu_percent"] or 0,
        reverse=True,
    )[:10]
    lines = [f"{p.info['name']} ({p.info['cpu_percent']:.1f}%)" for p in procs]
    return "Top processos:\n" + "\n".join(lines)
