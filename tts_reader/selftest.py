"""`TTSReader.exe --self-test [log]`: proves a build works end to end.

Parses sample books, renders speech with a bundled voice, then drives the
real window offscreen through play, jump and end-of-book with silent audio.
CI runs it against the packaged exe, where a missing DLL or data file shows
up as a failure instead of a crash on your desktop.
"""

import os
import sys
import tempfile
import time
import traceback
import zipfile

EPUB_SENTENCES = [
    "Chapter One", "Mr. Darcy walked in.", '"Hello," she said.',
    "Then silence fell!", "Second paragraph here.", "Chapter Two",
    "It was late.", "Part Two", "The end came quietly.",
]
EPUB_CHAPTERS = [("Chapter One", 0, 0), ("Chapter Two", 0, 5), ("Part Two", 1, 7)]

PDF_SENTENCES = [
    "Introduction", "This is the first page.", "Chapter 1",
    "Chapter text begins here.", "Section 1.1",
    "A section with a hyphenated word joined.", "Last page of the book.",
]
PDF_CHAPTERS = [("Introduction", 0, 0), ("Chapter 1", 0, 2), ("Section 1.1", 1, 4)]


def _xhtml(body):
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>x</title>'
            f'</head><body>{body}</body></html>')


def make_epub(path):
    files = {
        "META-INF/container.xml":
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:'
            'names:tc:opendocument:xmlns:container"><rootfiles><rootfile '
            'full-path="OEBPS/content.opf" media-type="application/oebps-'
            'package+xml"/></rootfiles></container>',
        "OEBPS/content.opf":
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
            'version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:title>Sample Book</dc:title></metadata><manifest>'
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
            'properties="nav"/>'
            '<item id="c1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="c2" href="text/ch2.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest><spine><itemref idref="c1"/><itemref idref="c2"/></spine>'
            '</package>',
        "OEBPS/nav.xhtml": _xhtml(
            '<nav epub:type="toc"><ol>'
            '<li><a href="text/ch1.xhtml">Chapter One</a></li>'
            '<li><a href="text/ch2.xhtml">Chapter Two</a><ol>'
            '<li><a href="text/ch2.xhtml#part2">Part Two</a></li></ol></li>'
            '</ol></nav>'),
        "OEBPS/text/ch1.xhtml": _xhtml(
            '<h1>Chapter One</h1><p>Mr. Darcy walked in. "Hello," she said. '
            'Then silence fell!</p><p>Second paragraph here.</p>'),
        "OEBPS/text/ch2.xhtml": _xhtml(
            '<h1>Chapter Two</h1><p>It was late.</p><h2 id="part2">Part Two</h2>'
            '<p>The end came quietly.</p>'),
    }
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        for name, data in files.items():
            z.writestr(name, data, zipfile.ZIP_DEFLATED)
    return path


def make_pdf(path):
    import pymupdf

    pages = [
        ["Running Header", "Introduction", "This is the first page.", "1"],
        ["Running Header", "Chapter 1", "Chapter text begins here.", "2"],
        ["Running Header", "Section 1.1", "A section with a hyphen-",
         "ated word joined.", "3"],
        ["Running Header", "Last page of the book.", "4"],
    ]
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page()
        for k, line in enumerate(lines):
            page.insert_text((72, 72 + 20 * k), line, fontsize=12)
    doc.set_toc([[1, "Introduction", 1], [1, "Chapter 1", 2], [2, "Section 1.1", 3]])
    doc.set_metadata({"title": "Sample PDF"})
    doc.save(path)
    doc.close()
    return path


def _wait(app, condition, timeout, what):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {what}")


def _check(label, got, want):
    if got != want:
        raise AssertionError(f"{label}: got {got!r}, want {want!r}")


def run(argv):
    i = argv.index("--self-test")
    log_path = argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("-") \
        else None
    shot = argv[argv.index("--screenshot") + 1] if "--screenshot" in argv else None
    if log_path:
        open(log_path, "w", encoding="utf-8").close()

    def log(msg):
        if sys.stdout is not None:
            print(msg, flush=True)
        if log_path:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(msg + "\n")

    tmp = tempfile.mkdtemp(prefix="tts-reader-selftest-")
    os.environ["TTS_READER_DATA"] = tmp
    os.environ["TTS_READER_AUDIO"] = "null"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        _run(log, tmp, shot)
    except Exception:
        log(traceback.format_exc())
        log("SELF-TEST FAILED")
        return 1
    log("SELF-TEST PASSED")
    return 0


def _run(log, tmp, shot):
    from . import paths
    from .book import open_book

    log(f"python {sys.version.split()[0]} on {sys.platform}, frozen={paths.FROZEN}")
    import sounddevice
    log(f"audio: {sounddevice.get_portaudio_version()[1]}")

    epub = open_book(make_epub(os.path.join(tmp, "sample.epub")))
    _check("epub sentences", epub.sentences, EPUB_SENTENCES)
    _check("epub chapters", epub.chapters, EPUB_CHAPTERS)
    log("epub: ok")
    pdf = open_book(make_pdf(os.path.join(tmp, "sample.pdf")))
    _check("pdf title", pdf.title, "Sample PDF")
    _check("pdf sentences", pdf.sentences, PDF_SENTENCES)
    _check("pdf chapters", pdf.chapters, PDF_CHAPTERS)
    log("pdf: ok")

    voices = paths.list_voices()
    log(f"voices: {', '.join(voices) or 'none'}")
    if not voices:
        raise AssertionError("no voices found")
    from piper import PiperVoice
    start = time.monotonic()
    name = paths.DEFAULT_VOICE if paths.DEFAULT_VOICE in voices else next(iter(voices))
    voice = PiperVoice.load(voices[name])
    samples = sum(len(c.audio_int16_array) for c in voice.synthesize("Self test."))
    if samples < 1000:
        raise AssertionError(f"piper produced only {samples} samples")
    log(f"piper: {samples} samples in {time.monotonic() - start:.2f}s")

    from PySide6.QtWidgets import QApplication

    from . import icons
    from .ui import MainWindow, apply_theme

    # Qt only prints exceptions raised in slots; make them fail the test.
    slot_errors = []
    previous_hook = sys.excepthook
    sys.excepthook = lambda *exc: (slot_errors.append(exc),
                                   previous_hook(*exc))

    def no_slot_errors(stage):
        if slot_errors:
            raise AssertionError(f"exception during {stage}: " + "".join(
                traceback.format_exception(*slot_errors[0])))

    app = QApplication.instance() or QApplication(["tts-reader-selftest"])
    apply_theme(app)
    app.setWindowIcon(icons.app_icon())
    if app.windowIcon().isNull():
        raise AssertionError("app icon missing")
    window = MainWindow(app)
    errors = []
    window.player.error.connect(errors.append)
    ended = []
    window.player.ended.connect(lambda: ended.append(True))
    window.show()
    window.load_book(os.path.join(tmp, "sample.epub"))
    _wait(app, lambda: window.book is not None, 20, "the book to load")
    no_slot_errors("book loading")
    _check("chapter list", window.chapter_tree.topLevelItemCount(), 2)
    _check("title", window.title_label.text(), "Sample Book")
    window.toggle_play()
    _wait(app, lambda: window.pos >= 2 or errors, 60, "playback to reach sentence 2")
    if errors:
        raise AssertionError(f"player error: {errors[0]}")
    log(f"playback: reached sentence {window.pos}")
    window.jump_to(6)
    _wait(app, lambda: window.pos >= 7 or errors, 30, "the jump to sentence 6")
    _wait(app, lambda: ended or errors, 30, "the end of the book")
    if errors:
        raise AssertionError(f"player error: {errors[0]}")
    no_slot_errors("playback")
    log("jump + end of book: ok")
    if shot:
        window.grab().save(shot)
    window.player.stop()
    window.close()
