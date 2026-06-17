# Paçoca — Prompt de desenvolvimento para Claude Code

## Contexto do projeto

Você está trabalhando no **Paçoca**, um assistente pessoal de desktop estilo Jarvis,
desenvolvido em Python 3.10+, 100% open-source e gratuito.

O projeto pertence ao repositório: https://github.com/AthirsonLamonato/Pacoca
Desenvolvido por: Athy (AthirsonLamonato)

---

## Uso mínimo de tokens

Prioridade máxima: gastar o mínimo de tokens possível sem perder qualidade.

Regras:
- Não leia o projeto inteiro sem necessidade.
- Antes de abrir vários arquivos, use busca/listagem para localizar só os arquivos relevantes.
- Evite respostas longas.
- Resuma raciocínio; não explique o óbvio.
- Não cole arquivos inteiros na resposta.
- Mostre apenas trechos relevantes de código.
- Faça uma tarefa por vez.
- Antes de implementar algo grande, proponha um plano curto.
- Evite refactors amplos se uma correção pequena resolver.
- Não rode análises profundas sem pedido explícito.
- Use contexto já descoberto em vez de reler tudo.
- Ao finalizar, responda com: resumo, arquivos alterados, testes, próximos passos.

### Formato padrão de resposta

1. Resumo curto
2. Arquivos tocados
3. O que mudou
4. Testes/validação
5. Próximo passo sugerido

### Objetivos do projeto

- estabilidade
- rapidez na entrega
- evitar regressões
- manter código limpo

### Sempre seguir

1. Entender antes de alterar
2. Explicar plano curto
3. Implementar em etapas pequenas
4. Rodar testes/lint
5. Revisar diff final

### Ao investigar bugs

- encontrar causa raiz
- medir impacto
- preferir correção mínima
- evitar refactor sem necessidade

### Política de escolha de modelo

- Sonnet = padrão
- Opus = problemas complexos
- Haiku = tarefas simples

### Durante análises, procurar (somente quando pedido explicitamente)

- bugs silenciosos
- gargalos
- code smells
- dívida técnica
- melhorias de arquitetura
- novas features úteis

## Filosofia de implementação

Sempre prefira:
- solução simples > arquitetura perfeita
- patch pequeno > refactor grande
- código existente > abstrações novas

Evite:
- criar classes desnecessárias
- introduzir patterns complexos sem necessidade
- modularizar prematuramente

## Budget de tokens

Assuma que tokens custam dinheiro real.

Antes de qualquer análise:
1. Pergunte: preciso mesmo abrir esse arquivo?
2. Prefira grep/search
3. Evite scans recursivos desnecessários

Nunca:
- analisar arquivos >500 linhas sem motivo
- reler arquivos já analisados
- rodar análise completa do repo sem pedido

## Incerteza

Se não tiver certeza:
- diga explicitamente
- não invente comportamento de arquivos não lidos
- peça contexto mínimo necessário

## Prioridades de produto

Ao sugerir features, priorize:

1. automação
2. produtividade
3. UX rápida
4. baixo custo operacional
5. funcionamento offline/local-first

---

## O que já existe (estrutura base implementada)

Estrutura real atual (raiz do repo, sem pasta `axiom/` — o projeto chama-se **Paçoca** em todo lugar):

```
Pacoca/
├── main.py                    # entry point (--mode, --profile, --no-tts, --no-overlay)
├── setup_wizard.py            # wizard de instalação (GUI tkinter, gera config.yaml/credenciais)
├── pacoca.spec / wizard.spec  # specs PyInstaller (build.sh / build.bat)
├── requirements*.txt          # full / minimal / voice
│
├── core/
│   ├── orchestrator.py        # roteador central (ROUTES regex → módulo:função) + loop agentivo
│   ├── config.py              # carregador YAML com notação de pontos
│   ├── config.yaml            # toda a configuração do projeto
│   ├── profiles.py            # perfis work / casual
│   ├── providers.py           # resolução de provider de IA (ollama/groq/anthropic)
│   ├── embeddings.py          # cache semântico / NLU camada 2
│   ├── telemetry.py           # registro de métricas de comando
│   ├── plugin_loader.py       # carrega plugins/ dinamicamente
│   └── logger.py              # logging rotativo em arquivo
│
├── input/                     # stt.py, hotkeys.py, cli.py
├── output/                    # tts.py, overlay.py, notifier.py
├── storage/                   # db.py, file_store.py, context.py, memory.py, knowledge_base.py
├── web/                       # app.py — dashboard web (Flask) do Paçoca
├── plugins/                   # plugins externos (ROUTES próprias), ex: notes.py
│
├── modules/                   # cada módulo expõe funções `def acao(*_) -> str`
│   ├── system_control.py, dev_tools.py, productivity.py, routines.py
│   ├── summarizer.py, search.py, intent.py, semantic_router.py
│   ├── tools.py               # ToolRegistry (schemas Pydantic, risco, confirmação) p/ loop agentivo
│   ├── whatsapp.py            # envio de mensagens via WhatsApp Web (pywhatkit) + whitelist
│   ├── briefing.py, learner.py, habits.py, anaphora.py, trust.py
│   ├── calendar_integration.py, spotify_ctrl.py, weather.py, finance.py
│   ├── meeting_detector.py, transcription.py, backup.py, security.py
│   └── reminders.py, obsidian.py, clipboard_tools.py, screen_reader.py
│
├── docs/                      # comandos.md, configuracao.md, instalacao.md, troubleshooting.md, ...
└── tests/                     # pytest — um arquivo por módulo (tests/test_*.py)
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

## Status do desenvolvimento

As FASES 1-7 originais (boot, STT, overlay, transcrição de reuniões, dev tools,
rotinas/produtividade, refinamentos como testes e CI) já foram concluídas.
O roadmap vivo do projeto (versões v0.1 a v0.6+, com o que foi entregue em cada
uma) fica em **`README.md` → seção "Roadmap"** — atualize lá, não aqui, para
evitar duplicação. Use `git log` e `CHANGELOG.md` para o histórico detalhado.

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

---

## Observações importantes

- **Nunca** instalar dependências pagas ou que exijam cartão de crédito
- **Sempre** verificar compatibilidade Windows + Linux antes de implementar
- **Sempre** usar `config.get()` para qualquer valor configurável
- **Sempre** retornar `str` nas funções públicas dos módulos
- O projeto deve rodar em hardware modesto (4GB RAM, CPU sem GPU)
- Ollama com modelo `llama3` é o LLM padrão — garantir que o código funciona sem internet
