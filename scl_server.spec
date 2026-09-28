# scl_server.spec
# běží s: pyinstaller scl_server.spec

block_cipher = None

a = Analysis(
    ['server/scl_server/main.py'],
    pathex=['server/scl_server'],
    binaries=[],
    datas=[],
    hiddenimports=['parser_structured', 'handlers', 'diagnostics', 'syntax_keywords', 'scl_text'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter', 'unittest', 'pydoc', 'pydoc_data', 'lib2to3', 'sqlite3', 'test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # nebo False pro tichý režim bez cmd okna
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='SCLserver',
)
