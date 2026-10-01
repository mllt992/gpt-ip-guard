# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/26864/XiaomiMiMoProjects/.mimo-sessions/2026/10/01/ip-ip-ip-gpt-chatgpt-com/gpt-ip-guard/main.py'],
    pathex=['C:/Users/26864/XiaomiMiMoProjects/.mimo-sessions/2026/10/01/ip-ip-ip-gpt-chatgpt-com/gpt-ip-guard'],
    binaries=[],
    datas=[],
    hiddenimports=['psutil', 'requests', 'urllib3', 'charset_normalizer', 'idna', 'certifi', 'pystray', 'pystray._win32', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GPT-IP-Guard',
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
    icon=['C:/Users/26864/XiaomiMiMoProjects/.mimo-sessions/2026/10/01/ip-ip-ip-gpt-chatgpt-com/gpt-ip-guard/assets_icon.ico'],
)
