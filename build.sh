#!/usr/bin/env bash
set -e

echo ""
echo "[Paçoca] Compilando executável para Linux..."
echo ""

# Instalar PyInstaller se necessário
if ! pip3 show pyinstaller &>/dev/null; then
    echo "[1/3] Instalando PyInstaller..."
    pip3 install pyinstaller
else
    echo "[1/3] PyInstaller já instalado."
fi

# Criar pasta hooks se não existir
mkdir -p hooks

# Compilar
echo ""
echo "[2/3] Compilando (pode levar alguns minutos)..."
pyinstaller pacoca.spec --clean --noconfirm

# Copiar dados em runtime
echo ""
echo "[3/3] Copiando arquivos de dados..."
mkdir -p dist/Pacoca/data dist/Pacoca/logs

echo ""
echo "════════════════════════════════════════════"
echo " Build concluído!"
echo " Executável: dist/Pacoca/Pacoca"
echo ""
echo " Para distribuir: compacte a pasta dist/Pacoca/"
echo " O binário sozinho não funciona sem as libs ao lado."
echo "════════════════════════════════════════════"
