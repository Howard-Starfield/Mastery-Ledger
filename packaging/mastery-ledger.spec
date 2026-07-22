from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH).resolve().parent
source_root = project_root / "src"
web_root = source_root / "mastery_ledger" / "web"

webview_datas, webview_binaries, webview_hiddenimports = collect_all("webview")

analysis = Analysis(
    [str(source_root / "mastery_ledger" / "desktop.py")],
    pathex=[str(source_root)],
    binaries=webview_binaries,
    datas=[(str(web_root), "mastery_ledger/web"), *webview_datas],
    hiddenimports=[
        *webview_hiddenimports,
        "uvicorn.lifespan.on",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.h11_impl",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "yt_dlp", "faster_whisper"],
    noarchive=False,
    optimize=1,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="MasteryLedger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MasteryLedger",
)
