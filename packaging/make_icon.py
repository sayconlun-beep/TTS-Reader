"""Render packaging/icon.svg to build/icon.ico (Windows) and build/icon.icns
(macOS)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build"


def main():
    OUT.mkdir(exist_ok=True)
    _app = QGuiApplication(sys.argv)
    renderer = QSvgRenderer(str(ROOT / "packaging" / "icon.svg"))
    # 1024 px so the Retina sizes in the .icns stay sharp.
    img = QImage(1024, 1024, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    png = OUT / "icon.png"
    img.save(str(png))
    with Image.open(png) as icon:
        icon.save(OUT / "icon.ico", sizes=[(s, s) for s in
                                          (16, 24, 32, 48, 64, 128, 256)])
        icon.save(OUT / "icon.icns")
    print(f"wrote {OUT / 'icon.ico'} and {OUT / 'icon.icns'}")


if __name__ == "__main__":
    main()
