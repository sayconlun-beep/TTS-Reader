"""Save a whole book as one audio file for a phone: an .m4b audiobook with
chapter markers, or .m4a / .mp3.

Every sentence is rendered with its paragraph's voice and streamed as PCM
into ffmpeg, so memory stays flat however long the book is. Chapter times
are only known once everything is rendered, so a second ffmpeg pass copies
the audio and adds them. The file appears under its real name only when it
is complete.

ffmpeg comes from imageio-ffmpeg, which ships a static build with AAC and
LAME for Windows, macOS and Linux; the packaged app carries it in ffmpeg/.
"""

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Signal

from . import paths
from .engine import GAP, Models, resample

RATE = 24000                # Kokoro's rate; piper's 22.05 kHz is resampled up
PARAGRAPH_GAP = 0.35        # seconds of silence after a paragraph
HEADING_GAP = 1.0           # ... and after a heading
FORMATS = {                 # suffix -> ffmpeg encoder options, muxer
    ".m4b": (["-c:a", "aac", "-b:a", "64k"], "ipod"),
    ".m4a": (["-c:a", "aac", "-b:a", "64k"], "ipod"),
    ".mp3": (["-c:a", "libmp3lame", "-b:a", "64k"], "mp3"),
}
# No console window flashing up for each ffmpeg run on Windows.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def ffmpeg_path():
    """The bundled ffmpeg, else imageio-ffmpeg's, else one on PATH."""
    folder = paths.bundle_dir() / "ffmpeg"
    if folder.is_dir():
        for f in sorted(folder.iterdir()):
            if f.name.startswith("ffmpeg"):
                return str(f)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _meta(text):
    return re.sub(r"([=;#\\\n])", r"\\\1", text)


def chapter_metadata(title, chapters, total_samples, rate=RATE):
    """FFMETADATA for (start sample, title) chapters; empty ones are dropped."""
    lines = [";FFMETADATA1", f"title={_meta(title)}", f"album={_meta(title)}",
             "genre=Audiobook"]
    for n, (start, name) in enumerate(chapters):
        end = chapters[n + 1][0] if n + 1 < len(chapters) else total_samples
        if end > start:
            lines += ["[CHAPTER]", f"TIMEBASE=1/{rate}", f"START={start}",
                      f"END={end}", f"title={_meta(name)}"]
    return "\n".join(lines) + "\n"


class Exporter(QObject):
    progress = Signal(float, float)     # fraction done, seconds left
    finished = Signal(str)              # the saved file
    failed = Signal(str)

    def __init__(self, book, voice, out):
        super().__init__()
        self.book, self.voice, self.out = book, voice, out
        self.voices = dict(book.voices)     # the book may change while we work
        self.cancelled = False
        self.proc = None
        self.thread = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def cancel(self):
        self.cancelled = True
        proc = self.proc
        if proc and proc.poll() is None:
            proc.kill()

    def _run(self):
        work = tempfile.mkdtemp(prefix="tts-reader-export-")
        try:
            error = self._render(work)
        except Exception as e:
            error = f"Couldn't save the audiobook ({e})."
        finally:
            shutil.rmtree(work, ignore_errors=True)
        # Signals emitted here are queued to the window's thread.
        if self.cancelled:
            return
        if error:
            self.failed.emit(error)
        else:
            self.finished.emit(self.out)

    def _ffmpeg(self, args, **kw):
        self.proc = subprocess.Popen(
            [self.exe, "-hide_banner", "-loglevel", "error", "-y", *args],
            stderr=subprocess.PIPE, creationflags=NO_WINDOW, **kw)
        return self.proc

    def _render(self, work):
        self.exe = ffmpeg_path()
        if not self.exe:
            return "ffmpeg isn't available, so audiobooks can't be saved."
        book = self.book
        suffix = os.path.splitext(self.out)[1].lower()
        codec, muxer = FORMATS[suffix]
        audio = os.path.join(work, f"audio{suffix}")
        # stderr goes to a file: a pipe nobody reads can fill and stall ffmpeg.
        errlog = open(os.path.join(work, "ffmpeg.log"), "w+b")
        proc = subprocess.Popen(
            [self.exe, "-hide_banner", "-loglevel", "error", "-y", "-f", "s16le",
             "-ar", str(RATE), "-ac", "1", "-i", "pipe:0", *codec, "-f", muxer, audio],
            stdin=subprocess.PIPE, stderr=errlog, creationflags=NO_WINDOW)
        self.proc = proc

        def ffmpeg_error():
            errlog.seek(0)
            return errlog.read().decode(errors="replace").strip()[-300:]

        para_of = [0] * len(book.sentences)
        gaps = {}                           # last sentence of a paragraph -> seconds
        for n, (heading, lo, hi) in enumerate(book.paragraphs):
            para_of[lo:hi] = [n] * (hi - lo)
            gaps[hi - 1] = HEADING_GAP if heading else PARAGRAPH_GAP
        starts = {start: title for title, _depth, start in book.chapters}
        models, chapters = Models(), []
        samples, total, began = 0, len(book.sentences), time.monotonic()
        try:
            for i in range(total):
                if self.cancelled:
                    return None
                if i in starts:
                    chapters.append((samples, starts[i]))
                voice = self.voices.get(para_of[i], self.voice)
                try:
                    model = models.get(voice)
                    with models.lock:
                        parts = model.render(book.spoken(i), 1.0)
                except Exception as e:
                    return f"The voice {voice} couldn't read sentence {i + 1} ({e})."
                pcm = resample(np.concatenate(parts) if parts else np.zeros(0, np.int16),
                               model.sample_rate, RATE)
                silence = np.zeros(int(RATE * (GAP + gaps.get(i, 0))), np.int16)
                try:
                    proc.stdin.write(pcm.tobytes() + silence.tobytes())
                except OSError:
                    return None if self.cancelled else f"ffmpeg stopped: {ffmpeg_error()}"
                samples += len(pcm) + len(silence)
                if i % 4 == 0 or i == total - 1:
                    spent = time.monotonic() - began
                    self.progress.emit((i + 1) / total, spent / (i + 1) * (total - i - 1))
            proc.stdin.close()
            if proc.wait() != 0:
                return None if self.cancelled else f"ffmpeg failed: {ffmpeg_error()}"
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            try:
                proc.stdin.close()
            except OSError:
                pass
            errlog.close()

        meta = os.path.join(work, "chapters.txt")
        with open(meta, "w", encoding="utf-8") as fh:
            fh.write(chapter_metadata(book.title, chapters, samples))
        partial = f"{self.out}.part"
        proc = self._ffmpeg(
            ["-i", audio, "-i", meta, "-map", "0:a", "-map_metadata", "1",
             "-map_chapters", "1", "-c", "copy",
             *(["-id3v2_version", "3"] if suffix == ".mp3" else []),
             "-f", muxer, partial], stdin=subprocess.DEVNULL)
        _out, err = proc.communicate()
        if proc.returncode != 0:
            try:
                os.unlink(partial)
            except OSError:
                pass
            return None if self.cancelled else \
                f"ffmpeg failed: {err.decode(errors='replace').strip()[-300:]}"
        os.replace(partial, self.out)
        return None
