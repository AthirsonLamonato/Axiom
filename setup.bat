@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo.
echo  ██████╗ ██╗  ██╗██╗ ██████╗ ███╗   ███╗
echo ██╔══██╗╚██╗██╔╝██║██╔═══██╗████╗ ████║
echo ███████║ ╚███╔╝ ██║██║   ██║██╔████╔██║
echo ██╔══██║ ██╔██╗ ██║██║   ██║██║╚██╔╝██║
echo ██║  ██║██╔╝ ██╗██║╚██████╔╝██║ ╚═╝ ██║
echo ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝     ╚═╝
echo.
echo  Instalador do Axiom para Windows
echo ════════════════════════════════════════════
echo.

:: Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale Python 3.9+ em python.org
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% encontrado.

:: Instalar dependencias principais
echo.
echo [1/5] Instalando dependencias Python (requirements.txt)...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas.

:: Dashboard web (opcional mas recomendado)
echo.
echo [2/5] Instalando dashboard web (FastAPI + uvicorn)...
pip install fastapi "uvicorn[standard]"
echo [OK] Dashboard web disponivel.

:: Criar diretorios de dados
echo.
echo [3/5] Criando diretorios...
for %%d in (data data\transcriptions data\backups data\screenshots logs plugins) do (
    if not exist "%%d" mkdir "%%d"
)
echo [OK] Diretorios criados.

:: Executar testes
echo.
echo [4/5] Verificando instalacao (testes)...
python -m pytest tests/ -q --tb=no 2>nul
if errorlevel 1 (
    echo [AVISO] Alguns testes falharam. Execute 'python -m pytest tests/ -v' para detalhes.
) else (
    echo [OK] Todos os testes passaram.
)

:: Ollama (opcional)
echo.
echo [5/5] Modelo de IA local (Ollama)...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Ollama nao encontrado.
    echo         Para usar IA local, instale em: https://ollama.com
    echo         Apos instalar, execute: ollama pull llama3
) else (
    echo Ollama encontrado. Baixando modelo llama3 (~4 GB)...
    echo (Pressione Ctrl+C para pular)
    ollama pull llama3
    echo [OK] Modelo llama3 pronto.
)

echo.
echo ════════════════════════════════════════════
echo  Instalacao concluida!
echo.
echo  Para iniciar:
echo    python main.py --mode text --no-tts      (teste sem microfone)
echo    python main.py --web                     (com dashboard web)
echo    python main.py                           (modo completo com voz)
echo.
pause
