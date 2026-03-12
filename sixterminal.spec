# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for SixTerminal
# Build command: pyinstaller sixterminal.spec

import sys
from pathlib import Path

block_cipher = None

# Get the absolute path to the project directory
project_dir = Path.cwd()

a = Analysis(
    ['src/app.py'],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[
        # Include all source files
        ('src/*.py', 'src'),
        # Include Streamlit static files
        (f'{sys.prefix}/Lib/site-packages/streamlit/static', 'streamlit/static'),
        (f'{sys.prefix}/Lib/site-packages/streamlit/runtime', 'streamlit/runtime'),
        # Include other necessary data files
        ('requirements.txt', '.'),
    ],
    hiddenimports=[
        'streamlit',
        'streamlit.web.cli',
        'streamlit.runtime.scriptrunner.magic_funcs',
        'xerparser',
        'pandas',
        'openpyxl',
        'plotly',
        'openai',
        'watchdog',
        'dateutil',
        'PIL',
        'altair',
        'pyarrow',
        'pydeck',
        'tornado',
        'validators',
        'click',
        'toml',
        'blinker',
        'cachetools',
        'gitpython',
        'importlib_metadata',
        'packaging',
        'pympler',
        'rich',
        'tenacity',
        'tzlocal',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'numpy.distutils',
        'tkinter',
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
    name='SixTerminal',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Keep console window to show Streamlit logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon file path here if you have one: icon='icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SixTerminal',
)
