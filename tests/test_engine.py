import os
import time
import unittest

os.environ["TTS_READER_AUDIO"] = "null"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication  # noqa: E402

from tts_reader import paths  # noqa: E402
from tts_reader.book import Book  # noqa: E402
from tts_reader.engine import Player  # noqa: E402


def voice():
    voices = paths.list_voices()
    return paths.DEFAULT_VOICE if paths.DEFAULT_VOICE in voices else next(iter(voices))


@unittest.skipUnless(paths.list_voices(), "no piper voices installed")
class PlayerTests(unittest.TestCase):
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
        self.player.start(self.book(3), 0, voice(), 2.0)
        self.wait(lambda: self.ended)
        self.assertEqual(sorted(set(self.positions)), [0, 1, 2])

    def test_jump_drops_audio_rendered_for_the_old_spot(self):
        self.player.start(self.book(30), 0, voice(), 1.0)
        self.player.jump(20)
        self.positions.clear()
        self.wait(lambda: 21 in self.positions)
        self.assertTrue(all(p >= 20 for p in self.positions), self.positions)

    def test_speed_change_rerenders_from_the_current_sentence(self):
        self.player.start(self.book(10), 4, voice(), 1.0)
        self.wait(lambda: self.player.pos == 4 and self.player.cache)
        self.player.set_speed(1.5)
        self.assertEqual(self.player.cache, {})
        self.positions.clear()
        self.wait(lambda: 5 in self.positions)
        self.assertEqual(self.positions[0], 4)


if __name__ == "__main__":
    unittest.main()
