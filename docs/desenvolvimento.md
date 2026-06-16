# Guia de Desenvolvimento

> Arquitetura técnica completa em [ARCHITECTURE.md](../ARCHITECTURE.md).
> Este guia foca em "como adicionar coisas" no dia a dia.

---

## Adicionando um novo comando a um módulo existente

1. Escreva a função em `modules/<modulo>.py`:

```python
def minha_funcao(arg: str, *_) -> str:
    return f"Executado com {arg}"
```

Sempre retorna `str` — é a resposta que o usuário vê/ouve.

2. Registre a rota em `core/orchestrator.py`, na lista `ROUTES`:

```python
ROUTES: list[tuple[str, str, bool]] = [
    # (padrão regex, "modulo:funcao", requer_confirmacao)
    (r"meu comando (.+)", "modules.meu_modulo:minha_funcao", False),
]
```

A 3ª posição (`bool`) define se a ação pede confirmação antes de executar
(use `True` para ações destrutivas/irreversíveis).

3. Atualize `docs/comandos.md` com o novo comando.

---

## Criando um módulo novo do zero

```python
"""
modules/meu_modulo.py — descrição curta
"""

import logging

logger = logging.getLogger(__name__)


def _get_config():
    from core.config import Config
    return Config()


def minha_acao(*_) -> str:
    config = _get_config()
    valor = config.get("meu_modulo.minha_chave", "default")
    logger.info("Executando minha_acao com %s", valor)
    return f"Feito: {valor}"
```

Padrões obrigatórios:
- **Import lazy** de dependências pesadas/opcionais (não quebra o boot se faltar)
- **Sempre `config.get()`** para valores configuráveis, nunca hardcode
- **Sempre retorna `str`**
- **Compatível Windows + Linux** — use `platform.system()` quando o comportamento difere

---

## Criando um plugin (sem editar o core)

Plugins em `plugins/` são carregados automaticamente por `core/plugin_loader.py` e não
precisam de entrada em `ROUTES`. Veja `plugins/_template.py` como base:

```python
NAME        = "meu_plugin"
VERSION     = "1.0.0"
DESCRIPTION = "O que esse plugin faz"

ROUTES = [
    (r"meu comando (.+)", "plugins.meu_plugin:minha_funcao", False),
]

def minha_funcao(arg: str, *_) -> str:
    return f"Plugin executou: {arg}"
```

Comandos de voz: `lista os plugins`, `recarrega os plugins`.

---

## Pipeline NLU — quando uma regex não é suficiente

Se o comando tem muita variação de fraseado, ele cai automaticamente para a camada 2
(TF-IDF, `modules/intent.py:classify_local()`) e depois camada 3 (LLM com tool-calling,
`run_agentic_loop()`). Para registrar uma nova ferramenta no agentic loop, adicione o
schema em `modules/tools.py` (`ToolRegistry`, validação via Pydantic).

---

## Testando

```bash
pytest tests/ -v                  # tudo, exceto testes de integração
pytest tests/test_orchestrator.py -v   # um arquivo específico
pytest tests/ -v -m integration   # inclui testes que tocam Groq/Ollama reais
```

Padrão de teste: cada módulo novo deveria ter ao menos um `tests/test_<modulo>.py`
cobrindo o caminho feliz e um erro esperado (ex: dependência ausente).

---

## Circuit breaker e providers — cuidado ao tocar

`core/providers.py` tem um circuit breaker para a Groq API (3 falhas consecutivas →
pausa 120s). A função `_record_groq_failure()` deve ser chamada **apenas** dentro de
`_groq_raw()` e `_groq_stream()` — nunca em código que os chama (orchestrator,
intent.py), ou o circuito conta falhas em dobro.

---

## Dashboard web — adicionando uma página

Páginas vivem em `web/app.py` como rotas FastAPI (`@app.get(...)`). Para manter
consistência visual, copie o `<style>` block de uma página existente (`/metrics` ou
`/integrations`) e adicione o link de navegação nas outras páginas também.

---

## Checklist antes de abrir PR

- [ ] `pytest tests/ -v` passando
- [ ] Nenhum import pesado fora de função (lazy import)
- [ ] Novo comando documentado em `docs/comandos.md`
- [ ] Config nova documentada em `docs/configuracao.md` (se aplicável)
- [ ] Testado em pelo menos um SO (idealmente os dois)
