# Changelog

Todas as mudanças notáveis do projeto Paçoca são documentadas aqui.
Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

---

## [Não lançado]

### Adicionado
- **Janela de desktop** (`output/overlay.py`, mesmo módulo/API pública de
  antes — todos os call sites existentes continuam funcionando) — quando
  `overlay.enabled: true` (padrão), abre uma interface completa: histórico
  de conversa, caixa de texto para digitar comandos, botão de microfone
  (captura um comando de voz único via `input.stt.listen_once()`) e botão de
  conta Google (reusa o OAuth já existente de Calendar/Drive). Quando
  `enabled: false` (ou `--no-overlay`), nada muda — roda só por texto/voz no
  terminal, como antes desta funcionalidade. Toda interação roda em thread
  de fundo e some pela mesma fila thread-safe que já existia, sem travar a
  janela durante chamadas ao Groq/Ollama. Validado abrindo a janela de
  verdade (screenshot) e despachando um comando real de ponta a ponta
- `position`/`duration_ms`/`opacity` de `overlay.*` não têm mais efeito (a
  janela agora é uma janela normal centralizada, sem fade nem fechamento
  automático) — mantidos no config por compatibilidade, documentado em
  `docs/configuracao.md`

### Corrigido
- **`cleanup_old_entries()` (storage/knowledge_base.py) nunca removia nada.**
  A query filtrava por uma coluna `created_at` que não existe na tabela
  `memories` (só existe `updated_at`) — toda chamada levantava
  `sqlite3.OperationalError`, mascarado por um `except Exception: return 0`.
  Corrigido para filtrar por `updated_at`. Validado: memória de baixa
  importância e desatualizada agora é removida de fato; memórias importantes
  ou recentes são preservadas

### Adicionado
- **`update_calendar_event`** — remarca data/hora e/ou renomeia um evento
  existente (busca por título, mesma desambiguação do delete: nunca altera
  se houver mais de um resultado). Fecha o CRUD completo do calendário no
  loop agentivo: criar, ler, editar, apagar. Validado criando, remarcando e
  apagando um evento real na agenda
- **`delete_calendar_event`** — apaga/cancela evento do Google Calendar por
  título (busca por trecho, sem diferenciar maiúsculas/minúsculas). Nunca
  apaga se houver mais de um evento correspondente — lista as opções e pede
  pra ser específico. Requer confirmação explícita (ação destrutiva/
  irreversível), tanto na rota direta de voz ("apaga o evento X") quanto no
  loop agentivo. Validado apagando eventos de teste reais
- **Convidados em eventos de calendário** — `create_event()`/`add_event()`
  agora aceitam `attendees` (e-mails); `add_event()` extrai e-mails
  mencionados na frase automaticamente (ex: "reunião com x@y.com"). O Google
  Calendar envia o convite por e-mail de verdade quando há convidados.
  Validado com um evento real de teste entre duas contas próprias

### Corrigido (encontrados testando criação de evento real, com convite)
- **Data errada quando o pedido usava expressões fora de 'hoje'/'amanhã'.**
  "marca uma reunião pra depois de amanhã" criava o evento para *amanhã*
  (1 dia errado) — o LLM não sabia a data de hoje, então não conseguia
  calcular "depois de amanhã" como data exata, e `_resolve_day()` só entende
  'hoje'/'amanhã'/AAAA-MM-DD literalmente, caindo silenciosamente no padrão
  ("amanhã") para qualquer outra coisa. Agora o prompt do loop agentivo
  informa a data atual e instrui o modelo a sempre calcular AAAA-MM-DD
  exato para qualquer dia que não seja literalmente hoje/amanhã. Validado:
  "depois de amanhã" (16/06) agora cria corretamente em 18/06, antes caía em 17/06
- **Título do evento perdia maiúsculas internas.** `.capitalize()` forçava
  todo o título para minúsculo exceto a 1ª letra — `"[TESTE] Reunião com a
  Paçoca"` virava `"[teste] reunião com a paçoca"`. Trocado por uma
  capitalização que só garante a 1ª letra maiúscula sem tocar no resto
- **Ferramentas de Google Calendar no loop agentivo** — `get_calendar_events`,
  `get_next_calendar_event` e `create_calendar_event` agora estão disponíveis
  para o LLM via tool-calling (antes só existiam como rotas diretas de
  regex; o agente não sabia que podia marcar reuniões). `create_event()`
  (novo, em `modules/calendar_integration.py`) recebe campos estruturados
  (`title`, `day`, `time`) em vez do parser por regex usado pela rota de voz
  — o LLM já normaliza datas/horários melhor do que regex

### Corrigido (encontrado via teste real com GROQ_API_KEY)
- **O modelo ignorava erros reais de ferramentas e inventava sucesso.**
  Testando `create_calendar_event` sem `google-api-python-client` instalado,
  a ferramenta retornou corretamente "Instale: pip install ..." — mas o LLM,
  no turno seguinte, ignorou esse erro e respondeu "Reunião marcada com
  sucesso!". Reforçado o prompt base do loop agentivo para se ater
  estritamente ao conteúdo real do resultado da ferramenta e nunca afirmar
  sucesso quando o resultado indica erro/falha. Validado com chamadas reais
  ao Groq antes e depois da correção
- **`run_agentic_loop()` mentia ter completado ações que falharam.** Quando a
  chamada ao Groq falhava com `tool_use_failed` (o modelo formata a chamada
  de ferramenta errado — medido empiricamente: acontece em ~80% das vezes em
  alguns comandos, ex: "marca uma reunião pra mim"), o código desistia após 1
  tentativa e pedia uma resposta final sem ferramentas — e o LLM, sem saber
  que nada foi executado, respondia "Reunião marcada" mesmo sem ter chamado
  nenhuma ferramenta. Agora: (1) `tool_use_failed` tem retry automático (até
  3 tentativas — resolve sozinho na maioria das vezes, já que é falha de
  amostragem do modelo, não indisponibilidade real); (2) se mesmo assim
  nenhuma ferramenta for executada, o prompt final instrui o modelo a admitir
  isso e pedir esclarecimento em vez de fingir sucesso
- **`tool_use_failed` (400) contava como falha real do Groq no circuit
  breaker** (`core/providers.py:_groq_raw`), podendo abrir o circuito e
  empurrar a IA para Ollama por 120s só por causa de um erro de formatação do
  modelo, não uma indisponibilidade de verdade. Novo helper
  `_is_tool_use_failed()` exclui esse caso específico do circuit breaker

### Adicionado
- **Memória semântica** — `storage/knowledge_base.py` agora busca memórias por
  significado, não só por palavra-chave (ex: "o que eu gosto de ouvir?" agora
  encontra uma memória salva como "prefere rock e jazz", mesmo sem nenhuma
  palavra em comum). Novo `core/embeddings.py` com dois backends gratuitos:
  Gemini (API REST, `GEMINI_API_KEY`) e Ollama local (`nomic-embed-text`),
  modo `auto` (padrão) escolhe entre eles, e `none` desativa — cai de volta
  para a busca por palavra-chave de antes, sem nenhuma configuração extra
  necessária. Circuit breaker próprio, independente do do Groq
- Testes para `core/embeddings.py` e `storage/knowledge_base.py` (módulo não
  tinha nenhum teste antes)

### Corrigido
- Modelo padrão de embeddings Gemini era `text-embedding-004` — testado com
  chave real e descoberto que o Google descontinuou esse modelo; trocado para
  `gemini-embedding-001` (3072 dimensões, confirmado funcionando)
- Limiar de similaridade semântica (`_MIN_SIMILARITY`) estava em `0.35`,
  calibrado sem dados reais. Medido com a API real do Gemini: frases
  totalmente não-relacionadas em PT-BR já ficam em ~0.55-0.65 de similaridade
  de cosseno (piso de ruído alto, típico de embeddings de frase) — um limiar
  de 0.35 deixava passar memórias irrelevantes em toda busca. Recalibrado
  para `0.55` com base em testes ponta-a-ponta reais
- **README.md desatualizado em vários pontos**: anunciava `v1.0.0` "Lançado" com
  links de download (`Pacoca-Setup.exe`, `.zip`) para uma release que não existe
  no GitHub (confirmado: nenhuma release publicada); badge de testes dizia "73
  passing" (são 222); TTS estava documentado como só `pyttsx3` (o padrão atual é
  `edge-tts`); roadmap listava "síntese de voz neural" e "testes para web/app.py"
  como pendentes, já implementados. Versão do banner em `main.py` atualizada de
  v0.5.0 para v0.6.0 para bater com o `CHANGELOG`
- **Cookie de sessão do dashboard** (`pacoca_token`) deixou de ser um hash estático
  da senha (`sha256(senha)`, válido para sempre e compartilhado por todos os
  clientes via um único relógio global em memória) e passou a ser um cookie
  assinado (HMAC-SHA256) com timestamp de emissão embutido: cada sessão expira
  pela própria idade, sem depender de estado global, e reiniciar o servidor
  invalida sessões antigas (a chave de assinatura é gerada por processo)
- `_intent_dispatch()` (core/orchestrator.py) retorna um `IntentResult`
  (NamedTuple) em vez de uma tupla posicional de 4 elementos com um sentinel
  `_empty` duplicado em dois pontos do código
- `modules/intent.py` parou de reimplementar seu próprio cache TTL
  (`_intent_cache` com `time.time()`) e passou a reusar `_TTLCache` de
  `core/providers.py`, a mesma classe usada pelo cache de clima/finanças/busca
- `modules/spotify_ctrl.py:_api_request()` parou de duplicar a chamada HTTP em
  dois blocos quase idênticos (antes/depois do refresh de token 401) e passou a
  reusar `_retry_http()` de `core/providers.py`, ganhando de graça o backoff
  exponencial para 429/502/503 que já existia para Groq/Ollama
- WebSocket do dashboard (`/ws/command`, `/ws/events`) só checava a expiração de
  sessão na conexão inicial — uma conexão aceita antes do timeout continuava
  processando comandos/eventos indefinidamente mesmo após a sessão expirar.
  Agora a expiração é reavaliada periodicamente dentro do loop (no ritmo do
  heartbeat, para não reabrir `config.yaml` a cada 0.3s) e comandos reais via
  `/ws/command` renovam a sessão como qualquer requisição HTTP

### Adicionado
- **Segurança do dashboard web** — rate limiting de login (5 tentativas/60s por IP),
  expiração de sessão por inatividade (`security.session_timeout_min`) e token CSRF
  sincronizado para requisições htmx que alteram estado
- Testes para `core/providers.py`, `core/telemetry.py` e endpoints web
  (`tests/test_providers.py`, `tests/test_telemetry.py`, `tests/test_web_endpoints.py`)

### Corrigido
- Documentação (`docs/`) atualizada para refletir `security.session_timeout_min`,
  pool de conexões HTTP compartilhado e as proteções do dashboard web
- CI (`.github/workflows/tests.yml`) agora roda em matriz `windows-latest` +
  `ubuntu-latest` (antes só Windows) e usa Python 3.10 (antes 3.9), alinhado com o
  requisito de compatibilidade Windows/Linux do projeto
- **`dispatch_chain()`** não ficava mais mudo: quando uma parte do comando
  encadeado era respondida via streaming (TTS já falado) e outra não, a fala da
  parte não-streamada era descartada por engano — agora cada parte fala
  individualmente o que ainda não foi dito
- **WebSocket do dashboard** (`/ws/command`, `/ws/events`) agora respeita
  `security.session_timeout_min` na conexão — antes só validava o token,
  ignorando a expiração de sessão que já valia para as rotas HTTP
- `POST /api/integrations/test/{name}` passou a exigir o token CSRF, como as
  demais rotas que alteram estado
- Circuit breaker e sessão HTTP compartilhada (`core/providers.py`) agora usam
  `threading.Lock` — havia uma corrida de dados possível entre o loop de voz/texto
  e o dashboard web acessando o mesmo estado concorrentemente
- `_login_attempts` (rate limit de login) não acumula mais entradas de IPs que
  nunca mais voltaram a tentar logar
- Limites de rate limiting de login (`security.login_max_attempts`,
  `security.login_window_s`) agora são configuráveis via `config.yaml` em vez de
  hardcoded

---

## [0.6.0] — 2026-06-15

### Adicionado
- **`core/providers.py` centralizado** — cliente HTTP único para Groq/Ollama/clima/
  finanças/busca, com circuit breaker (3 falhas → pausa 120s), retry exponencial
  para 429/502/503, cache TTL em memória (`_TTLCache`) e truncamento de contexto
  (`_truncate_messages`, limite de 24k chars)
- **`core/telemetry.py`** — registro por comando (rota, ferramenta, provedor,
  latência, tokens, sucesso, fallback), exposto em `/api/metrics` e `/metrics`
- **NLU de 3 camadas** (regex → TF-IDF → LLM agentic loop) com `ToolRegistry` em
  `modules/tools.py`
- Aviso de privacidade no boot quando `ai.provider: groq` está ativo

### Alterado
- Renaming geral de "axiom" para "Paçoca" em módulos internos
- Tokens OAuth (Spotify, Google Calendar) salvos com `chmod 600`

---

## [0.5.0] — 2026-05-08

### Alterado
- **Groq substitui Anthropic** como fallback cloud de IA — gratuito, sem cartão, OpenAI-compatible; `GROQ_API_KEY` (console.groq.com); modelo padrão `llama3-8b-8192`

### Adicionado
- **73 testes** (eram 36): `test_dispatch_chain.py`, `test_reminders.py`, `test_context.py`
- **WebSocket no dashboard** — endpoint `/ws/command` para respostas instantâneas; `/ws/events` para push em tempo real (lembretes, reuniões)
- **Editor visual de rotinas** no dashboard — CRUD com htmx, persistido no `config.yaml`
- **Autenticação no dashboard** — middleware de cookie + página de login; ativado por `web.password` no config
- **Scripts de instalação reescritos** — `setup.bat` / `setup.sh` usam `requirements.txt`, criam diretórios, rodam testes e baixam llama3
- **Build como executável** — `axiom.spec` (PyInstaller) + `build.bat` / `build.sh`
- `hooks/` — diretório requerido pelo `axiom.spec`

### Corrigido
- `web_server.py` — senha lida do `orchestrator.config` em vez de criar nova instância de Config
- `web_server.py` — variável `_server_orc` adicionada para persistir referência do orchestrator
- `main.py` — versão corrigida de `v0.1.0-alpha` para `v0.5.0`
- `.github/workflows/tests.yml` — Python atualizado para 3.9; adicionados `google-auth`, `fastapi`, `uvicorn` ao CI

### Removido
- Diretório órfão `{core,input,modules,output,storage,logs,data` (criado acidentalmente)

---

## [0.4.0] — 2026-05-08

### Adicionado
- **Dashboard web local** (FastAPI + htmx, porta 7755) com `--web` flag
- **Exportação para Obsidian** — transcrições, sumários, nota diária, anotações com frontmatter YAML
- **Comandos encadeados** — `dispatch_chain()` com conectores naturais ("e depois", "em seguida", "então") e detecção automática via "e"
- **Detector de reunião automático** — monitora Zoom/Teams/Slack/Webex via psutil; ativa perfil meeting e transcrição
- **TTS profile-aware** — rate e volume do TTS sincronizados ao trocar perfil por voz
- `web/app.py`, `web/__init__.py`, `modules/web_server.py`, `modules/meeting_detector.py`, `modules/obsidian.py`
- `_CHAIN_SEP`, `_CHAIN_AND`, `_matches_route()`, `_sync_tts_profile()` no orchestrator
- `TTS.set_volume()` em `output/tts.py`
- Seções `obsidian` e `web` no `config.yaml`
- `fastapi`, `uvicorn[standard]` como deps opcionais no `requirements.txt`

---

## [0.3.0] — 2026-05-07

### Adicionado
- **Memória contextual** — ring buffer (deque, maxlen=10) injetado no prompt do LLM; `storage/context.py`
- **Lembretes por voz** — horário absoluto ("às 15h") e relativo ("em 30 min"); `modules/reminders.py`
- **Clipboard por voz** — copiar texto/último resultado, ler e limpar; `modules/clipboard_tools.py`
- **OCR de tela** — `lê o texto na tela`, `salva screenshot`; `modules/screen_reader.py`
- **Multi-idioma STT** — troca PT/EN/ES/FR/DE/IT por voz; `switch_language()` em `input/stt.py`
- **Sumário de reunião estruturado** — 5 seções: resumo executivo, decisões, action items, pendências, próximos passos
- **Sumário de sessão** — `summarize_session()` gera bullet points do contexto atual

---

## [0.2.0] — 2026-05-07

### Adicionado
- **Calibração automática de ruído** — VAD por energia RMS; `calibrate()` e `_rms()` em `input/stt.py`
- **5 perfis dinâmicos** — work / casual / focus / meeting / night; `core/profiles.py` com singleton
- **Google Calendar** — ver agenda, próximo evento, criar evento por voz; `modules/calendar_integration.py`
- **Plugin system** — auto-scan de `plugins/`; hot-reload por voz; `core/plugin_loader.py`
- **Plugin de anotações** — `plugins/notes.py`; template em `plugins/_template.py`
- **Speaker diarization** — `pyannote.audio`; identificação de `[Falante 1]`, `[Falante 2]`…

---

## [0.1.0] — 2026-05-06

### Adicionado
- Boot completo com `core/logger.py`, `storage/db.py`, `modules/productivity.py`
- Modo texto e modo voz (push-to-talk `ctrl+shift+space`; wake word opcional via Porcupine)
- Overlay flutuante PyQt6 — estado (idle / listening / processing / speaking), histórico, fade animado
- Transcrição mic + loopback (WASAPI/PulseAudio) com auto-save a cada 5 min
- Dev tools: git por voz, abrir arquivo, ir para linha, explicar código via IA
- Pomodoro, relatório diário, rotinas com condições em YAML
- Backup local + Google Drive (OAuth)
- CI/CD com GitHub Actions (`tests.yml`)
