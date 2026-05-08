# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec para o Setup Wizard do Axiom
# Gera um executável standalone (~15MB) sem dependências externas

block_cipher = None

a = Analysis(
    ['setup_wizard.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'subprocess',
        'threading',
        'pathlib',
        'webbrowser',
        'shutil',
        'platform',
        'sys',
        'os',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'PIL',
        'PyQt6',
        'PyQt5',
        'wx',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Axiom-Setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
