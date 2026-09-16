# PyInstaller spec: pyinstaller packaging/TTSReader.spec
# Expects build/voices (fetch_voices.py) and build/icon.ico / icon.icns
# (make_icon.py). On macOS it also wraps the result in "TTS Reader.app".

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).parent
ICON = ROOT / "build" / "icon.ico"
ICNS = ROOT / "build" / "icon.icns"

datas = [
    (str(ROOT / "packaging" / "icon.svg"), "packaging"),
    (str(ROOT / "build" / "voices"), "voices"),
]
# piper needs espeak-ng-data next to its espeakbridge extension. The Hebrew
# and Arabic diacritizer models (~25 MB) only matter for those voices.
datas += collect_data_files("piper", excludes=[
    "**/train/**", "**/templates/**", "**/hebrew/**", "**/tashkeel/**"])
datas += collect_data_files("pymupdf")
binaries = collect_dynamic_libs("pymupdf") + collect_dynamic_libs("onnxruntime")
# Audiobook export runs imageio-ffmpeg's static ffmpeg (AAC and LAME built in).
# Only the binary goes in, to ffmpeg/, where tts_reader/export.py looks first.
import imageio_ffmpeg
binaries += [(imageio_ffmpeg.get_ffmpeg_exe(), "ffmpeg")]

a = Analysis(
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT)],
    datas=datas,
    binaries=binaries,
    hiddenimports=["piper.espeakbridge", "sounddevice", "pymupdf"],
    excludes=["tkinter", "imageio_ffmpeg", "piper.train", "piper.http_server", "matplotlib", "PIL",
              "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TTSReader",
    console=False,
    icon=str(ICON) if ICON.exists() and sys.platform == "win32" else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="TTSReader", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="TTS Reader.app",
        icon=str(ICNS) if ICNS.exists() else None,
        bundle_identifier="app.ttsreader.TTSReader",
        version=os.environ.get("APP_VERSION", "0.0.0"),
        info_plist={
            "CFBundleDisplayName": "TTS Reader",
            "LSMinimumSystemVersion": "14.0",
            "NSHighResolutionCapable": True,
            # Listed under Finder's "Open With" for books, never the default.
            "CFBundleDocumentTypes": [
                {"CFBundleTypeName": "EPUB book", "CFBundleTypeRole": "Viewer",
                 "LSHandlerRank": "Alternate",
                 "LSItemContentTypes": ["org.idpf.epub-container"]},
                {"CFBundleTypeName": "PDF document", "CFBundleTypeRole": "Viewer",
                 "LSHandlerRank": "Alternate",
                 "LSItemContentTypes": ["com.adobe.pdf"]},
                {"CFBundleTypeName": "Word document", "CFBundleTypeRole": "Viewer",
                 "LSHandlerRank": "Alternate",
                 "LSItemContentTypes": ["org.openxmlformats.wordprocessingml.document"]},
                {"CFBundleTypeName": "Markdown document", "CFBundleTypeRole": "Viewer",
                 "LSHandlerRank": "Alternate",
                 "LSItemContentTypes": ["net.daringfireball.markdown"]},
            ],
        },
    )
