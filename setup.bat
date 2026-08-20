@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo.
echo ██████╗  █████╗  ██████╗ ██████╗  ██████╗  █████╗
echo ██╔══██╗██╔══██╗██╔════╝██╔═══██╗██╔════╝ ██╔══██╗
echo ██████╔╝███████║██║     ██║   ██║██║      ███████║
echo ██╔═══╝ ██╔══██║██║     ██║   ██║██║      ██╔══██║
echo ██║     ██║  ██║╚██████╗╚██████╔╝╚██████╗ ██║  ██║
echo ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝
echo.
echo  Instalador do Pacoca — Assistente Pessoal v0.5.0
echo ════════════════════════════════════════════════════
echo.
echo  Niveis de instalacao:
echo    [1] Minimo   — apenas modo texto ^(mais rapido, recomendado para testar^)
echo    [2] Completo — TTS, overlay visual, controle de sistema
echo    [3] Voz      — tudo acima + reconhecimento de voz ^(requer pyaudio^)
echo.
set /p NIVEL="Escolha o nivel [1/2/3]: "

if "%NIVEL%"=="" set NIVEL=1
if "%NIVEL%"=="1" goto MINIMAL
if "%NIVEL%"=="2" goto FULL
if "%NIVEL%"=="3" goto VOICE
echo [ERRO] Opcao invalida. Usando nivel 1.
set NIVEL=1
goto MINIMAL

:: ── Verificações comuns ───────────────────────────────────────────────
:CHECK_PYTHON
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERRO] Python nao encontrado.
    echo        Instale Python 3.10+ em: https://python.org/downloads
    echo        Marque "Add Python to PATH" durante a instalacao.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% encontrado.

:: Verifica versao minima (3.10+)
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    if %%a LSS 3 (
        echo [ERRO] Python 3.10+ e necessario. Versao encontrada: %PYVER%
        pause
        exit /b 1
    )
    if %%a==3 if %%b LSS 10 (
        echo [AVISO] Python 3.10+ recomendado. Versao encontrada: %PYVER%
        echo         O projeto pode nao funcionar corretamente.
    )
)
goto :EOF

:: ── Nivel 1: Minimo ───────────────────────────────────────────────────
:MINIMAL
echo.
echo [Instalacao Minima]
echo Suficiente para: python main.py --mode text --no-tts --no-overlay
echo.
call :CHECK_PYTHON
echo.
echo [1/3] Instalando dependencias minimas...
pip install -r requirements-minimal.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias. Verifique sua conexao e tente novamente.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas.
goto DIRS

:: ── Nivel 2: Completo ─────────────────────────────────────────────────
:FULL
echo.
echo [Instalacao Completa]
echo Inclui: TTS, overlay PyQt6, controle de sistema, Google Drive/Calendar.
echo.
call :CHECK_PYTHON
echo.
echo [1/3] Instalando dependencias completas...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    echo        Se o erro for no PyQt6, tente: pip install PyQt6 --pre
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas.
goto DIRS

:: ── Nivel 3: Voz ──────────────────────────────────────────────────────
:VOICE
echo.
echo [Instalacao com Voz]
echo Inclui tudo do nivel 2 + reconhecimento de voz (STT).
echo.
call :CHECK_PYTHON
echo.
echo [1/4] Instalando dependencias base...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias base.
    pause
    exit /b 1
)
echo [OK] Dependencias base instaladas.

echo.
echo [2/4] Instalando pyaudio (Windows)...
echo.
echo ATENCAO: pyaudio no Windows requer PortAudio.
echo Tentando instalar via pipwin...
pip install pipwin >nul 2>&1
pipwin install pyaudio
if errorlevel 1 (
    echo.
    echo [AVISO] pipwin falhou. Tente manualmente:
    echo   1. Acesse: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
    echo   2. Baixe a wheel compativel com seu Python (ex: PyAudio-0.2.13-cp310-win_amd64.whl)
    echo   3. Execute: pip install PyAudio-0.2.13-cp310-win_amd64.whl
    echo.
    echo Continuando sem pyaudio. O modo voz nao estara disponivel ate instalar.
)

echo.
echo [3/4] Instalando dependencias de ML (STT + wake word)...
pip install faster-whisper openwakeword
if errorlevel 1 (
    echo [AVISO] Falha ao instalar faster-whisper/openwakeword.
    echo         O modo voz nao estara disponivel.
)
echo [OK] Dependencias de voz instaladas.
goto DIRS

:: ── Diretórios + testes comuns ────────────────────────────────────────
:DIRS
echo.
echo [Criando diretorios de dados...]
for %%d in (data data\transcriptions data\backups data\screenshots logs plugins) do (
    if not exist "%%d" mkdir "%%d"
)
echo [OK] Diretorios criados.

echo.
echo [Verificando instalacao (testes)...]
python -m pytest tests/ -q --tb=no 2>nul
if errorlevel 1 (
    echo [AVISO] Alguns testes falharam.
    echo         Execute 'python -m pytest tests/ -v' para detalhes.
) else (
    echo [OK] Todos os testes passaram.
)

echo.
echo [IA local — Ollama (opcional)]...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Ollama nao encontrado.
    echo        Para usar IA local sem internet, instale em: https://ollama.com
    echo        Depois execute: ollama pull qwen3:4b
    echo        Sem Ollama, o assistente usa DuckDuckGo para buscas.
) else (
    for /f "tokens=2" %%v in ('ollama --version 2^>^&1') do set OLLVER=%%v
    echo [OK] Ollama !OLLVER! encontrado.
    echo Deseja baixar o modelo qwen3:4b agora? (~3 GB — pode demorar)
    set /p BAIXAR="[s/N]: "
    if /i "!BAIXAR!"=="s" (
        echo Baixando qwen3:4b...
        ollama pull qwen3:4b
        echo Baixando nomic-embed-text...
        ollama pull nomic-embed-text
        echo [OK] Modelos locais prontos.
    ) else (
        echo [INFO] Pulando. Execute 'ollama pull qwen3:4b' quando quiser.
    )
)

echo.
echo ════════════════════════════════════════════════════
echo  Instalacao concluida!
echo.
echo  Para iniciar:
if "%NIVEL%"=="1" (
    echo    python main.py --mode text --no-tts --no-overlay   ^(minimo, sem dependencias pesadas^)
) else if "%NIVEL%"=="2" (
    echo    python main.py --mode text --no-tts                ^(sem voz, com overlay^)
    echo    python main.py --mode text                         ^(texto com TTS^)
) else (
    echo    python main.py --mode text --no-tts                ^(sem voz, com overlay^)
    echo    python main.py --mode voice                        ^(modo voz completo^)
    echo    python main.py                                     ^(modo padrao: voz^)
)
echo    python main.py --web                               ^(com dashboard web^)
echo.
echo  Dica: use 'run.bat' para iniciar rapidamente.
echo.
pause
