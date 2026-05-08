# -*- mode: python ; coding: utf-8 -*-
# axiom.spec — PyInstaller spec para empacotar o Axiom como executável
# Uso: pyinstaller axiom.spec --clean
#      ou via: build.bat (Windows) / build.sh (Linux)

block_cipher = None

# Módulos importados dinamicamente pelo orchestrator (não detectados pelo análise estática)
_hidden = [
    # Módulos do Axiom (imports lazy via importlib)
    "modules.system_control",
    "modules.transcription",
    "modules.summarizer",
    "modules.search",
    "modules.dev_tools",
    "modules.routines",
    "modules.productivity",
    "modules.security",
    "modules.backup",
    "modules.calendar_integration",
    "modules.reminders",
    "modules.clipboard_tools",
    "modules.screen_reader",
    "modules.meeting_detector",
    "modules.obsidian",
    "modules.web_server",
    "core.profiles",
    "core.plugin_loader",
    "input.stt",
    "output.overlay",
    "output.tts",
    "output.notifier",
    "storage.context",
    "storage.db",
    "storage.file_store",
    # uvicorn (não detectado porque é carregado como string "web.app:app")
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "fastapi",
    "starlette",
    "anyio",
    "anyio._backends._asyncio",
    "anyio._backends._trio",
    # pyttsx3 drivers (carregados dinamicamente)
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",    # Windows
    "pyttsx3.drivers.nsss",     # macOS
    "pyttsx3.drivers.espeak",   # Linux
    # Outros
    "websockets",
    "h11",
    "httptools",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("core/config.yaml", "core"),
        ("plugins", "plugins"),
        ("web", "web"),
    ],
    hiddenimports=_hidden,
    hookspath=["hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="axiom",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,      # manter console para ver logs; mude para False para janela-only
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,         # adicione "assets/axiom.ico" quando tiver um ícone
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="axiom",
)
