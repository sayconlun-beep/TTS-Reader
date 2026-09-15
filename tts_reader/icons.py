"""Material icons as inline SVG, tinted at runtime (Fusion's stock media icons
look out of place on Windows 11)."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "play": "M8 5v14l11-7z",
    "pause": "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
    "skip-back": "M6 6h2v12H6zm3.5 6l8.5 6V6z",
    "skip-forward": "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z",
    "seek-back": "M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z",
    "seek-forward": "M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z",
    "open": "M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 "
            "0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z",
    "recent": "M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 "
              "3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l"
              "-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9"
              "-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z",
    "menu": "M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 "
            ".9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 "
            "2-.9 2-2-.9-2-2-2z",
    "chapters": "M3 9h14V7H3v2zm0 4h14v-2H3v2zm0 4h14v-2H3v2zm16 0h2v-2h-2v2z"
                "m0-10v2h2V7h-2zm0 6h2v-2h-2v2z",
    "alarm": "M22 5.72l-4.6-3.86-1.29 1.53 4.6 3.86L22 5.72zM7.88 3.39L6.6 "
             "1.86 2 5.71l1.29 1.53 4.59-3.85zM12.5 8H11v6l4.75 2.85.75-1.23"
             "-4-2.37V8zM12 4c-4.97 0-9 4.03-9 9s4.02 9 9 9c4.97 0 9-4.03 9-9"
             "s-4.03-9-9-9zm0 16c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13"
             " 7-7 7z",
    "book": "M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0"
            "-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z",
}


def _render(svg, size, dpr):
    img = QImage(round(size * dpr), round(size * dpr),
                 QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def pixmap(name, color, size, dpr=1.0):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
           f'<path fill="{color}" d="{PATHS[name]}"/></svg>')
    return _render(svg, size, dpr)


def icon(name, color, disabled="#545c7e"):
    ic = QIcon()
    for size in (16, 20, 24, 32, 48):
        ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
        ic.addPixmap(pixmap(name, disabled, size), QIcon.Mode.Disabled)
    return ic


def app_icon():
    from . import paths
    svg_path = paths.bundle_dir() / "packaging" / "icon.svg"
    if not svg_path.exists():
        svg_path = paths.bundle_dir() / "icon.svg"
    try:
        svg = svg_path.read_text(encoding="utf-8")
    except OSError:
        return QIcon()
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(_render(svg, size, 1.0))
    return ic
