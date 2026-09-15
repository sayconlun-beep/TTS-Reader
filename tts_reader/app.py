"""Entry point: `python -m tts_reader [book]`, TTSReader.exe or TTS Reader.app."""

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

    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import QApplication

    from . import icons, paths
    from .ui import MainWindow, apply_theme

    class OpenFiles(QObject):
        """macOS hands over Finder's "Open With" as FileOpen events, not argv,
        and the first one can arrive before the window exists."""

        def __init__(self):
            super().__init__()
            self.window = None
            self.pending = None

        def eventFilter(self, _obj, event):
            if event.type() == QEvent.Type.FileOpen and event.file():
                if self.window:
                    self.window.show_window()
                    self.window.load_book(event.file())
                else:
                    self.pending = event.file()
                return True
            return False

    app = QApplication(argv)
    opener = OpenFiles()
    app.installEventFilter(opener)
    app.setApplicationName(paths.APP_NAME)
    app.setDesktopFileName("tts-reader-qt")
    app.setQuitOnLastWindowClosed(False)     # closing while playing goes to the tray
    apply_theme(app)
    app.setWindowIcon(icons.app_icon())
    window = MainWindow(app)
    window.setWindowIcon(app.windowIcon())
    window.show()
    # Cmd+Q from the macOS app menu quits without closing the window first.
    app.aboutToQuit.connect(lambda: (window.save_position(), window.player.stop()))
    opener.window = window
    books = [a for a in argv[1:] if not a.startswith("-") and os.path.isfile(a)]
    if opener.pending:
        books.insert(0, opener.pending)
    if books:
        window.load_book(books[0])
    return app.exec()
