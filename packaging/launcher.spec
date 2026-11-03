#--------------------#
# launcher.spec
# pyinstaller onefile build of launcher.py into dist/CANDecoderLauncher.exe
# run: pyinstaller packaging/launcher.spec --distpath dist --workpath build
# see docs/DEVELOPER_SETUP.md, build the release artifacts
#--------------------#

from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(REPO_ROOT / "launcher.py")],
    pathex=[str(REPO_ROOT)],
    # the launcher never touches the heavy app libraries, keep them out
    excludes=[
        "PySide6",
        "pyqtgraph",
        "matplotlib",
        "asammdf",
        "cantools",
        "reportlab",
        "numpy",
        "git",
        "tkinter",
    ],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CANDecoderLauncher",
    upx=True,
    console=True,  # update prompt is a console input() for now
)
