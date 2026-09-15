import os
import tempfile
import unittest

from tts_reader import selftest
from tts_reader.book import BookError, open_book, split_sentences


class SplitTests(unittest.TestCase):
    def test_abbreviations_do_not_split(self):
        self.assertEqual(split_sentences("Mr. Darcy came. He left."),
                         ["Mr. Darcy came.", "He left."])

    def test_dialogue_keeps_its_attribution(self):
        self.assertEqual(split_sentences('"Stop!" she cried. Then quiet.'),
                         ['"Stop!" she cried.', "Then quiet."])

    def test_long_sentences_break_at_clauses(self):
        parts = split_sentences(", ".join(["one two three"] * 20) + ".")
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p.split()) <= 45 for p in parts))


class BookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_epub(self):
        book = open_book(selftest.make_epub(os.path.join(self.tmp, "a.epub")))
        self.assertEqual(book.title, "Sample Book")
        self.assertEqual(book.sentences, selftest.EPUB_SENTENCES)
        self.assertEqual(book.chapters, selftest.EPUB_CHAPTERS)
        self.assertEqual(book.spoken(0), "Chapter One.")
        self.assertEqual(book.chapter_at(8), 2)

    def test_pdf(self):
        book = open_book(selftest.make_pdf(os.path.join(self.tmp, "a.pdf")))
        self.assertEqual(book.title, "Sample PDF")
        self.assertEqual(book.sentences, selftest.PDF_SENTENCES)
        self.assertEqual(book.chapters, selftest.PDF_CHAPTERS)

    def test_rejects_other_files(self):
        path = os.path.join(self.tmp, "notes.txt")
        open(path, "w").close()
        with self.assertRaises(BookError):
            open_book(path)

    def test_damaged_epub(self):
        path = os.path.join(self.tmp, "broken.epub")
        with open(path, "wb") as fh:
            fh.write(b"not a zip")
        with self.assertRaises(BookError):
            open_book(path)


if __name__ == "__main__":
    unittest.main()
