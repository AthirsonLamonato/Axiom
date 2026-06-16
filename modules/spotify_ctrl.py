"""
modules/spotify_ctrl.py — Controle do Spotify
Modo básico: abre Spotify com URI de busca (sem autenticação).
Modo avançado: Web API com OAuth (SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET no .env).
"""

import os
import json
import logging
import re
import subprocess
import platform
import time
from pathlib import Path

logger = logging.getLogger(__name__)

OS = platform.system()
_TOKEN_FILE = Path(__file__).parent.parent / ".spotify_token.json"


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False

IS_WSL = OS == "Linux" and _is_wsl()


# ── Modo básico: URI scheme (sem autenticação) ─────────────────────────

def _is_spotify_running() -> bool:
    """Verifica se o processo do Spotify está rodando no Windows via PowerShell."""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-Process -Name 'Spotify' -ErrorAction SilentlyContinue | Select-Object -First 1"],
            capture_output=True, text=True, timeout=5
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _ensure_spotify_ready(was_just_opened: bool = False):
    """Garante que o Spotify está pronto para receber comandos."""
    if was_just_opened:
        # Spotify acabou de abrir — espera ele carregar
        time.sleep(4)
        return

    if not _is_spotify_running():
        # Abre o Spotify e espera
        _open_spotify_uri("spotify:")
        time.sleep(5)


def _open_spotify_uri(uri: str):
    """Abre um URI do Spotify (spotify:search:xxx, spotify:track:ID, etc.)."""
    if IS_WSL or OS == "Windows":
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-Command", f'Start-Process "{uri}"'],
            start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    else:
        subprocess.Popen(["xdg-open", uri], start_new_session=True)


_GENERIC_QUERIES = {"uma música", "uma musica", "algo", "qualquer coisa", "alguma coisa", "música", "musica", ""}

_ARTIST_PREFIXES = re.compile(
    r'\b(?:do|da|de|pelo|pela|por)\s+(.+)$', re.IGNORECASE
)
_GENERIC_TRACK = re.compile(
    r'^(?:uma\s+)?(?:m[úu]sica|faixa|track|som|algo|qualquer)(?:\s+(?:do|da|de|pelo|pela|por)\s+(.+))?$',
    re.IGNORECASE
)


def _parse_query(raw: str) -> tuple[str, str]:
    """
    Retorna (track_query, artist) a partir de strings como:
      'Rap God do Eminem'        → ('Rap God', 'Eminem')
      'uma música do Eminem'     → ('', 'Eminem')
      'Bohemian Rhapsody'        → ('Bohemian Rhapsody', '')
      'o artista Eminem'         → ('', 'Eminem')
      'toca Linkin Park'         → ('Linkin Park', '')
    """
    raw = raw.strip().rstrip(".,!")

    # Remove verbos iniciais que possam ter escapado das rotas ("toca", "play", etc.)
    raw = _LEADING_VERBS_Q.sub("", raw).strip()

    # "o artista X" / "a banda X" / "cantor X" etc. → artist
    leading_artist = _ARTIST_LEADING.match(raw)
    if leading_artist:
        return "", leading_artist.group(1).strip()

    # Padrão: "[track] do/de [artista]"
    artist_match = _ARTIST_PREFIXES.search(raw)
    if artist_match:
        artist = artist_match.group(1).strip()
        track = raw[:artist_match.start()].strip()
        # Se a parte do track for genérica ("uma música", etc.), ignora
        if _GENERIC_TRACK.match(track) or track.lower() in _GENERIC_QUERIES:
            track = ""
        return track, artist

    return raw, ""


def play_search(query: str, spotify_just_opened: bool = False) -> str:
    """Abre o Spotify buscando pela query (sem autenticação)."""
    import urllib.parse
    query = query.strip().rstrip(".,!")

    # Query genérica ("toca uma música") — só retoma ou abre o Spotify
    if query.lower() in _GENERIC_QUERIES:
        _ensure_spotify_ready(spotify_just_opened)
        if _has_api_credentials():
            return _api_resume()
        _media_key("play")
        return "Spotify pronto."

    # Tenta Web API se credenciais disponíveis
    if _has_api_credentials():
        _ensure_spotify_ready(spotify_just_opened)
        return _api_play_search(query)

    # Fallback: garante que o Spotify está pronto e abre com URI de busca
    _ensure_spotify_ready(spotify_just_opened)
    uri = f"spotify:search:{urllib.parse.quote(query)}"
    _open_spotify_uri(uri)
    return f"Buscando '{query}' no Spotify."


def play_playlist(name: str) -> str:
    """Toca uma playlist pelo nome."""
    name = name.strip().rstrip(".,!")
    if _has_api_credentials():
        return _api_play_playlist(name)

    import urllib.parse
    uri = f"spotify:search:{urllib.parse.quote(name)}"
    _open_spotify_uri(uri)
    return f"Buscando playlist '{name}' no Spotify."


def pause(*_) -> str:
    if _has_api_credentials():
        return _api_pause()
    _media_key("pause")
    return "Spotify pausado."


def resume(*_) -> str:
    if _has_api_credentials():
        return _api_resume()
    _media_key("play")
    return "Spotify retomado."


def next_track(*_) -> str:
    if _has_api_credentials():
        return _api_next()
    _media_key("next")
    return "Próxima música."


def previous_track(*_) -> str:
    if _has_api_credentials():
        return _api_previous()
    _media_key("previous")
    return "Música anterior."


def current_track(*_) -> str:
    if _has_api_credentials():
        return _api_current()
    return "Configure SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no .env para ver a música atual."


def _media_key(action: str):
    """Envia tecla de mídia global via Win32 keybd_event (Windows/WSL)."""
    vk_codes = {"play": 0xB3, "pause": 0xB3, "next": 0xB0, "previous": 0xB1}
    vk = vk_codes.get(action, 0xB3)
    if IS_WSL or OS == "Windows":
        ps = (
            "Add-Type -TypeDefinition '"
            "using System; using System.Runtime.InteropServices; "
            "public class MK { "
            "[DllImport(\"user32.dll\")] public static extern void keybd_event(byte vk, byte sc, uint fl, int ei); "
            "public static void Send(byte vk){ keybd_event(vk,0,0,0); keybd_event(vk,0,2,0); } }';"
            f"[MK]::Send({vk});"
        )
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=5)


# ── Modo avançado: Spotify Web API ─────────────────────────────────────

def _has_api_credentials() -> bool:
    return bool(os.environ.get("SPOTIFY_CLIENT_ID") and os.environ.get("SPOTIFY_CLIENT_SECRET"))


def _load_token() -> dict | None:
    if _TOKEN_FILE.exists():
        try:
            import os as _os
            # Garante permissão restrita mesmo em arquivo existente criado antes do fix
            try:
                _os.chmod(_TOKEN_FILE, 0o600)
            except Exception:
                pass
            return json.loads(_TOKEN_FILE.read_text())
        except Exception:
            pass
    return None


def _save_token(data: dict):
    _TOKEN_FILE.write_text(json.dumps(data))
    try:
        import os as _os
        _os.chmod(_TOKEN_FILE, 0o600)
    except Exception:
        pass


def _get_access_token() -> str | None:
    """Retorna access token válido, renovando se necessário."""
    import requests
    import base64

    token_data = _load_token()
    if token_data and token_data.get("expires_at", 0) > time.time() + 30:
        return token_data["access_token"]

    if token_data and token_data.get("refresh_token"):
        client_id = os.environ.get("SPOTIFY_CLIENT_ID")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
        creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": token_data["refresh_token"]},
            timeout=10,
        )
        if resp.ok:
            new_data = resp.json()
            new_data["refresh_token"] = token_data["refresh_token"]
            new_data["expires_at"] = time.time() + new_data.get("expires_in", 3600)
            _save_token(new_data)
            return new_data["access_token"]

    return None


def authorize(*_) -> str:
    """Inicia o fluxo OAuth do Spotify. Abre o browser para autorizar."""
    import urllib.parse
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import requests
    import base64

    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return (
            "Configure SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no .env.\n"
            "Crie um app em: https://developer.spotify.com/dashboard"
        )

    redirect_uri = "http://127.0.0.1:8765/callback"
    scopes = "user-modify-playback-state user-read-playback-state user-read-currently-playing"
    auth_url = (
        "https://accounts.spotify.com/authorize?"
        + urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scopes,
        })
    )

    auth_code_holder = []

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            code = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("code", [None])[0]
            if code:
                auth_code_holder.append(code)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<h1>Spotify autorizado! Pode fechar esta aba.</h1>")
            self.server.shutdown_flag = True

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 8765), _Handler)
    server.shutdown_flag = False
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    _open_spotify_uri(auth_url) if not (IS_WSL or OS == "Windows") else subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-Command", f'Start-Process "{auth_url}"'],
        start_new_session=True
    )

    deadline = time.time() + 60
    while not server.shutdown_flag and time.time() < deadline:
        time.sleep(0.5)
    server.shutdown()

    if not auth_code_holder:
        return "Timeout: autorização não concluída em 60s."

    code = auth_code_holder[0]
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
        timeout=10,
    )
    if not resp.ok:
        return f"Erro ao obter token: {resp.text}"

    data = resp.json()
    data["expires_at"] = time.time() + data.get("expires_in", 3600)
    _save_token(data)
    return "Spotify autorizado com sucesso!"


def _api_request(method: str, endpoint: str, **kwargs):
    import requests
    token = _get_access_token()
    if not token:
        return None
    resp = requests.request(
        method,
        f"https://api.spotify.com/v1{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
        **kwargs,
    )
    # Token expirado — renova e tenta uma vez mais
    if resp.status_code == 401:
        logger.info("Spotify 401 — renovando token e tentando novamente.")
        # Invalida cache de token em memória forçando releitura do disco
        token_data = _load_token()
        if token_data:
            token_data.pop("expires_at", None)
            _save_token(token_data)
        token = _get_access_token()
        if token:
            resp = requests.request(
                method,
                f"https://api.spotify.com/v1{endpoint}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
                **kwargs,
            )
    return resp


def _ensure_active_device() -> bool:
    """
    Garante que há um device ativo (is_active=True).
    Se há devices mas nenhum ativo, transfere a reprodução para o primeiro disponível.
    """
    for delay in (0, 2, 3):
        if delay:
            time.sleep(delay)
        resp = _api_request("GET", "/me/player/devices")
        if resp and resp.ok:
            devices = [d for d in resp.json().get("devices", []) if not d.get("is_restricted")]
            active = [d for d in devices if d.get("is_active")]
            if active:
                return True
            # Há devices mas nenhum ativo — transfere reprodução
            if devices:
                _api_request("PUT", "/me/player", json={"device_ids": [devices[0]["id"]], "play": False})
                time.sleep(1)
    # Último recurso: abre o Spotify e re-verifica
    _open_spotify_uri("spotify:")
    time.sleep(5)
    resp = _api_request("GET", "/me/player/devices")
    if resp and resp.ok:
        devices = [d for d in resp.json().get("devices", []) if not d.get("is_restricted")]
        return any(d.get("is_active") for d in devices)
    return False


_LEADING_ARTICLES = re.compile(
    r'^(?:o|a|os|as|um|uma|the|an?)\s+', re.IGNORECASE
)

_LEADING_VERBS_Q = re.compile(
    r'^(?:toca[r]?|toque|play|coloca[r]?|bota[r]?|quero\s+ouvir)\s+',
    re.IGNORECASE
)

_ARTIST_LEADING = re.compile(
    r'^(?:(?:o|a)\s+)?(?:artista|cantor[a]?|banda|grupo|álbum|album)\s+(.+)$',
    re.IGNORECASE
)


def _best_artist_match(candidates: list[dict], query: str) -> dict | None:
    """
    Escolhe o artista mais relevante combinando similaridade de nome + popularidade.
    Prioriza quem tem nome mais parecido com a query, não o mais popular globalmente.
    """
    from difflib import SequenceMatcher
    if not candidates:
        return None
    q = query.lower()

    def score(a: dict) -> float:
        name_sim = SequenceMatcher(None, a["name"].lower(), q).ratio()
        # Similaridade domina (70%), popularidade normalizada é desempate (30%)
        return name_sim * 0.7 + (a.get("popularity", 0) / 100) * 0.3

    return max(candidates, key=score)


def _api_play_search(query: str) -> str:
    import urllib.parse

    # Remove artigo inicial ("a Eminem" → "Eminem", "o Drake" → "Drake")
    clean = _LEADING_ARTICLES.sub("", query).strip()

    track, artist = _parse_query(clean)

    # Verifica playlists do usuário (só quando não há artista explícito)
    if not artist:
        user_playlists = _get_user_playlists()
        if _fuzzy_match_playlist(clean, user_playlists):
            return _api_play_playlist(clean)

    if not _ensure_active_device():
        return "Por favor, abra o Spotify em algum dispositivo primeiro."

    # Caso 1: "Rap God do Eminem" → track + artist
    if track and artist:
        resp = _api_request(
            "GET",
            f"/search?q={urllib.parse.quote(f'track:{track} artist:{artist}')}&type=track&limit=1",
        )
        return _play_first_track(resp, clean) or _open_fallback(clean)

    # Caso 2: "uma música do Eminem" ou "toca a Eminem" → busca artista
    if artist or (not track and clean):
        term = artist or clean
        resp = _api_request("GET", f"/search?q={urllib.parse.quote(term)}&type=artist&limit=5")
        if resp and resp.ok:
            candidates = resp.json().get("artists", {}).get("items", [])
            best = _best_artist_match(candidates, term)
            if best:
                top_resp = _api_request("GET", f"/artists/{best['id']}/top-tracks?market=BR")
                if top_resp and top_resp.ok:
                    top = top_resp.json().get("tracks", [])
                    if top:
                        uris = [t["uri"] for t in top[:5]]
                        play_resp = _api_request("PUT", "/me/player/play", json={"uris": uris})
                        if play_resp and play_resp.status_code in (200, 204):
                            return f"Tocando {best['name']}."
        # Fallback: busca por faixa
        return _play_first_track(
            _api_request("GET", f"/search?q={urllib.parse.quote(term)}&type=track&limit=1"),
            clean,
        ) or _open_fallback(clean)

    # Caso 3: termo único — pode ser artista OU faixa
    # Busca ambos e usa similaridade de nome para decidir
    term_q = urllib.parse.quote(track)
    resp_both = _api_request("GET", f"/search?q={term_q}&type=track,artist&limit=5")
    if resp_both and resp_both.ok:
        data = resp_both.json()
        candidates = data.get("artists", {}).get("items", [])
        best_artist = _best_artist_match(candidates, track)

        if best_artist:
            from difflib import SequenceMatcher
            sim = SequenceMatcher(None, best_artist["name"].lower(), track.lower()).ratio()
            # Usa o artista se o nome for parecido o suficiente (0.5+)
            if sim >= 0.5:
                top_resp = _api_request("GET", f"/artists/{best_artist['id']}/top-tracks?market=BR")
                if top_resp and top_resp.ok:
                    top = top_resp.json().get("tracks", [])
                    if top:
                        uris = [t["uri"] for t in top[:5]]
                        play_resp = _api_request("PUT", "/me/player/play", json={"uris": uris})
                        if play_resp and play_resp.status_code in (200, 204):
                            return f"Tocando {best_artist['name']}."

        # Nome não pareceu com artista → trata como faixa
        return _play_first_track(
            _api_request("GET", f"/search?q={term_q}&type=track&limit=1"), clean
        ) or _open_fallback(clean)

    return _open_fallback(clean)


def _play_first_track(resp, fallback_query: str) -> str | None:
    import urllib.parse
    if not resp or not resp.ok:
        return None
    items = resp.json().get("tracks", {}).get("items", [])
    if not items:
        return None
    uri  = items[0]["uri"]
    name = items[0]["name"]
    artist = items[0]["artists"][0]["name"]
    play_resp = _api_request("PUT", "/me/player/play", json={"uris": [uri]})
    if play_resp and play_resp.status_code in (200, 204):
        return f"Tocando '{name}' de {artist}."
    _open_spotify_uri(uri)
    return f"Abrindo '{name}' de {artist} no Spotify."


def _open_fallback(query: str) -> str:
    import urllib.parse
    _open_spotify_uri(f"spotify:search:{urllib.parse.quote(query)}")
    return f"Abrindo busca por '{query}' no Spotify."


def _get_user_playlists() -> list[dict]:
    """Retorna todas as playlists do usuário (incluindo privadas)."""
    items = []
    resp = _api_request("GET", "/me/playlists?limit=50")
    while resp and resp.ok:
        data = resp.json()
        items.extend([p for p in data.get("items", []) if p])
        next_url = data.get("next")
        if not next_url:
            break
        resp = _api_request("GET", next_url.replace("https://api.spotify.com/v1", ""))
    return items


def _fuzzy_match_playlist(name: str, playlists: list[dict]) -> dict | None:
    """Encontra a playlist mais parecida com o nome informado."""
    import difflib
    name_lower = name.lower().strip()
    # Tenta correspondência exata primeiro
    for p in playlists:
        if p["name"].lower() == name_lower:
            return p
    # Tenta correspondência parcial
    for p in playlists:
        if name_lower in p["name"].lower() or p["name"].lower() in name_lower:
            return p
    # Fallback: difflib
    names = [p["name"] for p in playlists]
    matches = difflib.get_close_matches(name, names, n=1, cutoff=0.4)
    if matches:
        return next(p for p in playlists if p["name"] == matches[0])
    return None


def _api_play_playlist(name: str) -> str:
    import urllib.parse

    # Busca nas playlists do próprio usuário (inclui privadas)
    user_playlists = _get_user_playlists()
    match = _fuzzy_match_playlist(name, user_playlists) if user_playlists else None

    if not match:
        # Fallback: busca pública
        resp = _api_request("GET", f"/search?q={urllib.parse.quote(name)}&type=playlist&limit=5")
        if resp and resp.ok:
            results = [p for p in resp.json().get("playlists", {}).get("items", []) if p]
            match = _fuzzy_match_playlist(name, results) if results else None

    if not match:
        _open_spotify_uri(f"spotify:search:{urllib.parse.quote(name)}")
        return f"Não encontrei '{name}' nas suas playlists. Abrindo busca no Spotify."

    uri = match["uri"]
    pl_name = match["name"]

    if not _ensure_active_device():
        return "Por favor, abra o Spotify em algum dispositivo primeiro."
    play_resp = _api_request("PUT", "/me/player/play", json={"context_uri": uri})
    if play_resp and play_resp.status_code in (200, 204):
        return f"Tocando playlist '{pl_name}'."
    _open_spotify_uri(uri)
    return f"Abrindo playlist '{pl_name}' no Spotify."


def _api_pause() -> str:
    resp = _api_request("PUT", "/me/player/pause")
    if resp and resp.status_code in (200, 204):
        return "Spotify pausado."
    if resp and resp.status_code == 403:
        return "Nada está tocando para pausar."
    return "Não foi possível pausar. Verifique se o Spotify está ativo."


def _api_resume() -> str:
    resp = _api_request("PUT", "/me/player/play")
    if resp and resp.status_code in (200, 204):
        return "Spotify retomado."
    return "Não foi possível retomar. Abra o Spotify em algum dispositivo primeiro."


def _api_next() -> str:
    resp = _api_request("POST", "/me/player/next")
    if resp and resp.status_code in (200, 204):
        return "Próxima música."
    return "Não foi possível avançar. Verifique se o Spotify está ativo."


def _api_previous() -> str:
    resp = _api_request("POST", "/me/player/previous")
    if resp and resp.status_code in (200, 204):
        return "Música anterior."
    return "Não foi possível voltar. Verifique se o Spotify está ativo."


def _api_current() -> str:
    resp = _api_request("GET", "/me/player/currently-playing")
    if not resp or resp.status_code == 204:
        return "Nenhuma música tocando agora."
    item = resp.json().get("item", {})
    name = item.get("name", "?")
    artist = item.get("artists", [{}])[0].get("name", "?")
    return f"Tocando agora: '{name}' de {artist}."
