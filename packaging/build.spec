#--------------------#
# build.spec
# pyinstaller onedir build of main.py, output goes to dist/
# run: pyinstaller packaging/build.spec --distpath dist --workpath build
# see docs/DEVELOPER_SETUP.md, build the release artifacts
#--------------------#

# qt modules the app never uses, excluding them keeps the build small
# remove one from this list if a feature starts needing it
QT_UNUSED_EXCLUDES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtSensors",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtTest",
    "PySide6.QtSql",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtSpatialAudio",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
]

# optional imports of the app's libraries that the app never uses
# (pyqtgraph has a matplotlib exporter, only the image exporter is used)
UNUSED_EXCLUDES = ["matplotlib", "tkinter"]

from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(REPO_ROOT / "main.py")],
    pathex=[str(REPO_ROOT)],
    datas=[
        # lands under _internal/, main.py finds it through sys._MEIPASS
        (str(REPO_ROOT / "config" / "defaults"), "config/defaults"),
    ],
    excludes=QT_UNUSED_EXCLUDES + UNUSED_EXCLUDES,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CANDecoder-app",
    upx=True,
    console=False,  # gui app, no console window
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    upx=True,
    name="CANDecoder-app",
)