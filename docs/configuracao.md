# Referência de Configuração

Todas as configurações vivem em `core/config.yaml`. Acesse valores no código sempre via
`config.get("secao.chave", valor_default)` — nunca hardcode.

---

## `profile`

```yaml
profile:
  active: work          # work | casual | focus | meeting | night
```

Perfil ativo na inicialização. Pode ser trocado em runtime com `ativa perfil <nome>`.

---

## `wake_word`

```yaml
wake_word:
  enabled: true
  sensitivity: 0.5       # 0.0 (menos sensível) → 1.0 (mais sensível)
  keyword: "paçoca"       # cosmético — nome exibido no terminal
  model_path: ""          # caminho para .onnx customizado, ou vazio para hey_jarvis
```

Se `enabled: false`, o STT cai automaticamente em modo push-to-talk (`ctrl+shift+space`).
Treinar modelo "Paçoca": https://github.com/dscripka/openWakeWord#training

---

## `stt`

```yaml
stt:
  model: small            # tiny | base | small | medium | large
  language: pt
  device: cpu              # cpu | cuda
  auto_calibrate: true      # calibra ruído ambiente no boot do modo voz
  noise_threshold: 300      # atualizado automaticamente pela calibração
```

Modelos maiores = mais precisão, mais RAM/CPU. Em hardware modesto (4GB RAM), use `tiny` ou `base`.

---

## `ai`

```yaml
ai:
  provider: groq            # ollama | groq
  model: llama3              # llama3 | mistral | phi3 (Ollama)
  ollama_url: http://localhost:11434
  groq_model: llama-3.1-8b-instant
  groq_api_key: ""            # prefira GROQ_API_KEY no .env ou keyring
  max_tokens: 1024
  use_context: true            # injeta histórico da sessão no prompt
  auto_learn: false             # extrai fatos de cada conversa para a KB (opt-in)
  embeddings_provider: auto              # auto | gemini | ollama | none
  embeddings_model: gemini-embedding-001   # modelo Gemini (free tier)
  embeddings_ollama_model: nomic-embed-text  # requer `ollama pull nomic-embed-text`
  embeddings_api_key: ""                 # prefira GEMINI_API_KEY no .env
  system_prompt: |
    Você é Paçoca, um assistente pessoal técnico e objetivo...
```

**Resolução de API key** (`_resolve_key()` em `core/providers.py`): variável de ambiente >
keyring > YAML (com aviso de log se vier do YAML em texto puro).

**Online-first**: Groq é primário (mais rápido, sem hardware exigido); Ollama é fallback local
automático se Groq falhar 3 vezes (circuit breaker abre por 120s) ou estiver sem internet.

**Memória semântica** (`core/embeddings.py`): a base de conhecimento
(`storage/knowledge_base.py`) busca memórias por *significado*, não só por
palavra-chave — ex: perguntar "o que eu gosto de ouvir?" encontra uma memória
salva como "prefere rock e jazz", mesmo sem nenhuma palavra em comum.
- `embeddings_provider: gemini` — API gratuita do Google AI Studio
  (console.cloud.google.com/apis, crie uma chave grátis e exporte
  `GEMINI_API_KEY`). Free tier generoso, suficiente para uso pessoal.
- `embeddings_provider: ollama` — local, sem chave nova, mas requer
  `ollama pull nomic-embed-text` (modelo dedicado de embeddings, diferente do
  `ai.model` usado para chat).
- `embeddings_provider: auto` (padrão) — tenta Gemini se houver chave, senão
  Ollama, senão `none`.
- `embeddings_provider: none` — desativa; a busca volta a ser só por
  palavra-chave (comportamento de antes desta funcionalidade, zero
  configuração necessária).
- Tem circuit breaker próprio (3 falhas → 120s pausado) — se o provedor
  configurado falhar/estiver fora do ar, a busca cai automaticamente para
  palavra-chave nesse intervalo, sem travar nenhum comando.

---

## `tts`

```yaml
tts:
  enabled: true
  engine: edge              # edge | pyttsx3 | coqui
  edge_voice: pt-BR-FranciscaNeural
  rate: 175                   # só pyttsx3
  volume: 0.9
```

`edge` (Microsoft Edge TTS) é o motor padrão — vozes naturais, requer internet e
`pip install edge-tts` (não está em requirements.txt por padrão, ver [instalacao.md](instalacao.md)).
`pyttsx3` funciona 100% offline.

---

## `overlay`

```yaml
overlay:
  enabled: true
  position: top-left        # top-left | top-right | bottom-left | bottom-right
  duration_ms: 4000           # tempo de exibição de cada mensagem
  opacity: 0.92
```

Janela PyQt6 frameless, always-on-top. Histórico das últimas 3 mensagens incluído.
Atalho `ctrl+shift+a` mostra/oculta.

---

## `security`

```yaml
security:
  confirm_critical: true
  critical_commands:
    - fechar tudo
    - deletar
    - formatar
    - git push
    - git reset
    - rm -rf
  session_timeout_min: 30
  login_max_attempts: 5
  login_window_s: 60
```

Ações marcadas `⚠` em [comandos.md](comandos.md) pedem confirmação antes de executar
(`modules/security.py`).

`session_timeout_min` controla o logout automático do dashboard web por inatividade
(`web/app.py:_session_timeout_s()`) — não afeta comandos de voz/texto.

---

## `privacy`

```yaml
privacy:
  retention_days: 30      # 0 = desabilita limpeza automática
```

Limpeza automática roda em thread daemon no boot (`main.py:_schedule_data_retention`).
Comando manual: `limpa os dados antigos`. Limpa: `command_history`, `transcriptions`,
`sessions` (SQLite), arquivos em `data/transcriptions|audio|recordings`, entradas antigas
de baixa importância na knowledge base, e trunca logs > 50MB.

Quando `ai.provider: groq`, um aviso é exibido no boot informando que comandos são
enviados para a API do Groq (online). Para 100% local, use `ai.provider: ollama`.

---

## `calendar`

```yaml
calendar:
  credentials_path: core/credentials.json
  token_path: core/google_token.json
  timezone: America/Sao_Paulo
```

Token salvo com `chmod 600`. Primeira autorização: `autoriza o calendário`.

---

## `obsidian`

```yaml
obsidian:
  vault_path: ""    # ex: C:/Users/user/Documents/Obsidian/Pacoca — vazio desabilita
```

---

## `backup`

```yaml
backup:
  local_dir: data/backups
  auto_schedule: true
  daily_time: "23:30"
  google_drive:
    enabled: false
    folder_name: Paçoca Backups
    credentials_path: core/credentials.json
    token_path: core/google_token.json
```

---

## `web`

```yaml
web:
  password: ""    # vazio = dashboard sem autenticação
```

Dashboard em `http://localhost:7755`. Páginas: `/` (principal), `/metrics`,
`/integrations`, `/docs`.

**Segurança do dashboard** (`web/app.py`):
- Se `web.password` estiver vazio, o dashboard fica sem autenticação (recomendado apenas
  em localhost confiável).
- Login (`/login`) tem rate limiting configurável: `security.login_max_attempts`
  tentativas por IP a cada `security.login_window_s` segundos (padrão: 5 a cada 60s).
- Sessão expira por inatividade após `security.session_timeout_min` (padrão 30min) e
  redireciona para `/login`.
- Requisições HTMX que alteram estado (ex: editar rotinas, apagar histórico) exigem o
  header `X-CSRF-Token`, validado contra um token gerado uma vez por processo
  (`_CSRF_TOKEN`). A página injeta o token automaticamente via `hx-headers`.

---

## `logging`

```yaml
logging:
  level: INFO       # DEBUG | INFO | WARNING | ERROR
  file: logs/pacoca.log
  max_mb: 10
```

---

## `profiles` (comportamento por perfil)

```yaml
profiles:
  work:
    tts_rate: 175
    tts_volume: 0.9
    response_style: technical
    startup_routine: work_mode
  casual: { tts_rate: 160, response_style: friendly }
  focus:  { tts_rate: 150, response_style: concise }       # máx 2 frases
  meeting:{ tts_rate: 145, response_style: formal }
  night:  { tts_rate: 155, tts_volume: 0.5 }
```

---

## `routines`

```yaml
routines:
  work_mode:
    name: "Modo trabalho"
    steps:
      - action: open_app
        target: code
      - action: notify
        message: "Modo trabalho ativado."
```

Ações disponíveis: `open_app`, `notify`, `set_volume`, `focus`, `daily_report`,
`save_transcriptions`, `close_overlay`. Editável pelo dashboard (`/`) ou
`python main.py --edit-routines`.

---

## Variáveis de ambiente (`.env`)

| Variável | Uso |
|---|---|
| `GROQ_API_KEY` | Chave da API Groq (preferida sobre YAML) |
| `GROQ_MODEL` | Sobrescreve `ai.groq_model` |
| `GEMINI_API_KEY` | Chave da API Gemini — habilita memória semântica (`ai.embeddings_provider: gemini`) |
| `PACOCA_CONFIG_PATH` | Caminho customizado para config.yaml |
| `HF_TOKEN` | Necessário só para speaker diarization (pyannote.audio) |
