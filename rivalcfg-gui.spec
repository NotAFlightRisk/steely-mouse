"""PyInstaller build. One self-contained binary with the UI and device profiles inside."""

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("rivalcfg")
datas += [
    ("rivalcfg_gui/templates", "rivalcfg_gui/templates"),
    ("rivalcfg_gui/static", "rivalcfg_gui/static"),
]

analysis = Analysis(
    ["rivalcfg_gui/__main__.py"],
    pathex=[SPECPATH],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "unittest", "pydoc_data"],
    noarchive=False,
)

exe = EXE(
    PYZ(analysis.pure),
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    name="rivalcfg-gui",
    console=True,
    strip=False,
    upx=False,
)
