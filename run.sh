#!/usr/bin/env bash
set -e

echo ""
echo " Paçoca — Quick Start"
echo "══════════════════════════════════"
echo ""
echo " Modos disponíveis:"
echo "   1 = Texto simples    (sem microfone, sem TTS)   — mais leve"
echo "   2 = Texto com TTS    (sem microfone, com voz)"
echo "   3 = Texto + Overlay  (sem microfone, com janela flutuante)"
echo "   4 = Voz completo     (microfone + TTS + overlay)"
echo "   5 = Com dashboard    (adiciona interface web em localhost:7755)"
echo ""
read -rp "Escolha o modo [1-5, padrão=1]: " MODO
MODO="${MODO:-1}"

if ! command -v python3 &>/dev/null; then
    echo "[ERRO] Python3 não encontrado. Execute ./setup.sh primeiro."
    exit 1
fi

case "$MODO" in
  1) echo "Iniciando modo texto simples..."
     python3 main.py --mode text --no-tts --no-overlay ;;
  2) echo "Iniciando modo texto com TTS..."
     python3 main.py --mode text --no-overlay ;;
  3) echo "Iniciando modo texto com overlay..."
     python3 main.py --mode text --no-tts ;;
  4) echo "Iniciando modo voz completo..."
     python3 main.py --mode voice ;;
  5) echo "Iniciando com dashboard web..."
     python3 main.py --mode text --no-tts --web ;;
  *) echo "[ERRO] Opção inválida. Iniciando modo 1."
     python3 main.py --mode text --no-tts --no-overlay ;;
esac
