# Exemplos de Plugins

> Visão geral rápida em [desenvolvimento.md](desenvolvimento.md#criando-um-plugin-sem-editar-o-core).
> Aqui vão três exemplos completos, prontos para copiar em `plugins/`.

Plugins em `plugins/*.py` são carregados automaticamente por `core/plugin_loader.py`
no boot (e recarregáveis em runtime com o comando de voz `recarrega os plugins`).
Não é preciso editar `core/orchestrator.py`.

---

## 1. Plugin simples (sem dependências, sem config)

`plugins/piada.py` — responde com uma piada fixa.

```python
"""plugins/piada.py — conta uma piada aleatória"""

import random

NAME        = "piada"
VERSION     = "1.0.0"
DESCRIPTION = "Conta uma piada curta"

ROUTES = [
    (r"conta\s+uma\s+piada", "plugins.piada:contar", False),
]

_PIADAS = [
    "Por que o programador foi ao médico? Porque tinha um bug.",
    "O que o Python disse pro Java? Você é muito verboso.",
    "Por que o SQL terminou o namoro? Faltava JOIN.",
]


def contar(*_) -> str:
    return random.choice(_PIADAS)
```

---

## 2. Plugin com configuração própria

`plugins/cotacao.py` — busca a cotação do dólar, com URL/intervalo configuráveis via
`config.yaml`. Mostra o padrão de **lazy import** e **`config.get()`** que o resto do
projeto usa.

```python
"""plugins/cotacao.py — cotação de moedas via API pública"""

import logging

logger = logging.getLogger(__name__)

NAME        = "cotacao"
VERSION     = "1.0.0"
DESCRIPTION = "Consulta cotação de moedas (API pública, sem chave)"

ROUTES = [
    (r"cota[çc][ãa]o\s+do\s+d[óo]lar", "plugins.cotacao:dolar", False),
]


def _get_config():
    from core.config import Config
    return Config()


def dolar(*_) -> str:
    config = _get_config()
    timeout = config.get("cotacao.timeout_s", 5)
    try:
        import requests
        r = requests.get(
            "https://economia.awesomeapi.com.br/json/last/USD-BRL",
            timeout=timeout,
        )
        data = r.json()["USDBRL"]
        return f"Dólar: R$ {data['bid']} (variação do dia: {data['pctChange']}%)"
    except Exception as e:
        logger.error("Erro ao buscar cotação", exc_info=True)
        return f"Não consegui buscar a cotação agora: {e}"
```

Adicione ao `core/config.yaml` (opcional, só se quiser mudar o default):

```yaml
cotacao:
  timeout_s: 5
```

---

## 3. Plugin com múltiplas rotas e confirmação

`plugins/notas.py` — bloco de notas simples persistido em arquivo, com uma ação
destrutiva (`limpar`) marcada para exigir confirmação (3º elemento da tupla `True`).

```python
"""plugins/notas.py — bloco de notas persistente em texto simples"""

import os

NAME        = "notas"
VERSION     = "1.0.0"
DESCRIPTION = "Bloco de notas rápido (anota / lista / limpa)"

ROUTES = [
    (r"anota\s+(.+)",            "plugins.notas:anotar",  False),
    (r"(lista|mostra)\s+as\s+notas", "plugins.notas:listar",  False),
    (r"limpa\s+as\s+notas",      "plugins.notas:limpar",  True),  # pede confirmação
]

_PATH = "data/notas.txt"


def _ensure_dir():
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)


def anotar(texto: str, *_) -> str:
    _ensure_dir()
    with open(_PATH, "a", encoding="utf-8") as f:
        f.write(texto.strip() + "\n")
    return f"Anotado: {texto.strip()}"


def listar(*_) -> str:
    if not os.path.exists(_PATH):
        return "Nenhuma nota ainda."
    with open(_PATH, encoding="utf-8") as f:
        linhas = [l.strip() for l in f if l.strip()]
    if not linhas:
        return "Nenhuma nota ainda."
    return "\n".join(f"{i+1}. {l}" for i, l in enumerate(linhas))


def limpar(*_) -> str:
    if os.path.exists(_PATH):
        os.remove(_PATH)
    return "Notas limpas."
```

---

## Testando um plugin

Plugins não precisam de teste registrado em `tests/`, mas é recomendado: trate o
plugin como qualquer módulo, importando a função direto:

```python
from plugins.piada import contar

def test_contar_retorna_string():
    assert isinstance(contar(), str)
```

## Limitações conhecidas

- Plugins não passam pela camada 2/3 do NLU (TF-IDF / LLM agentic loop) — apenas
  regex direto, como módulos do core.
- Erros não tratados dentro de um plugin se propagam para o orchestrator; sempre
  capture exceções de I/O ou rede dentro da própria função do plugin.
