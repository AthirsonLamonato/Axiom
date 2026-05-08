# Axiom

> Assistente pessoal inteligente de desktop — controle por voz ou texto, 100% open-source e gratuito.

![Version](https://img.shields.io/badge/version-v0.5.0-blue)
![Python](https://img.shields.io/badge/python-3.9+-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Tests](https://img.shields.io/badge/tests-73%20passing-brightgreen)
![CI](https://github.com/AthirsonLamonato/Axiom/actions/workflows/tests.yml/badge.svg)

Axiom é um assistente de desktop estilo Jarvis — modular, expansível e capaz de rodar completamente offline em hardware modesto (4 GB RAM, CPU sem GPU).

---

## Funcionalidades implementadas

| Módulo | O que faz |
|---|---|
| **STT** | Transcrição via Whisper (`faster-whisper`). Calibração automática de ruído no boot; VAD inteligente por energia RMS. Push-to-talk (ctrl+shift+space) por padrão; wake word via Porcupine se `access_key` configurada |
| **Overlay** | Janela flutuante PyQt6 sempre visível: indicador de estado (idle / listening / processing / speaking), histórico dos últimos 3 comandos, fade animado. Toggle: ctrl+shift+a |
| **Transcrição** | Captura microfone ou loopback do sistema (Windows: WASAPI · Linux: PulseAudio). Auto-save a cada 5 min |
| **Resumo / IA** | Resumo e explicações via Ollama (local) com fallback para Anthropic API |
| **Pesquisa** | Roteamento automático: perguntas factuais/atuais → DuckDuckGo + IA; demais → LLM local |
| **Dev tools** | VS Code, abrir arquivo por nome, ir para linha, criar arquivo, git status/log/commit/push/pull/branch, rodar testes, explicar código via IA |
| **Rotinas** | Sequências configuráveis em YAML com condições (weekday, weekend, morning, afternoon, evening) |
| **Pomodoro** | Timer de foco com notificação e overlay ao término |
| **Produtividade** | Monitoramento de apps via psutil, relatório diário em Markdown |
| **Sistema** | Abrir/fechar apps, volume, brilho, listar processos (Windows + Linux) |
| **Segurança** | Confirmação antes de ações críticas, lista configurável |
| **Backup** | Local automático + Google Drive (opcional, requer OAuth) |
| **Perfis** | work / casual / focus / meeting / night — alteráveis por voz em tempo real |
| **Google Calendar** | Ver agenda do dia, próximo evento, adicionar eventos por voz |
| **Calibração STT** | Calibração automática de ruído no boot + comando por voz |
| **Speaker diarization** | Identifica falantes na transcrição (`[Falante 1]`, `[Falante 2]`…) — requer pyannote.audio |
| **Plugin system** | Carregamento dinâmico de módulos em `plugins/`. Plugin de anotações incluído. Hot-reload por voz |
| **Memória contextual** | Histórico da sessão injetado no prompt do LLM para respostas coerentes |
| **Lembretes** | Notificações agendadas por voz — horário absoluto ou relativo |
| **Clipboard** | Copiar texto/último resultado, ler e limpar área de transferência por voz |
| **OCR de tela** | Lê texto visível na tela via pytesseract. Salva screenshots |
| **Multi-idioma STT** | Troca o idioma de reconhecimento por voz (PT, EN, ES, FR, DE…) |
| **Sumário de reunião** | Sumário estruturado com resumo executivo, decisões, action items e pendências |
| **Dashboard web** | Interface local (FastAPI + htmx) em `localhost:7755` — histórico, lembretes, envio de comandos |
| **Obsidian** | Exporta transcrições, sumários e nota diária para qualquer vault Markdown |
| **Comandos encadeados** | "abre o VS Code e depois foco por 25 min" — múltiplos comandos em sequência |
| **Modo reunião auto** | Detecta Zoom/Teams/Slack via psutil; ativa perfil meeting e transcrição automaticamente |
| **TTS profile-aware** | Rate e volume do TTS sincronizados ao trocar perfil |
| **Banco de dados** | SQLite — histórico de comandos, sessões e transcrições |
| **TTS** | pyttsx3 (offline, leve) ou Coqui TTS (mais natural) |

---

## Instalação rápida

### Windows

```bat
git clone https://github.com/AthirsonLamonato/Axiom.git
cd Axiom
setup.bat
```

### Linux / Mac

```bash
git clone https://github.com/AthirsonLamonato/Axiom.git
cd Axiom
bash setup.sh
```

### Manual

```bash
pip install -r requirements.txt
ollama pull llama3   # baixa o modelo de IA local (~4 GB)
```

---

## Executar

```bash
# Modo texto — ideal para testar sem microfone
python main.py --mode text --no-tts --no-overlay

# Modo texto com overlay
python main.py --mode text --no-tts

# Modo voz (push-to-talk por padrão)
python main.py

# Editor de rotinas
python main.py --edit-routines

# Dashboard web (abre o browser em localhost:7755)
python main.py --web

# Somente o dashboard, sem modo voz
python main.py --mode text --no-tts --no-overlay --web
```

---

## Comandos disponíveis

### Sistema
```
abre o VS Code
abre o Chrome
fecha o Spotify
volume 70
aumenta o brilho / diminui o brilho
muta o som
lista processos
```

### Transcrição
```
começa a transcrever
começa a transcrever o sistema        ← loopback (áudio do speaker)
para a transcrição
mostra o que foi falado
```

### IA e pesquisa
```
resume o que foi falado
resumo detalhado
explica o que é recursão
pesquisa como funciona decorators em Python
busca na internet o clima de amanhã
```

### Dev tools
```
abre o arquivo main.py
vai para a linha 42
cria arquivo utils.py
explica o arquivo orchestrator.py
commit "feat: nova funcionalidade"
git push / git pull
o que mudou                           ← git status
mostra os últimos commits             ← git log
cria branch feature/nome
branch atual
roda os testes
novo terminal
```

### Rotinas e produtividade
```
modo trabalho
modo foco
fim do dia
executa rotina end_of_day
foco por 25 min                       ← timer Pomodoro
cancela o timer
status do timer
mostra o tempo de uso
relatório de produtividade
relatório diário
```

### Perfis dinâmicos
```
perfil trabalho / perfil work
perfil casual
perfil foco / perfil focus
perfil reunião / perfil meeting
perfil noturno / perfil noite
qual perfil                           ← perfil atual
lista perfis                          ← todos os perfis disponíveis
```

### Google Calendar
```
o que tenho hoje / agenda hoje
próximo evento / próximo compromisso
adiciona reunião amanhã às 14h
adiciona dentista hoje às 10h30
autoriza calendário                   ← primeira autenticação OAuth
```

### Speaker diarization
```
identifica falantes                   ← roda após parar a transcrição
diariza falantes
```

### Plugins
```
lista plugins                         ← plugins carregados e rotas
recarrega plugins                     ← hot-reload sem reiniciar
```

### Anotações (plugin incluso)
```
anota reunião com João amanhã às 10h
minhas anotações
busca nas anotações reunião
limpa anotações
```

### Lembretes
```
me lembra às 15h de reunião
me lembra em 30 minutos de fazer backup
me lembra às 9h30 de tomar remédio
lista lembretes
cancela lembrete 2
cancela lembretes                     ← cancela todos
```

### Clipboard
```
copia o último resultado
copia Python é incrível para o clipboard
lê a área de transferência
lê o clipboard
limpa o clipboard
```

### OCR / Tela
```
lê o texto na tela
lê a tela
lê a região central
salva screenshot
```

### Idioma do STT
```
muda para inglês
muda para espanhol
muda para francês
idioma atual
```

### Contexto e sessão
```
mostra o contexto                     ← histórico da sessão
limpa o contexto                      ← reinicia memória contextual
resume a sessão                       ← bullet points do que foi feito
resume a reunião                      ← sumário estruturado com action items
```

### STT / Microfone
```
calibra o microfone                   ← recalibra o limiar de ruído
recalibra o mic
```

### Dashboard web
```
abre o dashboard                      ← inicia o servidor web e abre o browser
inicia a interface web
para o servidor web / fecha o dashboard
```

### Obsidian / exportação
```
exporta a transcrição para o obsidian
exporta o sumário para o obsidian
cria a nota diária / atualiza a nota diária
exporta as notas para o obsidian
```

### Detector de reunião automático
```
ativa o detector de reunião           ← monitora Zoom, Teams, Slack…
desativa o detector de reunião
status do detector
```

### Comandos encadeados
```
abre o VS Code e depois foco por 25 min
começa a transcrever e então ativa o detector de reunião
para a transcrição e em seguida exporta o sumário para o obsidian
```

### Overlay e meta
```
abre o overlay / fecha o overlay      ← ou ctrl+shift+a
ajuda                                 ← lista todos os comandos
```

---

## Configuração

Edite `core/config.yaml`:

```yaml
# Wake word (deixe vazio para push-to-talk)
wake_word:
  access_key: ""          # PICOVOICE_ACCESS_KEY — obtenha em picovoice.ai
  keyword: porcupine      # keywords gratuitas: porcupine, jarvis, computer…

# IA local
ai:
  provider: ollama        # ollama | anthropic
  model: llama3           # llama3 | mistral | phi3

# Overlay
overlay:
  enabled: true
  position: top-right     # top-left | top-right | bottom-left | bottom-right

# TTS
tts:
  enabled: true
  engine: pyttsx3         # pyttsx3 | coqui
```

### Anthropic como fallback (opcional)

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Linux/Mac
set ANTHROPIC_API_KEY=sk-ant-...      # Windows
```

Em `config.yaml`: `ai.provider: anthropic`

### Google Drive para backup (opcional)

1. Crie um projeto em [Google Cloud Console](https://console.cloud.google.com)
2. Ative a Drive API e baixe `credentials.json`
3. Coloque em `core/credentials.json`
4. Em `config.yaml`: `backup.google_drive.enabled: true`

### Plugins

Coloque qualquer arquivo `.py` em `plugins/` e ele será carregado automaticamente no próximo boot (ou via `"recarrega plugins"`). Cada plugin deve declarar `NAME`, `VERSION`, `DESCRIPTION` e `ROUTES`. Use `plugins/_template.py` como ponto de partida.

```yaml
plugins:
  enabled: true
  directory: plugins
```

### Dashboard web (opcional)

```bash
pip install fastapi "uvicorn[standard]"
python main.py --web        # ou diga "abre o dashboard"
```

Para proteger o dashboard com senha, defina em `config.yaml`:

```yaml
web:
  password: "sua_senha"    # deixe vazio para sem autenticação
```

Acesse `/logout` para sair da sessão.

### Obsidian / exportação de notas (opcional)

```yaml
obsidian:
  vault_path: C:/Users/seu_usuario/Documents/ObsidianVault/Axiom
```

### Google Calendar (opcional)

1. No mesmo projeto do Google Cloud Console, ative a **Calendar API**
2. Baixe o `credentials.json` (OAuth 2.0) e coloque em `core/credentials.json`
3. Execute o comando de voz `"autoriza calendário"` — o browser abre para login
4. O token é salvo em `core/calendar_token.json` e renovado automaticamente

```yaml
calendar:
  credentials_path: core/credentials.json
  token_path: core/calendar_token.json
  timezone: America/Sao_Paulo
```

---

## Estrutura do projeto

```
Axiom/
├── main.py                    # entry point — argparse, boot completo
├── setup.bat / setup.sh       # scripts de instalação
├── requirements.txt
│
├── core/
│   ├── orchestrator.py        # roteador regex → módulos + plugins
│   ├── plugin_loader.py       # escaneia plugins/ e injeta rotas
│   ├── config.py              # carregador YAML com notação de pontos
│   ├── config.yaml            # configuração central
│   ├── profiles.py            # perfis work / casual / focus / meeting / night
│   └── logger.py              # logging rotativo em arquivo
│
├── input/
│   ├── stt.py                 # Whisper + wake word / push-to-talk + calibração de ruído
│   ├── hotkeys.py             # atalhos globais
│   └── cli.py                 # interface de terminal
│
├── modules/
│   ├── system_control.py      # apps, volume, brilho, processos
│   ├── transcription.py       # mic + loopback, auto-save
│   ├── summarizer.py          # Ollama + fallback Anthropic
│   ├── search.py              # roteamento IA local vs DuckDuckGo
│   ├── dev_tools.py           # VS Code, Git, arquivos, testes
│   ├── routines.py            # rotinas YAML com condições
│   ├── productivity.py        # monitoramento, Pomodoro, relatórios
│   ├── security.py            # confirmação de ações críticas
│   ├── backup.py              # backup local + Google Drive
│   ├── calendar_integration.py # Google Calendar — agenda, próximo evento, criar evento
│   ├── reminders.py           # lembretes agendados por voz
│   ├── clipboard_tools.py     # copiar/ler área de transferência por voz
│   ├── screen_reader.py       # OCR de tela via pytesseract
│   ├── meeting_detector.py    # detecta videochamadas via psutil
│   ├── obsidian.py            # exporta notas/transcrições para vault Markdown
│   └── web_server.py          # inicia o servidor do dashboard web
│
├── output/
│   ├── tts.py                 # pyttsx3 / Coqui TTS
│   ├── overlay.py             # overlay PyQt6 thread-safe
│   └── notifier.py            # notificações desktop
│
├── storage/
│   ├── db.py                  # SQLite — histórico e sessões
│   ├── file_store.py          # transcrições e resumos em Markdown
│   └── context.py             # memória contextual de sessão (ring buffer)
│
├── web/
│   ├── __init__.py
│   └── app.py                 # FastAPI app com htmx — dashboard local
│
├── plugins/                   # plugins externos (carregados automaticamente)
│   ├── notes.py               # anotações rápidas (plugin incluso)
│   └── _template.py           # template para criar novos plugins
│
└── tests/                     # 36 testes (pytest)
    ├── test_config.py
    ├── test_db.py
    ├── test_orchestrator.py
    ├── test_stt.py
    └── test_dev_tools.py
```

---

## Stack tecnológica

| Funcionalidade | Ferramenta | Tipo |
|---|---|---|
| Speech-to-Text | faster-whisper (Whisper base) | Local / offline |
| Wake word | pvporcupine (free tier) | Local / offline |
| LLM | Ollama (llama3 / mistral / phi3) | Local / offline |
| LLM cloud | Anthropic API (claude-haiku) | Opcional / pago |
| TTS | pyttsx3 / Coqui TTS | Local / offline |
| Busca web | duckduckgo-search | Gratuito |
| Overlay | PyQt6 | Open-source |
| Monitoramento | psutil | Open-source |
| Banco de dados | SQLite | Open-source |
| Backup nuvem | Google Drive API | Gratuito |
| Google Calendar | Google Calendar API (OAuth 2.0) | Gratuito |
| Dashboard web | FastAPI + htmx + uvicorn | Open-source / opcional |
| Config | PyYAML | Open-source |

---

## Testes

```bash
python -m pytest tests/ -v
```

36+ testes cobrindo: config, orchestrator (roteamento), banco de dados, STT e dev tools.

CI automático via GitHub Actions em cada push para `main` e `dev`.

---

## Roadmap

### v0.1 — Base (concluído)
- [x] Boot completo com logger, db e produtividade
- [x] Modo texto e modo voz (push-to-talk)
- [x] Overlay flutuante com estado e histórico
- [x] Transcrição mic + loopback + auto-save
- [x] Dev tools: git por voz, abrir arquivo, explicar código
- [x] Pomodoro, relatório diário, rotinas com condições
- [x] CI/CD com GitHub Actions

### v0.2 — Concluído
- [x] Calibração automática de ruído para o microfone
- [x] Integração com Google Calendar
- [x] Modos de perfil dinâmicos via voz (focus, meeting, night + aliases PT)
- [x] Plugin system — carregamento dinâmico de `plugins/`, hot-reload por voz
- [x] Speaker diarization (`pyannote.audio`) — identificação de falantes (opcional, requer HF_TOKEN)

### v0.3 — Concluído
- [x] Memória contextual — histórico da sessão injetado no prompt do LLM (configurável)
- [x] Notificações agendadas por voz — "me lembra às 15h de reunião" / "em 30 min"
- [x] Clipboard por voz — copiar texto/último resultado, ler e limpar área de transferência
- [x] OCR de tela — "lê o texto na tela" e "salva screenshot" via pytesseract + Pillow
- [x] Troca de idioma STT por voz — "muda para inglês", "muda para espanhol" etc.
- [x] Sumário de reunião aprimorado — seções: resumo executivo, decisões, action items, pendências
- [x] Sumário da sessão — "resume a sessão" gera bullet points do que foi feito

### v0.4 — Concluído
- [x] Interface web local (FastAPI + htmx) — dashboard de histórico, lembretes, contexto e comandos
- [x] Exportação para Obsidian — transcrições, sumários, nota diária e anotações com frontmatter YAML
- [x] Comandos encadeados — separadores naturais: "e depois", "em seguida", "então" + "e" com detecção
- [x] Modo reunião automático — detecta Zoom/Teams/Slack/Webex via psutil; ativa perfil e transcrição
- [x] TTS profile-aware — rate e volume sincronizados ao trocar perfil por voz
- [x] `--web` flag — inicia o dashboard ao subir o assistente

### v0.5 — Concluído
- [x] 73 testes — cobertura para dispatch_chain, reminders e context
- [x] Dashboard WebSocket — resposta de comandos instantânea + push de eventos em tempo real
- [x] Editor visual de rotinas no dashboard (htmx CRUD, persistido no config.yaml)
- [x] Autenticação no dashboard — middleware + cookie + página de login (`web.password`)
- [x] Scripts de instalação reescritos — `setup.bat` / `setup.sh` com requirements.txt
- [x] Build como executável — `axiom.spec` + `build.bat` / `build.sh` (PyInstaller)

### v0.6 — Próximo
- [ ] Síntese de voz neural — Coqui TTS com modelo PT-BR
- [ ] Integração com Notion — exportar notas/transcrições
- [ ] Streaming de resposta do LLM — tokens em tempo real no dashboard
- [ ] Testes para web/app.py (endpoints, WebSocket mockado, CRUD de rotinas)
- [ ] Síntese de voz aprimorada — vozes neurais via Coqui TTS com modelo PT-BR

---

## Contribuição

1. Fork o repositório
2. Crie um módulo em `modules/` seguindo o padrão: funções públicas retornam `str`, use lazy imports
3. Registre as rotas em `core/orchestrator.py`
4. Adicione testes em `tests/`
5. Abra um Pull Request para `dev`

---

## Licença

MIT License — veja [LICENSE](LICENSE)

---

## Autor

Desenvolvido por [Athy (AthirsonLamonato)](https://github.com/AthirsonLamonato)
