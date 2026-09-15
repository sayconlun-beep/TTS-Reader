"""Entry point: `python -m tts_reader [book]` or the packaged TTSReader.exe."""

import os
import sys


def _log_to_file():
    """A windowed exe has no stdout/stderr; keep a log in the data folder."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    from . import paths
    try:
        folder = paths.data_dir()
        folder.mkdir(parents=True, exist_ok=True)
        log = open(folder / "log.txt", "w", encoding="utf-8", buffering=1)
    except OSError:
        return
    sys.stdout = sys.stderr = log
    import faulthandler
    faulthandler.enable(log)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if "--self-test" in argv:
        from .selftest import run
        return run(argv)
    _log_to_file()
    if sys.platform == "win32":
        # Its own taskbar group and icon, not python's.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "TTSReader.TTSReader")
        except Exception:
            pass

    from PySide6.QtWidgets import QApplication

    from . import icons, paths
    from .ui import MainWindow, apply_theme

    app = QApplication(argv)
    app.setApplicationName(paths.APP_NAME)
    app.setDesktopFileName("tts-reader-qt")
    app.setQuitOnLastWindowClosed(False)     # closing while playing goes to the tray
    apply_theme(app)
    app.setWindowIcon(icons.app_icon())
    window = MainWindow(app)
    window.setWindowIcon(app.windowIcon())
    window.show()
    books = [a for a in argv[1:] if not a.startswith("-") and os.path.isfile(a)]
    if books:
        window.load_book(books[0])
    return app.exec()
