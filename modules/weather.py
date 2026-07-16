"""
modules/weather.py — Consulta de clima via wttr.in (sem API key)
"""

import logging
import re
import urllib.parse

logger = logging.getLogger(__name__)


def get_weather(location: str = "") -> str:
    """Retorna previsão do tempo para a cidade informada (cache 10 min)."""
    from core.providers import _weather_cache, cached_get

    location = re.sub(r'\s*\b(?:hoje|amanhã|amanha|agora|essa?\s+semana|nessa?\s+semana)\b.*$', '', location, flags=re.IGNORECASE)
    location = location.strip().rstrip("?.,!")
    if not location:
        location = _get_default_location()

    def _fetch():
        return _fetch_weather(location)

    return cached_get(_weather_cache, f"weather:{location}", _fetch) or f"Não consegui obter o clima de {location}."


def _fetch_weather(location: str) -> str:
    import requests
    try:
        # Formato completo (3 linhas) para resposta falada
        url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1&lang=pt"
        resp = requests.get(url, timeout=8, headers={"User-Agent": "curl/7.0"})
        if not resp.ok:
            return f"Não consegui obter o clima de {location}."

        data = resp.json()
        current = data["current_condition"][0]
        area    = data["nearest_area"][0]
        city    = area["areaName"][0]["value"]
        country = area["country"][0]["value"]

        temp_c   = current["temp_C"]
        feels    = current["FeelsLikeC"]
        humidity = current["humidity"]
        desc     = current["lang_pt"][0]["value"] if current.get("lang_pt") else current["weatherDesc"][0]["value"]
        wind_kmh = current["windspeedKmph"]

        # Previsão para hoje
        today = data["weather"][0]
        max_c = today["maxtempC"]
        min_c = today["mintempC"]

        return (
            f"Em {city}, {country}: {desc}. "
            f"{temp_c}°C agora, sensação de {feels}°C. "
            f"Mínima {min_c}°C, máxima {max_c}°C. "
            f"Umidade {humidity}%, vento {wind_kmh} km/h."
        )

    except Exception as e:
        logger.warning("Erro ao consultar clima: %s", e)
        # Fallback: formato simples
        try:
            simple = requests.get(
                f"https://wttr.in/{urllib.parse.quote(location)}?format=3&lang=pt",
                timeout=6, headers={"User-Agent": "curl/7.0"}
            )
            if simple.ok:
                return simple.text.strip()
        except Exception:
            pass
        return f"Não consegui obter o clima de {location} agora."


def _get_default_location() -> str:
    """Tenta descobrir a cidade pelo IP."""
    try:
        import requests
        r = requests.get("https://ipinfo.io/json", timeout=4)
        if r.ok:
            return r.json().get("city", "Brasil")
    except Exception:
        pass
    return "Brasil"
