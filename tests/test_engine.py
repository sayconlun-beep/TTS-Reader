import os
import time
import unittest

os.environ["TTS_READER_AUDIO"] = "null"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication  # noqa: E402

from tts_reader import paths  # noqa: E402
from tts_reader.book import Book  # noqa: E402
from tts_reader.engine import Player, resample  # noqa: E402


def piper_voice():
    voices = [v for v in paths.list_voices() if not paths.is_kokoro(v)]
    return paths.default_voice(voices)


def kokoro_voice():
    voices = [v for v in paths.list_voices() if paths.is_kokoro(v)]
    return "kokoro:bf_emma" if "kokoro:bf_emma" in voices else voices[0]


def has_voices(kokoro):
    return any(paths.is_kokoro(v) == kokoro for v in paths.list_voices())


@unittest.skipUnless(has_voices(kokoro=False), "no piper voices installed")
class PlayerTests(unittest.TestCase):
    voice = staticmethod(piper_voice)

    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.player = Player()
        self.positions, self.ended, self.errors = [], [], []
        self.player.position.connect(self.positions.append)
        self.player.ended.connect(lambda: self.ended.append(True))
        self.player.error.connect(self.errors.append)

    def tearDown(self):
        self.player.stop()

    def wait(self, condition, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition() or self.errors:
                break
            time.sleep(0.02)
        self.assertEqual(self.errors, [])
        self.assertTrue(condition(), "timed out")

    def book(self, n):
        book = Book("test", "Test")
        book.add_para(" ".join(f"Sentence number {i}." for i in range(n)))
        return book

    def test_plays_every_sentence_then_ends(self):
        self.player.start(self.book(3), 0, self.voice(), 2.0)
        self.wait(lambda: self.ended)
        self.assertEqual(sorted(set(self.positions)), [0, 1, 2])

    def test_jump_drops_audio_rendered_for_the_old_spot(self):
        self.player.start(self.book(30), 0, self.voice(), 1.0)
        self.player.jump(20)
        self.positions.clear()
        self.wait(lambda: 21 in self.positions)
        self.assertTrue(all(p >= 20 for p in self.positions), self.positions)

    def test_speed_change_rerenders_from_the_current_sentence(self):
        self.player.start(self.book(10), 4, self.voice(), 1.0)
        self.wait(lambda: self.player.pos == 4 and self.player.cache)
        self.player.set_speed(1.5)
        self.assertEqual(self.player.cache, {})
        self.positions.clear()
        self.wait(lambda: 5 in self.positions)
        self.assertEqual(self.positions[0], 4)


class ResampleTests(unittest.TestCase):
    def test_changes_length_by_the_rate_ratio(self):
        import numpy as np
        samples = (np.sin(np.arange(22050) / 10) * 8000).astype(np.int16)
        out = resample(samples, 22050, 24000)
        self.assertEqual(out.dtype, np.int16)
        self.assertEqual(len(out), 24000)
        self.assertEqual(out[0], samples[0])
        self.assertIs(resample(samples, 22050, 22050), samples)


@unittest.skipUnless(has_voices(kokoro=True), "the Kokoro model isn't installed")
class KokoroPlayerTests(PlayerTests):
    voice = staticmethod(kokoro_voice)

    def two_voice_book(self):
        book = Book("test", "Test")
        for p in range(3):
            book.add_para(f"Paragraph {p} one. Paragraph {p} two.")
        book.voices[1] = self.voice()
        return book

    def test_paragraph_voice_reads_its_paragraph_only(self):
        if not has_voices(kokoro=False):
            self.skipTest("no piper voices installed")
        book = self.two_voice_book()
        self.player.start(book, 0, piper_voice(), 1.0)
        self.wait(lambda: self.ended)
        self.assertEqual(sorted(set(self.positions)), list(range(6)))
        self.assertEqual([self.player.voice_for(book, i) for i in range(6)],
                         [piper_voice()] * 2 + [self.voice()] * 2 + [piper_voice()] * 2)

    def test_changing_a_paragraph_voice_rerenders_it(self):
        if not has_voices(kokoro=False):
            self.skipTest("no piper voices installed")
        book = self.two_voice_book()
        self.player.start(book, 0, piper_voice(), 1.0)
        self.player.set_paused(True)
        self.wait(lambda: 3 in self.player.cache)
        self.assertEqual(self.player.cache[3][0][0], self.voice())
        book.voices[1] = piper_voice()
        self.player.voices_changed([1])
        self.wait(lambda: 3 in self.player.cache and self.player.cache[3][0][0] == piper_voice())

    def test_switching_engines_changes_the_output_rate(self):
        if not has_voices(kokoro=False):
            self.skipTest("no piper voices installed")
        self.player.start(self.book(10), 0, piper_voice(), 1.0)
        self.wait(lambda: 1 in self.positions)
        piper_rate = self.player.rate
        self.player.set_voice(self.voice())
        self.positions.clear()
        self.wait(lambda: len(set(self.positions)) >= 2)
        self.assertNotEqual(piper_rate, 24000)
        self.assertEqual(self.player.rate, 24000)


if __name__ == "__main__":
    unittest.main()
