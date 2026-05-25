# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['daemon.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    name='Claude Copy',
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
)

app = BUNDLE(
    exe,
    name='Claude Copy.app',
    icon=None,
    bundle_identifier='com.claude-copy',
    info_plist={
        'LSUIElement': True,                  # background app — no Dock icon
        'CFBundleName': 'Claude Copy',
        'CFBundleDisplayName': 'Claude Copy',
        'CFBundleShortVersionString': '1.0',
        'NSHumanReadableCopyright': '',
    },
)
