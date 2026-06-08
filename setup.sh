#!/usr/bin/env bash
set -e

echo ""
echo "██████╗  █████╗  ██████╗ ██████╗  ██████╗  █████╗"
echo "██╔══██╗██╔══██╗██╔════╝██╔═══██╗██╔════╝ ██╔══██╗"
echo "██████╔╝███████║██║     ██║   ██║██║      ███████║"
echo "██╔═══╝ ██╔══██║██║     ██║   ██║██║      ██╔══██║"
echo "██║     ██║  ██║╚██████╗╚██████╔╝╚██████╗ ██║  ██║"
echo "╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝"
echo ""
echo " Instalador do Paçoca — Assistente Pessoal v0.5.0"
echo "════════════════════════════════════════════════════"
echo ""
echo " Níveis de instalação:"
echo "   1 = Mínimo   — apenas modo texto (mais rápido, recomendado para testar)"
echo "   2 = Completo — TTS, overlay visual, controle de sistema"
echo "   3 = Voz      — tudo acima + reconhecimento de voz"
echo ""
read -rp "Escolha o nível [1/2/3, padrão=1]: " NIVEL
NIVEL="${NIVEL:-1}"

# ── Verificar Python ──────────────────────────────────────────────────
check_python() {
    if ! command -v python3 &>/dev/null; then
        echo "[ERRO] Python3 não encontrado. Instale Python 3.10+"
        exit 1
    fi
    PYVER=$(python3 --version 2>&1 | cut -d' ' -f2)
    echo "[OK] Python $PYVER encontrado."
    PYMAJ=$(echo "$PYVER" | cut -d'.' -f1)
    PYMIN=$(echo "$PYVER" | cut -d'.' -f2)
    if [ "$PYMAJ" -lt 3 ] || { [ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 10 ]; }; then
        echo "[AVISO] Python 3.10+ recomendado. Versão encontrada: $PYVER"
    fi
}

check_python

case "$NIVEL" in
  1)
    echo ""
    echo "[Instalação Mínima]"
    echo "Suficiente para: python3 main.py --mode text --no-tts --no-overlay"
    echo ""
    echo "[1/3] Instalando dependências mínimas..."
    pip3 install -r requirements-minimal.txt
    echo "[OK] Dependências instaladas."
    ;;
  2)
    echo ""
    echo "[Instalação Completa]"
    echo "Inclui: TTS, overlay PyQt6, controle de sistema."
    echo ""
    echo "[1/3] Instalando dependências completas..."
    pip3 install -r requirements.txt
    echo "[OK] Dependências instaladas."
    ;;
  3)
    echo ""
    echo "[Instalação com Voz]"
    echo ""
    echo "[1/4] Instalando dependências base..."
    pip3 install -r requirements.txt
    echo "[OK] Dependências base instaladas."

    echo ""
    echo "[2/4] Instalando pyaudio..."
    # Linux: requer portaudio19-dev
    if command -v apt-get &>/dev/null; then
        echo "Detectado apt. Instalando PortAudio via apt..."
        sudo apt-get install -y portaudio19-dev python3-pyaudio
    elif command -v brew &>/dev/null; then
        echo "Detectado Homebrew (Mac). Instalando PortAudio via brew..."
        brew install portaudio
        pip3 install pyaudio
    else
        echo "[AVISO] Gerenciador de pacotes não reconhecido."
        echo "        Instale PortAudio manualmente e depois: pip3 install pyaudio"
    fi

    echo ""
    echo "[3/4] Instalando dependências de ML (STT + wake word)..."
    pip3 install faster-whisper openwakeword || echo "[AVISO] Falha parcial — o modo voz pode não funcionar."
    echo "[OK] Dependências de voz processadas."
    ;;
  *)
    echo "[ERRO] Opção inválida. Use 1, 2 ou 3."
    exit 1
    ;;
esac

# ── Diretórios ────────────────────────────────────────────────────────
echo ""
echo "[Criando diretórios de dados...]"
mkdir -p data/transcriptions data/backups data/screenshots logs plugins
echo "[OK] Diretórios criados."

# ── Testes ────────────────────────────────────────────────────────────
echo ""
echo "[Verificando instalação (testes)...]"
if python3 -m pytest tests/ -q --tb=no 2>/dev/null; then
    echo "[OK] Todos os testes passaram."
else
    echo "[AVISO] Alguns testes falharam. Execute 'python3 -m pytest tests/ -v' para detalhes."
fi

# ── Ollama ────────────────────────────────────────────────────────────
echo ""
echo "[IA local — Ollama (opcional)]"
if ! command -v ollama &>/dev/null; then
    echo "[INFO] Ollama não encontrado."
    echo "       Para usar IA local, instale via:"
    echo "       curl -fsSL https://ollama.com/install.sh | sh"
    echo "       Depois execute: ollama pull llama3"
    echo "       Sem Ollama, o assistente usa DuckDuckGo para buscas."
else
    OLLVER=$(ollama --version 2>&1 | head -1)
    echo "[OK] Ollama encontrado ($OLLVER)."
    read -rp "Deseja baixar o modelo llama3 agora? (~4 GB) [s/N]: " BAIXAR
    if [[ "$BAIXAR" =~ ^[sS]$ ]]; then
        echo "Baixando llama3..."
        ollama pull llama3
        echo "[OK] Modelo llama3 pronto."
    else
        echo "[INFO] Pulando. Execute 'ollama pull llama3' quando quiser."
    fi
fi

# ── Resumo ────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════"
echo " Instalação concluída!"
echo ""
if [ "$NIVEL" = "1" ]; then
    echo " Para iniciar:"
    echo "   python3 main.py --mode text --no-tts --no-overlay"
elif [ "$NIVEL" = "2" ]; then
    echo " Para iniciar:"
    echo "   python3 main.py --mode text --no-tts    (sem voz, com overlay)"
    echo "   python3 main.py --mode text              (texto com TTS)"
else
    echo " Para iniciar:"
    echo "   python3 main.py --mode text --no-tts    (sem voz, com overlay)"
    echo "   python3 main.py --mode voice             (modo voz completo)"
    echo "   python3 main.py                          (modo padrão: voz)"
fi
echo "   python3 main.py --web                    (com dashboard web)"
echo ""
echo " Dica: use './run.sh' para iniciar rapidamente."
echo ""
