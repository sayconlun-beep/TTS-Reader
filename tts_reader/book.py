"""Books as sentences: the splitter plus the EPUB and PDF parsers.

Ported from the rice's GTK tts-reader. The EPUB side is unchanged; PDFs go
through PyMuPDF instead of Poppler, which has no Windows wheels.
"""

import os
import posixpath
import re
import zipfile
from urllib.parse import unquote

from lxml import etree


class BookError(Exception):
    pass


# -- text -------------------------------------------------------------------
ABBRS = {"mr", "mrs", "ms", "dr", "prof", "st", "vs", "etc", "no", "fig",
         "al", "jr", "sr", "capt", "lt", "sgt", "rev", "hon", "inc", "ltd"}


def split_sentences(para):
    out, start = [], 0
    for m in re.finditer(r"[.!?]+[\"')\]”’]*\s+", para):
        head = para[start:m.start()]
        last = re.search(r"([A-Za-z.]+)$", head)
        if last and last.group(1).lower().strip(".") in ABBRS:
            continue          # "Mr. Darcy", not two sentences
        nxt = para[m.end():m.end() + 1]
        if nxt and nxt.islower():
            continue          # dialogue plus its attribution stays together
        out.append(para[start:m.end()].strip())
        start = m.end()
    tail = para[start:].strip()
    if tail:
        out.append(tail)
    result = []
    for s in out:
        # A very long sentence would sit highlighted for far too long, so
        # break it at clause boundaries.
        if len(s.split()) > 45:
            cur = []
            for piece in re.split(r"(?<=[,;:—])\s+", s):
                cur.append(piece)
                if len(" ".join(cur).split()) >= 25:
                    result.append(" ".join(cur))
                    cur = []
            if cur:
                result.append(" ".join(cur))
        else:
            result.append(s)
    return [s for s in result if re.search(r"\w", s)]


class Book:
    """Sentences plus the structure needed to lay them out and navigate.

    paragraphs: [(is_heading, first_sentence, end_sentence)]
    chapters:   [(title, depth, first_sentence)]
    """

    def __init__(self, path, title):
        self.path = path
        self.title = title
        self.sentences = []
        self.headings = set()        # sentence indices that are headings
        self.paragraphs = []
        self.chapters = []

    def add_para(self, text, heading=False):
        text = " ".join(text.split())
        if not text:
            return
        parts = [text] if heading else split_sentences(text)
        if not parts or not re.search(r"\w", text):
            return
        lo = len(self.sentences)
        self.sentences.extend(parts)
        if heading:
            self.headings.add(lo)
        self.paragraphs.append((heading, lo, len(self.sentences)))

    def spoken(self, i):
        s = self.sentences[i]
        # Headings have no full stop, so piper would run them into the
        # first sentence of the chapter.
        if i in self.headings and not re.search(r"[.!?:]$", s):
            s += "."
        return s

    def chapter_at(self, i):
        """Index into self.chapters of the chapter containing sentence i."""
        best = -1
        for n, (_t, _d, start) in enumerate(self.chapters):
            if start <= i:
                best = n
            else:
                break
        return best

    def words_between(self, lo, hi):
        return sum(len(s.split()) for s in self.sentences[lo:hi])


def open_book(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".epub":
        book = parse_epub(path)
    elif ext == ".pdf":
        book = parse_pdf(path)
    else:
        raise BookError("Only EPUB and PDF files can be opened.")
    if not book.sentences:
        raise BookError("No readable text was found in this file.")
    # Chapters must be in reading order for chapter_at() and the sidebar.
    book.chapters.sort(key=lambda c: c[2])
    if not book.chapters:
        book.chapters = [(book.title, 0, 0)]
    return book


# -- EPUB -------------------------------------------------------------------
BLOCK = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote",
         "pre", "section", "article", "td", "th", "dd", "dt", "figcaption",
         "tr", "header", "footer", "aside", "nav", "ul", "ol", "table",
         "body", "hr", "figure", "caption"}
SKIP = {"script", "style", "head", "title", "svg", "math", "rt", "rp"}
XML = etree.XMLParser(recover=True, resolve_entities=False, no_network=True,
                      huge_tree=True)


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _xml(data):
    root = etree.fromstring(data, XML)
    if root is None:
        raise BookError("A file inside the EPUB could not be parsed.")
    return root


def _find_all(root, name):
    return [e for e in root.iter() if _local(e.tag) == name]


def parse_epub(path):
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        raise BookError("This EPUB is damaged or not really an EPUB.")
    names = set(z.namelist())

    def read(name):
        if name not in names:
            raise KeyError(name)
        return z.read(name)

    try:
        container = _xml(read("META-INF/container.xml"))
        opf_path = _find_all(container, "rootfile")[0].get("full-path")
        opf = _xml(read(opf_path))
    except (KeyError, IndexError):
        raise BookError("This EPUB has no package file.")
    base = posixpath.dirname(opf_path)

    def resolve(rel, frm):
        rel = unquote(rel.split("#", 1)[0])
        return posixpath.normpath(posixpath.join(frm, rel)) if rel else ""

    titles = [e.text for e in _find_all(opf, "title") if e.text]
    title = titles[0].strip() if titles else os.path.splitext(
        os.path.basename(path))[0]
    book = Book(path, title)

    manifest = {}
    nav_path = ncx_path = None
    for item in _find_all(opf, "item"):
        href = resolve(item.get("href", ""), base)
        manifest[item.get("id")] = href
        if "nav" in (item.get("properties") or "").split():
            nav_path = href
        if item.get("media-type") == "application/x-dtbncx+xml":
            ncx_path = href
    spine_el = _find_all(opf, "spine")
    toc_id = spine_el[0].get("toc") if spine_el else None
    if toc_id in manifest:
        ncx_path = manifest[toc_id]

    anchors = {}       # (doc, id or None) -> sentence index
    doc_titles = []    # fallback chapters: (title, first sentence)
    for ref in _find_all(opf, "itemref"):
        if ref.get("linear") == "no":
            continue
        doc = manifest.get(ref.get("idref"))
        if not doc or doc not in names or doc == nav_path:
            continue
        anchors[(doc, None)] = len(book.sentences)
        try:
            root = _xml(read(doc))
        except BookError:
            continue
        first_heading = []
        _walk_xhtml(root, book, doc, anchors, first_heading)
        heading = first_heading[0] if first_heading else None
        if anchors[(doc, None)] < len(book.sentences):
            doc_titles.append((heading or f"Section {len(doc_titles) + 1}",
                               anchors[(doc, None)]))

    def target(href, frm):
        doc = resolve(href, frm)
        frag = unquote(href.split("#", 1)[1]) if "#" in href else None
        if (doc, frag) in anchors:
            return anchors[(doc, frag)]
        return anchors.get((doc, None))

    total = len(book.sentences)
    if nav_path and nav_path in names:
        nav = _xml(read(nav_path))
        navs = _find_all(nav, "nav")
        tocs = [n for n in navs if any(
            k.endswith("type") and "toc" in v for k, v in n.attrib.items())]
        top = (tocs or navs or [None])[0]
        if top is not None:
            frm = posixpath.dirname(nav_path)

            def walk_ol(ol, depth):
                for li in ol:
                    if _local(li.tag) != "li":
                        continue
                    link = next((e for e in li.iter() if _local(e.tag) in
                                 ("a", "span")), None)
                    if link is not None:
                        label = " ".join("".join(link.itertext()).split())
                        idx = target(link.get("href", ""), frm) \
                            if link.get("href") else None
                        if label and idx is not None and idx < total:
                            book.chapters.append((label, depth, idx))
                    for sub in li:
                        if _local(sub.tag) == "ol":
                            walk_ol(sub, depth + 1)

            for ol in top:
                if _local(ol.tag) == "ol":
                    walk_ol(ol, 0)
    if not book.chapters and ncx_path and ncx_path in names:
        ncx = _xml(read(ncx_path))
        frm = posixpath.dirname(ncx_path)

        def walk_np(parent, depth):
            for np_ in parent:
                if _local(np_.tag) != "navpoint":
                    continue
                label = next((" ".join("".join(e.itertext()).split())
                              for e in np_ if _local(e.tag) == "navlabel"), "")
                src = next((e.get("src") for e in np_
                            if _local(e.tag) == "content"), None)
                idx = target(src, frm) if src else None
                if label and idx is not None and idx < total:
                    book.chapters.append((label, depth, idx))
                walk_np(np_, depth + 1)

        for nm in _find_all(ncx, "navmap"):
            walk_np(nm, 0)
    if not book.chapters:
        book.chapters = [(t, 0, i) for t, i in doc_titles]
    # Text-less entries (a cover) share a sentence with the next real entry.
    # Keep the LAST label for each (sentence, depth), so the sidebar shows
    # "Chapter 1" rather than "Cover" at that spot.
    seen, uniq = set(), []
    for label, depth, idx in reversed(book.chapters):
        if (idx, depth) not in seen:
            seen.add((idx, depth))
            uniq.append((label, depth, idx))
    book.chapters = list(reversed(uniq))
    return book


def _walk_xhtml(root, book, doc, anchors, first_heading):
    bodies = _find_all(root, "body")
    buf = []
    state = {"heading": False}

    def flush():
        text = "".join(buf)
        buf.clear()
        if text.strip():
            if state["heading"] and not first_heading:
                first_heading.append(" ".join(text.split()))
            book.add_para(text, heading=state["heading"])

    def walk(el):
        name = _local(el.tag)
        if name in SKIP or not isinstance(el.tag, str):
            return
        el_id = el.get("id")
        if el_id:
            # Before a flush the buffer belongs to the paragraph this anchor
            # sits in, so it lands on that paragraph's first sentence.
            anchors[(doc, el_id)] = len(book.sentences)
        block = name in BLOCK
        is_heading = name in ("h1", "h2", "h3", "h4", "h5", "h6")
        if block:
            flush()
            if is_heading:
                state["heading"] = True
        if name == "br":
            buf.append(" ")
        if el.text:
            buf.append(el.text)
        for child in el:
            walk(child)
            if child.tail:
                buf.append(child.tail)
        if block:
            flush()
            if is_heading:
                state["heading"] = False

    for body in bodies or [root]:
        walk(body)
    flush()


# -- PDF --------------------------------------------------------------------
PAGE_NO = re.compile(r"^\W*(\d{1,4}|[ivxlcdm]{1,6})\W*$", re.I)
SENT_END = re.compile(r"[.!?:\"')\]”’]$")


def parse_pdf(path):
    import pymupdf

    try:
        doc = pymupdf.open(path)
    except Exception:
        doc = None
    if doc is None or not doc.is_pdf or doc.needs_pass:
        raise BookError("Couldn't open this PDF - it may be encrypted or "
                        "damaged.")
    with doc:
        title = ((doc.metadata or {}).get("title") or "").strip() or \
            os.path.splitext(os.path.basename(path))[0]
        n = doc.page_count
        pages = [[ln.strip() for ln in (page.get_text("text") or "").splitlines()]
                 for page in doc]
        outline = []    # (title, depth, page index)
        for level, label, page, *_rest in doc.get_toc(simple=True):
            label = " ".join((label or "").split())
            if label and 1 <= page <= n:
                outline.append((label, max(level - 1, 0), page - 1))
    book = Book(path, title)
    if not any(any(ln for ln in pg) for pg in pages):
        raise BookError("This PDF has no text layer - it's probably scanned "
                        "images, which can't be read aloud.")

    heading_titles = {}
    for label, _d, page in outline:
        heading_titles.setdefault(page, set()).add(label.casefold())

    # Running headers and footers: the same first/last line (digits ignored)
    # on a good share of pages is furniture, not prose.
    def norm(ln):
        return re.sub(r"\d+", "#", ln.casefold())

    edge_counts = {}
    for pg in pages:
        lines = [ln for ln in pg if ln]
        for ln in {*(lines[:1]), *(lines[-1:])}:
            edge_counts[norm(ln)] = edge_counts.get(norm(ln), 0) + 1
    furniture = {k for k, v in edge_counts.items()
                 if n >= 4 and v >= max(3, n * 0.3)}

    lengths = sorted(len(ln) for pg in pages for ln in pg if ln)
    typical = lengths[int(len(lengths) * 0.9)] if lengths else 80

    page_start = []
    heading_at = {}     # (page, title) -> sentence of that heading
    buf = []

    def flush(heading=False):
        if buf:
            book.add_para(" ".join(buf), heading=heading)
            buf.clear()

    for p, pg in enumerate(pages):
        lines = [ln for ln in pg if ln]
        while lines and (PAGE_NO.match(lines[0]) or norm(lines[0]) in furniture):
            lines.pop(0)
        while lines and (PAGE_NO.match(lines[-1]) or norm(lines[-1]) in furniture):
            lines.pop()
        # A paragraph that ended at the bottom of the last page must not
        # swallow this page's opening, or the page anchor lands a page early.
        if buf and SENT_END.search(buf[-1]):
            flush()
        page_start.append(len(book.sentences) if not buf else None)
        titles = heading_titles.get(p, set())
        for ln in lines:
            if ln.casefold() in titles:
                flush()
                buf.append(ln)
                flush(heading=True)
                heading_at.setdefault((p, ln.casefold()), len(book.sentences) - 1)
                if page_start[p] is None:
                    page_start[p] = len(book.sentences) - 1
                continue
            if buf and buf[-1].endswith("-") and len(buf[-1]) > 1 \
                    and buf[-1][-2].isalpha() and ln[:1].islower():
                buf[-1] = buf[-1][:-1] + ln        # re-join a hyphenated word
            else:
                buf.append(ln)
            if SENT_END.search(ln) and len(ln) < typical * 0.8:
                flush()
        if page_start[p] is None:
            # The page opened mid-paragraph: point at that paragraph.
            page_start[p] = len(book.sentences)
    flush()
    total = len(book.sentences)
    page_start = [min(s, max(total - 1, 0)) for s in page_start]

    if outline:
        book.chapters = [(t, d, heading_at.get((p, t.casefold()), page_start[p]))
                         for t, d, p in outline]
    else:
        book.chapters = [(f"Page {p + 1}", 0, page_start[p]) for p in range(n)
                         if any(pages[p])]
    return book
