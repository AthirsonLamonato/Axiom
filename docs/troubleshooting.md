# Troubleshooting / FAQ

> Problemas comuns ao instalar ou rodar o Paçoca, e como resolver.

---

## Boot e instalação

**`ModuleNotFoundError` ao rodar `python main.py`**

Algum import pesado não está protegido por lazy import, ou uma dependência opcional
não foi instalada. Rode primeiro o modo mínimo para isolar o problema:

```bash
python main.py --mode text --no-tts --no-overlay
```

Se isso funcionar, o problema é uma dependência opcional (TTS, overlay, voz). Veja
[instalacao.md](instalacao.md#6-recursos-opcionais) para o pacote certo.

**`FileNotFoundError: core/config.yaml`**

Você está rodando o comando de um diretório diferente da raiz do projeto. Sempre
execute `python main.py` a partir da raiz do repositório (onde está `core/`).

**Erro de `pyaudio` no Windows ao instalar `requirements-voice.txt`**

`pyaudio` precisa do PortAudio compilado. Use `pipwin install pyaudio` ou baixe a
wheel pré-compilada (veja [instalacao.md](instalacao.md#4-modo-voz-stt--wake-word)).

---

## STT / voz

**Wake word não detecta "paçoca"**

Por padrão o openWakeWord usa o modelo `hey_jarvis` (não existe modelo treinado para
"paçoca" ainda). Ou treine um modelo customizado, ou desative `wake_word.enabled` no
`config.yaml` e use push-to-talk (`ctrl+shift+space`).

**Microfone não é detectado / transcrição vazia**

1. Confirme que o microfone correto está selecionado no SO.
2. Teste captura crua com `python -c "import pyaudio; pyaudio.PyAudio().get_default_input_device_info()"`.
3. Verifique se `faster-whisper` baixou o modelo (~150MB na primeira execução) — sem
   internet na primeira vez, o download falha silenciosamente.

**Transcrição do sistema (loopback) não captura nada**

- Windows: precisa de `pyaudiowpatch` instalado.
- Linux: confirme que existe um dispositivo `*.monitor` no PulseAudio
  (`pactl list sources short | grep monitor`).

---

## LLM / IA (Groq, Ollama)

**Respostas da IA muito lentas ou nunca chegam**

Veja [performance.md](performance.md#latência-de-llm) para diagnóstico de latência
por etapa do pipeline.

**`circuit breaker aberto` / Groq não responde por 2 minutos**

Isso é esperado: após 3 falhas consecutivas na API da Groq, o `core/providers.py`
abre um circuito por 120s para não martelar uma API instável, e usa Ollama (se
disponível) como fallback automático. Se você não tem Ollama instalado, a IA local
simplesmente não responde durante esse intervalo — instale Ollama para ter fallback
100% offline.

**`GROQ_API_KEY` configurada mas erro de autenticação**

Confirme que a chave está no `.env` na raiz do projeto (não em `core/.env`), e que
não há aspas ou espaços extras: `GROQ_API_KEY=gsk_...`.

**Quero rodar 100% offline, sem nenhuma chamada de rede**

No `core/config.yaml`, defina `ai.provider: ollama`. Isso desativa o fallback para
Groq. Confirme que `ollama serve` está rodando e que o modelo (`ollama pull llama3`)
já foi baixado.

---

## Janela de desktop

**Fechei a janela pelo X e o Paçoca continua rodando em segundo plano**

Comportamento esperado. A janela tem barra de título agora (diferente do
overlay flutuante antigo), mas fechá-la só oculta — não mata o processo.
Reabra com `ctrl+shift+a` ou dizendo "abre o overlay".

**A caixa de texto/botão "Enviar" ficaram cinza por alguns segundos**

Esperado — ficam desabilitados enquanto o comando é processado (chamada ao
Groq/Ollama), pra evitar enviar vários comandos em cima do outro. Reabilitam
quando a resposta chega.

**Cliquei no microfone e nada aconteceu**

Captura um único comando (até 8s) — fale logo após clicar. Se as
dependências de voz (`faster-whisper`, `pyaudio`) não estiverem instaladas,
a resposta no histórico vai dizer isso explicitamente.

**Botão de conta Google não mostra o e-mail conectado**

Por padrão, só mostra "Conectado"/"Não conectado" — não busca o e-mail da
conta, porque isso exigiria um escopo OAuth novo (`email`/`profile`) que o
projeto não solicita hoje (só Calendar + Drive).

---

## Dashboard web

**`/login` retorna 429 "Muitas tentativas"**

Rate limiting: máximo de 5 tentativas de senha por IP em 60 segundos. Espere um
minuto e tente novamente. Se você esqueceu a senha, ela está em
`config.get("web.password")` (ou variável de ambiente, conforme sua config) —
edite `core/config.yaml` diretamente se necessário.

**Sessão desloga sozinha após alguns minutos**

Comportamento esperado: `security.session_timeout_min` (padrão 30 min) desloga por
inatividade. Ajuste no `config.yaml` se quiser uma sessão mais longa.

**Erro "Token CSRF inválido" ao adicionar/excluir rotina**

O token CSRF é gerado uma vez por processo do servidor. Se você reiniciou o
dashboard mas a aba do navegador continua aberta com o HTML antigo, recarregue a
página (`F5`) para receber o token atualizado.

**WebSocket fica "reconectando..." sem parar**

- Confirme que o dashboard foi iniciado (`python main.py --web`) e a porta 7755 não
  está bloqueada por firewall.
- Se você está atrás de um proxy reverso, confirme que ele suporta upgrade de
  conexão para WebSocket.

---

## Geral

**Como sei se um comando está registrado?**

Rode `python main.py --web` e acesse `http://localhost:7755/docs`, ou veja
[comandos.md](comandos.md) — ambos são gerados a partir da mesma lista `ROUTES` em
`core/orchestrator.py`.

**Onde ficam os logs?**

`logs/pacoca.log` (rotativo). Para mais detalhe, ajuste o nível de log em
`core/config.yaml` (`logging.level: DEBUG`).

**Como faço o Paçoca esquecer dados antigos (privacidade)?**

`storage/db.py:cleanup_old_data(days)` remove comandos, transcrições e arquivos
mais antigos que `days` dias. Configurável via `privacy.retention_days` no
`config.yaml` (`0` desativa a limpeza automática).
