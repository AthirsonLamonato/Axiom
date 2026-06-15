"""
modules/finance.py — Cotações de moedas e criptomoedas em tempo real
Usa AwesomeAPI (gratuita, sem chave, dados do Banco Central do Brasil).
"""

import logging
import re

logger = logging.getLogger(__name__)

# Normalização de nomes para código de moeda
_CURRENCY_MAP = {
    "dólar": "USD", "dolar": "USD", "usd": "USD", "dollar": "USD",
    "euro": "EUR", "eur": "EUR",
    "libra": "GBP", "gbp": "GBP",
    "iene": "JPY", "yen": "JPY", "jpy": "JPY",
    "bitcoin": "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH",
    "peso": "ARS", "peso argentino": "ARS", "ars": "ARS",
    "dólar canadense": "CAD", "cad": "CAD",
    "franco suíço": "CHF", "chf": "CHF",
    "yuan": "CNY", "cny": "CNY",
}

_AMOUNT_RE = re.compile(
    r'(?:quanto[s]?\s+(?:é|sao|são|vale[m]?|custa[m]?)\s+)?'
    r'([\d]+(?:[.,]\d+)?)\s*'
    r'(dólar(?:es)?|dolar(?:es)?|euro[s]?|libra[s]?|bitcoin[s]?|btc|usd|eur|gbp)\s*'
    r'(?:em\s+reais?|para\s+reais?|em\s+brl)?',
    re.IGNORECASE,
)


def get_quote(currency_name: str) -> str:
    """Retorna a cotação atual de uma moeda em reais (cache 2 min)."""
    from core.providers import _finance_cache, cached_get

    currency_name = currency_name.strip().lower()
    code = _resolve_code(currency_name)
    if not code:
        return f"Não reconheço a moeda '{currency_name}'. Tente: dólar, euro, bitcoin, libra."

    def _fetch():
        return _fetch_quote(currency_name, code)

    return cached_get(_finance_cache, f"quote:{code}", _fetch) or f"Não consegui a cotação de {currency_name}."


def _fetch_quote(currency_name: str, code: str) -> str:
    import requests
    try:
        pair = f"{code}-BRL"
        resp = requests.get(
            f"https://economia.awesomeapi.com.br/json/last/{pair}",
            timeout=6,
        )
        if not resp.ok:
            return f"Não consegui obter a cotação de {currency_name} agora."

        data = resp.json().get(f"{code}BRL", {})
        bid  = float(data.get("bid", 0))
        ask  = float(data.get("ask", 0))
        pct  = float(data.get("pctChange", 0))
        name = data.get("name", currency_name.title())

        arrow = "▲" if pct >= 0 else "▼"
        return (
            f"{name}: R$ {bid:.2f} (compra) / R$ {ask:.2f} (venda). "
            f"Variação: {arrow} {abs(pct):.2f}% hoje."
        )

    except Exception as e:
        logger.warning("Erro ao consultar cotação: %s", e)
        return f"Não consegui obter a cotação de {currency_name} agora."


def convert(text: str) -> str:
    """Converte um valor de moeda para reais. Ex: '100 dólares em reais'."""
    import requests

    m = _AMOUNT_RE.search(text.lower())
    if not m:
        # Tenta extrair só a moeda para cotação simples
        code_name = re.sub(r'(?:quanto[s]?\s+(?:é|vale[m]?|custa[m]?|sao|são)\s+(?:um|o|a)\s+)', '', text, flags=re.IGNORECASE).strip()
        return get_quote(code_name)

    amount_str = m.group(1).replace(",", ".")
    currency_name = m.group(2)
    amount = float(amount_str)
    code = _resolve_code(currency_name.lower())
    if not code:
        return f"Moeda não reconhecida: {currency_name}"

    try:
        resp = requests.get(
            f"https://economia.awesomeapi.com.br/json/last/{code}-BRL",
            timeout=6,
        )
        if not resp.ok:
            return "Não consegui obter a cotação agora."
        bid = float(resp.json().get(f"{code}BRL", {}).get("bid", 0))
        total = amount * bid
        return f"{amount_str} {currency_name} = R$ {total:,.2f} (cotação: R$ {bid:.2f})."
    except Exception as e:
        logger.warning("Erro na conversão: %s", e)
        return "Erro ao converter moeda."


def _resolve_code(name: str) -> str:
    """Resolve nome/abreviação → código ISO."""
    name = name.strip().lower().rstrip("s")  # remove plural
    for key, code in _CURRENCY_MAP.items():
        if name == key or name == key.rstrip("s"):
            return code
    # Tenta match parcial
    for key, code in _CURRENCY_MAP.items():
        if name in key or key in name:
            return code
    # Tenta como código direto (USD, EUR, BTC...)
    if re.match(r'^[A-Za-z]{3}$', name):
        return name.upper()
    return ""
