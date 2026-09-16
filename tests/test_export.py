import os
import re
import subprocess
import tempfile
import time
import unittest

os.environ["TTS_READER_AUDIO"] = "null"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication  # noqa: E402

from tts_reader import paths  # noqa: E402
from tts_reader.book import Book  # noqa: E402
from tts_reader.export import Exporter, chapter_metadata, ffmpeg_path  # noqa: E402


def piper_voice():
    return paths.default_voice([v for v in paths.list_voices() if not paths.is_kokoro(v)])


def probe(path):
    """(duration seconds, [chapter titles]) from ffmpeg's own report."""
    err = subprocess.run([ffmpeg_path(), "-hide_banner", "-i", path],
                         capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    titles = re.findall(r"Chapter #\d+:\d+.*\n\s+Metadata:\n\s+title\s+: (.*)", err)
    return int(h) * 3600 + int(m) * 60 + float(s), titles


class MetadataTests(unittest.TestCase):
    def test_chapters_end_where_the_next_starts_and_escape_specials(self):
        meta = chapter_metadata("A = B", [(0, "One"), (0, "Empty"), (48000, "Two; #2")], 96000)
        self.assertIn("title=A \\= B", meta)
        self.assertNotIn("title=One", meta)          # zero length, dropped
        self.assertIn("START=0\nEND=48000\ntitle=Empty", meta)
        self.assertIn("START=48000\nEND=96000\ntitle=Two\; \\#2", meta)


@unittest.skipUnless(ffmpeg_path() and any(not paths.is_kokoro(v) for v in paths.list_voices()),
                     "needs ffmpeg and a piper voice")
class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def book(self):
        book = Book("test", "Test Book")
        book.add_para("Chapter One", heading=True)
        book.add_para("The first sentence. The second one.")
        book.add_para("Chapter Two", heading=True)
        book.add_para("The end.")
        book.chapters = [("Chapter One", 0, 0), ("Chapter Two", 0, 3)]
        return book

    def run_export(self, suffix, cancel_after=None):
        out = os.path.join(tempfile.mkdtemp(), f"book{suffix}")
        exporter = Exporter(self.book(), piper_voice(), out)
        done, failed, progress = [], [], []
        exporter.finished.connect(done.append)
        exporter.failed.connect(failed.append)
        exporter.progress.connect(lambda f, _eta: progress.append(f))
        exporter.start()
        deadline = time.monotonic() + 60
        while exporter.running and time.monotonic() < deadline:
            if cancel_after is not None and time.monotonic() > deadline - 60 + cancel_after:
                exporter.cancel()
            self.app.processEvents()
            time.sleep(0.02)
        self.app.processEvents()
        return out, done, failed, progress

    def test_m4b_has_both_chapters_in_order(self):
        out, done, failed, progress = self.run_export(".m4b")
        self.assertEqual(failed, [])
        self.assertEqual(done, [out])
        self.assertEqual(progress[-1], 1.0)
        duration, titles = probe(out)
        self.assertEqual(titles, ["Chapter One", "Chapter Two"])
        self.assertGreater(duration, 2)
        self.assertFalse(os.path.exists(out + ".part"))

    def test_mp3(self):
        out, done, failed, _progress = self.run_export(".mp3")
        self.assertEqual((failed, done), ([], [out]))
        self.assertGreater(probe(out)[0], 2)

    def test_cancel_leaves_no_file(self):
        out, done, failed, _progress = self.run_export(".m4b", cancel_after=0.0)
        self.assertEqual((done, failed), ([], []))
        self.assertEqual(os.listdir(os.path.dirname(out)), [])


if __name__ == "__main__":
    unittest.main()
