# AXIOM — Prompt de desenvolvimento para Claude Code

## Contexto do projeto

Você está trabalhando no **Paçoca**, um assistente pessoal de desktop estilo Jarvis,
desenvolvido em Python 3.10+, 100% open-source e gratuito.

O projeto pertence ao repositório: https://github.com/AthirsonLamonato/Pacoca
Desenvolvido por: Athy (AthirsonLamonato)

---

## O que já existe (estrutura base implementada)

```
axiom/
├── main.py                    # entry point com argparse (--mode, --profile, --no-tts, --no-overlay)
├── requirements.txt
├── .gitignore
│
├── core/
│   ├── orchestrator.py        # roteador central por regex → despacha para módulos
│   ├── config.py              # carregador YAML com notação de pontos (config.get("tts.enabled"))
│   ├── config.yaml            # toda a configuração do projeto
│   ├── profiles.py            # perfis work / casual
│   └── logger.py              # logging rotativo em arquivo
│
├── input/
│   ├── stt.py                 # Whisper (faster-whisper) + wake word (openWakeWord)
│   ├── hotkeys.py             # hotkeys globais via keyboard
│   └── cli.py                 # interface de terminal interativa
│
├── modules/
│   ├── system_control.py      # abrir/fechar apps, volume, brilho, processos
│   ├── transcription.py       # transcrição em tempo real (thread separada)
│   ├── summarizer.py          # Ollama (llama3/mistral) + fallback Anthropic API
│   ├── search.py              # roteamento automático: IA local vs DuckDuckGo
│   ├── dev_tools.py           # VS Code, Git (commit/push/pull), testes, arquivos
│   ├── routines.py            # executa rotinas do config.yaml (work_mode, end_of_day)
│   ├── productivity.py        # monitoramento de tempo por app via psutil
│   ├── security.py            # confirmação de ações críticas + whitelist
│   └── backup.py              # backup local + Google Drive API
│
├── output/
│   ├── tts.py                 # pyttsx3 (padrão) ou Coqui TTS, em thread separada
│   ├── overlay.py             # janela flutuante PyQt6 sempre visível
│   └── notifier.py            # notificações desktop via plyer
│
└── storage/
    ├── db.py                  # SQLite: histórico de comandos, sessões, transcrições
    └── file_store.py          # persistência de transcrições e resumos em Markdown
```

---

## Stack tecnológica

| Funcionalidade     | Ferramenta                        |
|--------------------|-----------------------------------|
| STT                | faster-whisper (Whisper base)     |
| Wake word          | openWakeWord (sem API key)         |
| LLM local          | Ollama (llama3 / mistral / phi3)  |
| LLM cloud fallback | Groq API (free tier, llama3)      |
| TTS                | pyttsx3 / Coqui TTS               |
| Busca web          | duckduckgo-search                 |
| Overlay            | PyQt6                             |
| Backup nuvem       | Google Drive API                  |
| Monitoramento      | psutil + ActivityWatch            |
| Banco de dados     | SQLite (storage/db.py)            |
| Config             | YAML (core/config.yaml)           |

---

## Padrões de código que DEVEM ser seguidos

### 1. Imports lazy nos módulos
Todos os módulos usam import lazy para não quebrar o boot se uma dependência estiver ausente:
```python
def _get_config():
    from core.config import Config
    return Config()
```

### 2. Interface pública dos módulos
Cada módulo expõe funções de nível superior que o orchestrator chama diretamente:
```python
# O orchestrator chama assim:
# "modules.transcription:start" → transcription.start()
def start(*_) -> str:
    ...
def stop(*_) -> str:
    ...
```
Funções sempre retornam `str` com a resposta para o usuário.

### 3. Rotas no orchestrator
Novas funcionalidades devem ser registradas em `core/orchestrator.py` na lista `ROUTES`:
```python
ROUTES: list[tuple[str, str, bool]] = [
    # (padrão regex, "modulo:funcao", requer_confirmacao)
    (r"meu comando (.+)", "modules.meu_modulo:minha_funcao", False),
]
```

### 4. Config via YAML
Nunca hardcode valores. Use sempre:
```python
config.get("secao.chave", valor_default)
```
E adicione a chave correspondente em `core/config.yaml`.

### 5. Logging
```python
import logging
logger = logging.getLogger(__name__)
logger.info("mensagem")
logger.error("erro", exc_info=True)
```

### 6. Compatibilidade Windows/Linux
```python
import platform
OS = platform.system()  # "Windows" | "Linux" | "Darwin"
if OS == "Windows":
    ...
elif OS == "Linux":
    ...
```

---

## O que ainda precisa ser desenvolvido (por fase)

### FASE 1 — Fazer o projeto rodar (prioridade máxima)

- [ ] **Testar e corrigir o boot completo** em `python main.py --mode text`
- [ ] **Verificar todas as importações** — garantir que nenhum import quebra no boot
- [ ] **Integrar `storage/db.py`** no `main.py` (chamar `db.init()` no startup)
- [ ] **Integrar `core/logger.py`** no `main.py` (chamar `setup_logging(config)` antes de tudo)
- [ ] **Integrar `modules/productivity.py`** no startup (`productivity.start_tracking()`)
- [ ] **Inicializar overlay** no `main.py` se `overlay.enabled = true`
- [ ] **Escrever testes básicos** para `core/config.py`, `core/orchestrator.py` e `storage/db.py`
  - Usar `pytest` com fixtures
  - Cobrir: carregamento de config, roteamento de comandos, persistência no SQLite

### FASE 2 — STT e voz

- [ ] **Testar `input/stt.py`** com microfone real
  - Validar captura de áudio com pyaudio
  - Validar transcrição com faster-whisper modelo `base`
  - Testar wake word "paçoca" com openWakeWord (modelo customizado necessário)
- [ ] **Implementar fallback de STT**: se openWakeWord não estiver disponível (sem API key), rodar em modo "push-to-talk" com hotkey `ctrl+shift+space`
- [ ] **Calibração automática de ruído**: usar `speech_recognition.Microphone` para ajustar threshold de silêncio automaticamente
- [ ] **Indicador visual de escuta** no overlay: mostrar "ouvindo..." enquanto captura

### FASE 3 — Overlay e UX

- [ ] **Corrigir e testar `output/overlay.py`** com PyQt6
  - A janela deve ser frameless, always-on-top e transparente
  - Deve exibir mensagens com fade-in/fade-out
  - Posição configurável via `config.yaml` (top-left, top-right, bottom-left, bottom-right)
- [ ] **Adicionar estado ao overlay**: ícone/texto indicando modo atual (escutando / processando / ocioso)
- [ ] **Histórico de comandos no overlay**: últimos 3 comandos visíveis
- [ ] **Atalho para mostrar/ocultar overlay**: `ctrl+shift+a`

### FASE 4 — Transcrição de reuniões

- [ ] **Testar `modules/transcription.py`** com microfone real
- [ ] **Implementar captura de loopback** (áudio do sistema, não só microfone):
  - Windows: usar `pyaudiowpatch` para capturar WASAPI loopback
  - Linux: usar PulseAudio monitor source
- [ ] **Transcrição em tempo real com buffer**: exibir texto conforme vai sendo transcrito
- [ ] **Identificação de falantes** (speaker diarization) com `pyannote.audio` — opcional, marcar como `[Falante 1]`, `[Falante 2]`
- [ ] **Comando "mostra o que foi falado"**: exibir últimos 5 minutos de transcrição no overlay
- [ ] **Auto-save a cada 5 minutos** durante transcrição ativa

### FASE 5 — Dev tools avançados

- [ ] **Integração VS Code via extensão**: usar `code --command` para comandos avançados
- [ ] **Abrir arquivo específico por voz**: "axiom, abre o arquivo main.py"
- [ ] **Navegação de arquivos por voz**: "axiom, vai para a linha 42"
- [ ] **Git status por voz**: "axiom, o que mudou?" → retorna `git status --short`
- [ ] **Git log resumido**: "axiom, mostra os últimos commits"
- [ ] **Criar branch por voz**: "axiom, cria branch feature/nome"
- [ ] **Explicação de código via IA**: selecionar trecho no VS Code e pedir explicação

### FASE 6 — Rotinas e produtividade

- [ ] **Editor de rotinas via CLI**: `axiom --edit-routines` abre um editor interativo
- [ ] **Rotinas com condições**: executar ação só se condição for verdadeira (ex: "se for segunda-feira, abre o calendário")
- [ ] **Relatório diário automático**: ao final do dia, gerar resumo de produtividade e salvar
- [ ] **Integração com Google Calendar** (opcional): "axiom, o que tenho hoje?"
- [ ] **Timer de foco (Pomodoro)**: "axiom, foco por 25 minutos" → notifica ao fim

### FASE 7 — Refinamentos

- [ ] **Adicionar testes de integração** para fluxo completo: comando → rota → módulo → resposta
- [ ] **CI/CD com GitHub Actions**: rodar pytest automaticamente em cada push
- [ ] **Documentação de cada módulo** com docstrings completas
- [ ] **Script de instalação** (`setup.sh` e `setup.bat`) que instala dependências e baixa modelo Ollama
- [ ] **Comando "axiom, ajuda"**: lista todos os comandos disponíveis dinamicamente a partir de ROUTES

---

## Comandos para começar

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar em modo texto (sem microfone, para testar)
python main.py --mode text --no-tts --no-overlay

# Rodar com overlay mas sem TTS
python main.py --mode text --no-tts

# Rodar completo
python main.py

# Rodar testes
pytest tests/ -v
```

---

## Convenções de commit

```
feat: adiciona novo módulo de calendário
fix: corrige crash no stt quando openWakeWord não está instalado
refactor: extrai lógica de confirmação para security.py
test: adiciona testes para orchestrator
docs: atualiza README com novos comandos
chore: atualiza requirements.txt
```

---

## Prioridade de desenvolvimento

1. Fazer `python main.py --mode text` rodar sem erros
2. Todos os módulos importam sem quebrar
3. Pelo menos um comando funcionar de ponta a ponta (ex: "abre o VS Code")
4. Testes básicos passando
5. STT funcionando com microfone
6. Overlay funcionando
7. Demais fases em ordem

---

## Observações importantes

- **Nunca** instalar dependências pagas ou que exijam cartão de crédito
- **Sempre** verificar compatibilidade Windows + Linux antes de implementar
- **Sempre** usar `config.get()` para qualquer valor configurável
- **Sempre** retornar `str` nas funções públicas dos módulos
- O projeto deve rodar em hardware modesto (4GB RAM, CPU sem GPU)
- Ollama com modelo `llama3` é o LLM padrão — garantir que o código funciona sem internet
