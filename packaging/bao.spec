# PyInstaller spec for Bao.app. Build with: packaging/build_mac.sh
# ruff: noqa
from pathlib import Path

ROOT = Path(SPECPATH).parent
VERSION = "0.1.0"

a = Analysis(
    [str(ROOT / "packaging" / "bao_app.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "bao" / "characters"), "bao/characters")],
    hiddenimports=[
        # Imported lazily by the CLI dispatcher / app, so list them explicitly.
        "bao.__main__",
        "bao.app",
        "bao.doctor",
        "bao.hook",
        "bao.installer",
        "AppKit",
        "Foundation",
        "objc",
        "PySide6.QtMultimedia",
    ],
    excludes=[
        "tkinter",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.Qt3DCore",
        "PySide6.QtPdf",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtDesigner",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "pytest",
        "ruff",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Bao",
    console=False,
    argv_emulation=False,
    strip=False,
    upx=False,
)

# Qt-free helper for the Claude Code hook: starts in ~60 ms instead of ~150 ms.
h = Analysis(
    [str(ROOT / "packaging" / "bao_hook.py")],
    pathex=[str(ROOT)],
    hiddenimports=["bao.hook"],
    excludes=["PySide6", "shiboken6", "AppKit", "Foundation", "objc", "tkinter"],
)
hook_exe = EXE(
    PYZ(h.pure),
    h.scripts,
    [],
    exclude_binaries=True,
    name="bao-hook",
    console=True,
    strip=False,
    upx=False,
)

coll = COLLECT(
    exe, hook_exe, a.binaries, a.datas, h.binaries, h.datas, name="Bao", strip=False, upx=False
)

app = BUNDLE(
    coll,
    name="Bao.app",
    icon=str(ROOT / "packaging" / "Bao.icns"),
    bundle_identifier="dev.bao.pet",
    version=VERSION,
    info_plist={
        "CFBundleName": "Bao",
        "CFBundleDisplayName": "Bao",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSUIElement": True,  # no Dock icon, no menu bar
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSAppleEventsUsageDescription": (
            "Bao brings the terminal tab of your Claude Code session to the front "
            "when you click the pet."
        ),
    },
)
