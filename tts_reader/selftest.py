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

MARKDOWN = """---
title: Sample Notes
tags: [x]
---
# Getting Started

Read **this** first. It links to [the docs](https://example.com)
and wraps onto a second line.

<!-- a comment that isn't read -->
- First item
- Second `item`

```sh
echo "code is skipped"
```

Details
-------

> A quoted line.

| Name | Value |
| ---- | ----- |
| Speed | Fast |
"""
MARKDOWN_SENTENCES = [
    "Getting Started", "Read this first.",
    "It links to the docs and wraps onto a second line.", "First item",
    "Second item", "Details", "A quoted line.", "Name, Value", "Speed, Fast",
]
MARKDOWN_CHAPTERS = [("Getting Started", 0, 0), ("Details", 1, 5)]

DOCX_SENTENCES = [
    "Sample Report", "Overview", "The first paragraph.", "It has two sentences.",
    "Tabs and breaks join words.", "Background", "Cell one, Cell two",
    "Findings", "The last word.",
]
DOCX_CHAPTERS = [("Overview", 0, 1), ("Background", 1, 5), ("Findings", 0, 7)]


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


def make_markdown(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(MARKDOWN)
    return path


def make_docx(path):
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

    def para(text, style=None):
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        return f"<w:p>{ppr}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"

    body = "".join([
        para("Sample Report", "Title"),
        para("Overview", "Heading1"),
        '<w:p><w:r><w:t>The first paragraph. </w:t></w:r>'
        '<w:r><w:t>It has two sentences.</w:t></w:r></w:p>',
        '<w:p><w:r><w:t>Tabs</w:t><w:tab/><w:t>and</w:t><w:br/>'
        '<w:t>breaks join words.</w:t></w:r></w:p>',
        para("", None),
        para("Background", "MySubHeading"),
        "<w:tbl><w:tr><w:tc>" + para("Cell one") + "</w:tc><w:tc>"
        + para("Cell two") + "</w:tc></w:tr></w:tbl>",
        '<w:p><w:pPr><w:outlineLvl w:val="0"/></w:pPr>'
        '<w:r><w:t>Findings</w:t></w:r></w:p>',
        para("The last word."),
    ])
    styles = (
        f'<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/></w:style>'
        f'<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
        f'<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>'
        f'<w:style w:type="paragraph" w:styleId="MySubHeading"><w:name w:val="My Sub"/>'
        f'<w:basedOn w:val="Heading2"/></w:style>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml",
                   f'<w:document {w}><w:body>{body}<w:sectPr/></w:body></w:document>')
        z.writestr("word/styles.xml", f"<w:styles {w}>{styles}</w:styles>")
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
    md = open_book(make_markdown(os.path.join(tmp, "sample.md")))
    _check("markdown title", md.title, "Sample Notes")
    _check("markdown sentences", md.sentences, MARKDOWN_SENTENCES)
    _check("markdown chapters", md.chapters, MARKDOWN_CHAPTERS)
    log("markdown: ok")
    docx = open_book(make_docx(os.path.join(tmp, "sample.docx")))
    _check("docx title", docx.title, "Sample Report")
    _check("docx sentences", docx.sentences, DOCX_SENTENCES)
    _check("docx chapters", docx.chapters, DOCX_CHAPTERS)
    log("docx: ok")

    voices = paths.list_voices()
    log(f"voices: {', '.join(voices) or 'none'}")
    if not voices:
        raise AssertionError("no voices found")
    from piper import PiperVoice
    start = time.monotonic()
    name = paths.default_voice([v for v in voices if not paths.is_kokoro(v)])
    voice = PiperVoice.load(voices[name])
    samples = sum(len(c.audio_int16_array) for c in voice.synthesize("Self test."))
    if samples < 1000:
        raise AssertionError(f"piper produced only {samples} samples")
    log(f"piper: {samples} samples in {time.monotonic() - start:.2f}s")
    kokoro_voices = [v for v in voices if paths.is_kokoro(v)]
    if kokoro_voices:
        from piper.phonemize_espeak import ESPEAK_DATA_DIR

        from .kokoro import KOKORO_VOICES, Kokoro
        start = time.monotonic()
        model = voices[kokoro_voices[0]]
        kokoro = Kokoro(model, os.path.join(os.path.dirname(model), KOKORO_VOICES),
                        ESPEAK_DATA_DIR)
        samples = len(kokoro.synthesize("Self test.", kokoro_voices[0][7:]))
        if samples < 1000:
            raise AssertionError(f"kokoro produced only {samples} samples")
        log(f"kokoro: {samples} samples in {time.monotonic() - start:.2f}s")
    elif paths.FROZEN:
        raise AssertionError("the Kokoro model isn't bundled")

    from PySide6.QtWidgets import QApplication

    from . import icons
    from .ui import MainWindow, apply_theme, voice_label

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
    voice, combo = window._voice(), window.voice_combo
    if voice not in window._favourites():
        window.toggle_favourite()
        _check("favourite listed first", combo.itemData(0), voice)
        _check("favourite starred", combo.itemText(0).startswith("★"), True)
        _check("favourite still selected", window._voice(), voice)
        window.toggle_favourite()
        _check("unfavourited", voice in window._favourites(), False)
        _check("unfavourited voice still selected", window._voice(), voice)
        log("favourites: ok")
    other = next(v for v in window.voices if v != voice)
    window.set_paragraph_voice([1, 2], other)
    _check("paragraph voices", window.book.voices, {1: other, 2: other})
    _check("paragraph tooltip", window.view.voice_names.get(2), voice_label(other))
    _check("paragraph voices saved",
           sorted(window.lib.book(window.book.path).get("voices", {})), ["1", "2"])
    window.set_paragraph_voice([1, 2], "")
    _check("paragraph voices cleared", window.book.voices, {})
    log("paragraph voices: ok")
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
    window.player.stop()

    from .export import ffmpeg_path
    log(f"ffmpeg: {ffmpeg_path()}")
    window.set_paragraph_voice([1], other)
    out = os.path.join(tmp, "sample.m4b")
    window.start_export(window.book, voice, out)
    _check("export bar shown", window.export_bar.isVisible(), True)
    _wait(app, lambda: window.exporter is None, 300, "the audiobook export")
    no_slot_errors("export")
    if not os.path.exists(out):
        raise AssertionError(f"export failed: {window.toast_label.text()}")
    import re
    import subprocess
    report = subprocess.run([ffmpeg_path(), "-hide_banner", "-i", out], capture_output=True,
                            text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stderr
    chapters = re.findall(r"title\s+: (Chapter One|Chapter Two|Part Two)", report)
    _check("audiobook chapters", chapters, ["Chapter One", "Chapter Two", "Part Two"])
    log(f"audiobook export: {os.path.getsize(out) // 1024} KB, chapters ok")
    if shot:
        window.grab().save(shot)
    window.close()
