import os
import tempfile
import unittest

from tts_reader import selftest
from tts_reader.book import Book, BookError, open_book, split_sentences


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

    def test_markdown(self):
        book = open_book(selftest.make_markdown(os.path.join(self.tmp, "a.md")))
        self.assertEqual(book.title, "Sample Notes")
        self.assertEqual(book.sentences, selftest.MARKDOWN_SENTENCES)
        self.assertEqual(book.chapters, selftest.MARKDOWN_CHAPTERS)

    def test_markdown_title_from_first_heading(self):
        path = os.path.join(self.tmp, "b.markdown")
        with open(path, "w") as fh:
            fh.write("Intro text.\n\n# Real Title\n\nBody.\n")
        book = open_book(path)
        self.assertEqual(book.title, "Real Title")
        self.assertEqual(book.chapters, [("Real Title", 0, 1)])

    def test_docx(self):
        book = open_book(selftest.make_docx(os.path.join(self.tmp, "a.docx")))
        self.assertEqual(book.title, "Sample Report")
        self.assertEqual(book.sentences, selftest.DOCX_SENTENCES)
        self.assertEqual(book.chapters, selftest.DOCX_CHAPTERS)
        self.assertEqual(book.spoken(1), "Overview.")

    def test_damaged_docx(self):
        path = os.path.join(self.tmp, "broken.docx")
        with open(path, "wb") as fh:
            fh.write(b"PK\x03\x04\x00\xff truncated")
        with self.assertRaises(BookError):
            open_book(path)

    def test_markdown_named_docx(self):
        path = os.path.join(self.tmp, "export.docx")
        with open(path, "w") as fh:
            fh.write("# Heading\n\nActually *Markdown*.\n")
        self.assertEqual(open_book(path).sentences, ["Heading", "Actually Markdown."])

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


class ParagraphTests(unittest.TestCase):
    def test_paragraph_at_maps_sentences_to_their_paragraph(self):
        book = Book("test", "Test")
        book.add_para("Title", heading=True)
        book.add_para("One. Two. Three.")
        book.add_para("Four.")
        self.assertEqual([book.paragraph_at(i) for i in range(5)], [0, 1, 1, 1, 2])
        self.assertEqual(book.paragraph_text(1), "One. Two. Three.")


if __name__ == "__main__":
    unittest.main()
