# Paçoca — Arquitetura Técnica

## Visão geral

O Paçoca é um assistente de desktop offline-first com suporte a IA em nuvem como acelerador opcional.
O processamento de linguagem natural usa três camadas em ordem crescente de custo/latência:

```
Usuário (voz/texto)
       ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Camada 1 — Regex (<1ms, 0 rede)                                     │
│  orchestrator.py → ROUTES[] — padrões diretos sem IA                │
└────────────────────┬────────────────────────────────────────────────┘
                     │ sem match
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Camada 2 — TF-IDF local (<5ms, 0 rede)                              │
│  modules/intent.py → classify_local() → execute_actions()           │
└────────────────────┬────────────────────────────────────────────────┘
                     │ incerteza alta
                     ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Camada 3 — LLM (centenas de ms, opcional)                           │
│  Online:  Groq API → run_agentic_loop() (tool-calling)              │
│  Local:   Ollama  → parse_intent_ollama() (few-shot)                │
│  Fallback: summarizer.ask_ai() (resposta em linguagem natural)      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Componentes principais

### `core/orchestrator.py`
Roteador central. Recebe um comando de texto e:
1. Testa cada regex em `ROUTES[]` — se bate, chama o handler diretamente.
2. Passa para `_intent_dispatch()` → pipeline NLU de 3 camadas.
3. Registra telemetria em `core/telemetry.py`.
4. Atualiza overlay com estado descritivo ("Consultando Groq", "Executando spotify ctrl", etc.).

### `core/providers.py`
Cliente HTTP centralizado para todos os provedores de IA.

- **Circuit breaker**: após 3 falhas consecutivas do Groq, abre por 120s e usa Ollama.
- **Sessão compartilhada**: `requests.Session` com connection pool (4 conexões).
- **Retry exponencial**: 429/502/503 → espera e tenta novamente (máx 3 tentativas).
- **`_resolve_key()`**: env var > keyring > YAML (com aviso).
- **`_TTLCache`**: cache em memória com TTL — clima (10min), finanças (2min), busca (5min).
- **`_truncate_messages()`**: garante que o contexto não excede 24k chars, contando content + tool_calls.

### `core/telemetry.py`
Registra por comando: rota, ferramenta, provedor, latência, tokens, sucesso, fallback.
Exposto em `/api/metrics` (JSON) e `/metrics` (HTML visual).

### `core/embeddings.py`
Provedor de embeddings para memória semântica, mesmo padrão arquitetural de
`core/providers.py` (reusa `_resolve_key`, `_get_session`, `_retry_http`,
`_TTLCache`/`cached_get` por import lazy — não duplica).
- Backends: `gemini` (API REST gratuita do Google AI Studio), `ollama` (local,
  `/api/embeddings`), `auto` (tenta Gemini se houver chave, senão Ollama),
  `none` (desativa).
- Circuit breaker **próprio**, com estado separado do circuit breaker do Groq
  (3 falhas → 120s aberto) — uma falha aqui nunca afeta o roteamento Groq/Ollama
  do chat.
- `embed_text()` nunca propaga exceção — retorna `None` em qualquer falha,
  para que `storage/knowledge_base.py` sempre tenha um fallback seguro
  (busca por palavra-chave) sem try/except próprio em cada call site.
- Embeddings são armazenados como `BLOB` compactado (`array.array('f', ...)`),
  não JSON texto — ~3x menor, sem dependência de numpy.

### `modules/intent.py`
Pipeline NLU de 3 camadas:
1. `classify_local()`: TF-IDF com cache de comandos (TTL 300s, via `_TTLCache` de
   `core/providers.py` — mesma classe usada pelo cache de clima/finanças/busca).
2. `run_agentic_loop()`: Groq com tool-calling (seleção de ferramenta → execução → resposta natural).
3. `parse_intent_ollama()`: Groq alternativa que força Ollama (evita dupla chamada ao Groq no fallback).

`_intent_dispatch()` (orchestrator) retorna um `IntentResult` (NamedTuple:
`response, provider, tool, fallback_used`) em vez de uma tupla posicional solta.

### `output/overlay.py`
Janela de desktop do Paçoca (PyQt6) — quando `overlay.enabled: true`, é a
interface gráfica completa: histórico de conversa, caixa de texto, botão de
microfone (captura um comando único via `input.stt.listen_once()`) e botão
de conta Google (reusa `modules.calendar_integration.auth_calendar()`).
Quando desabilitada, o Paçoca roda só por texto/voz no terminal.

Thread-safe via `queue.Queue` + `QTimer` — toda interação (texto digitado,
clique no microfone, login Google) dispara uma thread em background que
chama `Orchestrator.dispatch_chain()` (injetado via `set_orchestrator()`,
chamado por `main.py` depois que o orchestrator é criado) e devolve a
resposta pela mesma queue, nunca tocando widgets fora da thread do Qt.
- `set_state(state)`: estados simples (idle/listening/processing/speaking).
- `set_state_detail(state, detail)`: rótulo descritivo, ex: `"processing", "Consultando Groq"`.

### `output/tts.py`
Text-to-speech com suporte a streaming:
- `speak(text)`: fala em thread separada (não bloqueia).
- `speak_stream(generator)`: consome um gerador, quebrando em frases e falando cada uma. Permite feedback auditivo durante streaming do LLM.

---

## Fluxo de dados (online-first)

```
Comando
  → Groq (primeira tentativa)
      ↓ falha 3x
  → Circuit breaker abre (120s)
      → Ollama (fallback local)
          ↓ indisponível
      → Resposta de erro

Telemetria:
  record_command(route, provider, tool, latency_s, fallback_used)
  record_llm_call(provider, latency_s, tokens)
```

---

## Privacidade e segurança

| Item | Implementação |
|------|---------------|
| Chaves de API | env var > keyring > YAML (com aviso se YAML) |
| Tokens OAuth | chmod 600 ao salvar (Spotify, Google Calendar) |
| Dados externos | Aviso no boot quando `ai.provider=groq` com GROQ_API_KEY |
| Retenção | `privacy.retention_days` em config.yaml (padrão: 30 dias) |
| Logs | Sanitizados: `Authorization: Bearer ***` nunca aparece |
| Sessão do dashboard | Cookie assinado (HMAC-SHA256) com timestamp de emissão embutido — expira por idade própria, sem depender de um relógio global compartilhado; chave de assinatura é gerada por processo, então reiniciar o servidor invalida sessões antigas (`web/app.py:_make_session_cookie()`) |

---

## Dependências opcionais vs obrigatórias

| Dependência | Obrigatória? | Sem ela |
|-------------|-------------|---------|
| `requests` | Sim | Sem IA, clima, finanças |
| `scikit-learn` | Sim | Sem NLU camada 2 (TF-IDF) |
| `pydantic>=2.0` | Sim | Sem validação de args de ferramentas |
| `schedule` | Sim | Sem backup automático |
| `keyring` | Não | Chaves só via env var ou YAML |
| `PyQt6` | Não | Sem overlay visual |
| `pyttsx3`/`edge-tts` | Não | Sem resposta por voz |
| `faster-whisper` | Não | Sem STT (use `--mode text`) |
| Ollama | Não | Sem IA local (usa só Groq) |
| GROQ_API_KEY | Não | Usa só Ollama local |

---

## Adicionando novos módulos

1. Crie `modules/meu_modulo.py` com funções públicas retornando `str`.
2. Registre em `core/orchestrator.py` na lista `ROUTES`:
   ```python
   (r"meu padrão (.+)", "modules.meu_modulo:minha_funcao", False),
   ```
3. Use imports lazy para não quebrar o boot:
   ```python
   def minha_funcao(arg: str) -> str:
       from core.config import Config
       config = Config()
       ...
   ```
4. Qualquer valor configurável vai em `core/config.yaml` e é lido via `config.get("secao.chave", default)`.
