"""The window - a Qt port of the rice's GTK/libadwaita tts-reader."""

import bisect
import itertools
import os
import time
from pathlib import Path

from PySide6.QtCore import (QByteArray, QEasingCurve, QEvent, QPropertyAnimation,
                            QSize, Qt, QThreadPool, QTimer, QUrl, Signal)
from PySide6.QtGui import (QAction, QActionGroup, QColor, QDesktopServices, QFont,
                           QKeySequence, QPainter, QPalette, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTextDocument)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QMainWindow, QMenu, QProgressBar,
                               QProxyStyle, QPushButton, QSizePolicy, QSlider,
                               QSplitter, QStackedWidget, QStyle,
                               QSystemTrayIcon, QTextEdit, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import icons, paths
from .book import BookError, open_book
from .engine import Player
from .library import Library

WPM = 160           # for the time-left estimate at 1.0x
SPEEDS = ["0.75", "0.9", "1.0", "1.1", "1.25", "1.5", "1.75", "2.0"]
SLEEPS = [("off", "Off"), ("15", "15 minutes"), ("30", "30 minutes"),
          ("45", "45 minutes"), ("60", "1 hour"), ("chapter", "End of chapter")]
DEFAULT_TEXT_SIZE = 14

# Tokyo Night with the cyan accent, like the rice.
COLORS = {
    "@accenthover": "#9ddcff",
    "@accentfg": "#16161e",
    "@accent": "#7dcfff",
    "@surface": "#1f2335",
    "@raised": "#292e42",
    "@border": "#2f334d",
    "@base": "#16161e",
    "@bg": "#1a1b26",
    "@fg": "#c0caf5",
    "@dim": "#737aa2",
    "@off": "#545c7e",
}
FG, DIM, ACCENT, ACCENT_FG = (COLORS[k] for k in ("@fg", "@dim", "@accent",
                                                  "@accentfg"))

STYLE = """
QToolTip { background: @surface; color: @fg; border: 1px solid @border;
           padding: 4px 6px; }
#header { background: @bg; border-bottom: 1px solid @border; }
#playerBar { background: @bg; border-top: 1px solid @border; }
#title { font-weight: 600; }
#subtitle, #dim { color: @dim; }
#h1 { font-size: 20pt; font-weight: 700; }
#heading { font-weight: 700; }
QToolButton { border: none; border-radius: 8px; padding: 6px; color: @fg; }
QToolButton:hover { background: @raised; }
QToolButton:pressed, QToolButton:checked { background: @border; }
QToolButton:disabled { color: @off; }
QToolButton::menu-indicator { image: none; width: 0; }
#playButton { background: @accent; border-radius: 26px; }
#playButton:hover { background: @accenthover; }
QPushButton#pill { background: @accent; color: @accentfg; border: none;
                   border-radius: 16px; padding: 8px 22px; min-height: 18px;
                   font-weight: 600; }
QPushButton#pill:hover { background: @accenthover; }
QPushButton#recentRow { background: @surface; border: none; border-radius: 10px;
                        text-align: left; }
QPushButton#recentRow:hover { background: @raised; }
#rowTitle { font-weight: 600; }
QTextEdit#reader { background: @base; border: none; }
QTreeWidget#chapters { background: @bg; border: none; outline: 0; padding: 6px; }
QTreeWidget#chapters::item { padding: 6px 4px; border-radius: 6px; color: @fg; }
QTreeWidget#chapters::item:hover { background: @surface; }
QTreeWidget#chapters::item:selected { background: @raised; color: @accent; }
QTreeWidget#chapters::branch { background: transparent; }
QSplitter::handle { background: @border; }
QSlider::groove:horizontal { height: 4px; background: @raised; border-radius: 2px; }
QSlider::sub-page:horizontal { background: @accent; border-radius: 2px; }
QSlider::handle:horizontal { background: @fg; width: 14px; height: 14px;
                             margin: -5px 0; border-radius: 7px; }
QComboBox { background: @raised; color: @fg; border: none; border-radius: 8px;
            padding: 5px 10px; }
QComboBox:disabled { color: @off; }
QComboBox::drop-down { border: none; width: 16px; }
QComboBox QAbstractItemView { background: @surface; color: @fg; border: 1px solid @border;
                              selection-background-color: @raised;
                              selection-color: @accent; outline: 0; }
QMenu { background: @surface; color: @fg; border: 1px solid @border; padding: 4px; }
QMenu::item { padding: 6px 24px 6px 24px; border-radius: 6px; }
QMenu::item:selected { background: @raised; }
QMenu::item:disabled { color: @off; }
QMenu::separator { height: 1px; background: @border; margin: 4px 8px; }
#toast { background: @surface; color: @fg; border: 1px solid @border;
         border-radius: 16px; padding: 8px 18px; }
QProgressBar { background: @raised; border: none; border-radius: 3px; }
QProgressBar::chunk { background: @accent; border-radius: 3px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @raised; border-radius: 3px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: @border; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""


class Style(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        # Clicking the progress bar jumps there instead of paging.
        if hint == QStyle.StyleHint.SH_Slider_AbsoluteSetButtons:
            return Qt.MouseButton.LeftButton.value
        return super().styleHint(hint, option, widget, returnData)


def apply_theme(app):
    app.setStyle(Style("Fusion"))
    pal = QPalette()
    roles = QPalette.ColorRole
    for role, key in [(roles.Window, "@bg"), (roles.WindowText, "@fg"),
                      (roles.Base, "@base"), (roles.AlternateBase, "@surface"),
                      (roles.Text, "@fg"), (roles.Button, "@raised"),
                      (roles.ButtonText, "@fg"), (roles.Highlight, "@accent"),
                      (roles.HighlightedText, "@accentfg"),
                      (roles.ToolTipBase, "@surface"), (roles.ToolTipText, "@fg"),
                      (roles.PlaceholderText, "@dim"), (roles.Link, "@accent")]:
        pal.setColor(role, QColor(COLORS[key]))
    for role in (roles.Text, roles.ButtonText, roles.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(COLORS["@off"]))
    app.setPalette(pal)
    style = STYLE
    for token in sorted(COLORS, key=len, reverse=True):
        style = style.replace(token, COLORS[token])
    app.setStyleSheet(style)


def voice_label(name):
    parts = name.split("-")
    if len(parts) >= 2:
        return f"{parts[1].replace('_', ' ').title()} ({parts[0]})"
    return name


def time_left_label(minutes):
    minutes = int(round(minutes))
    if minutes < 1:
        return "under a minute left"
    h, m = divmod(minutes, 60)
    return f"{h} h {m} min left" if h else f"{m} min left"


def _u16(s):
    """QTextDocument positions count UTF-16 units, not code points."""
    return len(s.encode("utf-16-le")) // 2


def _code(key):
    return getattr(key, "value", key)


class ElidedLabel(QLabel):
    def __init__(self, text="", name=None):
        super().__init__(text)
        if name:
            self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight,
                                             self.width())
        painter.drawText(self.rect(), int(self.alignment().value), text)


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWordWrap(True)
        self.hide()
        self.above = None               # widget the toast sits just above
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self.hide)

    def show_message(self, text):
        self.setText(text)
        self.place()
        self.show()
        self.raise_()
        self.timer.start()

    def place(self):
        parent = self.parentWidget()
        self.setMaximumWidth(max(200, parent.width() - 48))
        self.adjustSize()
        bottom = parent.height()
        if self.above is not None and self.above.isVisible():
            bottom = self.above.y()
        self.move((parent.width() - self.width()) // 2, bottom - self.height() - 16)


class SentenceView(QTextEdit):
    """The book's text; click a sentence to read from it."""

    sentenceClicked = Signal(int)
    userScrolled = Signal()
    zoomRequested = Signal(int)
    MAX_WIDTH = 720

    def __init__(self):
        super().__init__()
        self.setObjectName("reader")
        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAcceptDrops(False)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.starts, self.ends, self.heads = [], [], []
        self.own_doc = None
        self.current = None
        self.press_pos = None
        self.point_size = DEFAULT_TEXT_SIZE
        self.anim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self.anim.setDuration(220)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.verticalScrollBar().sliderPressed.connect(self.userScrolled)
        self.set_point_size(self.point_size)

    def set_point_size(self, size):
        self.point_size = size
        font = QFont(self.font())
        font.setPointSizeF(size)
        self.setFont(font)
        self.document().setDefaultFont(font)
        self._format_headings()

    def _format_headings(self):
        if not self.heads:
            return
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setFontPointSize(self.point_size * 1.4)
        cur = QTextCursor(self.document())
        cur.beginEditBlock()
        for a, b in self.heads:
            cur.setPosition(a)
            cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            cur.mergeCharFormat(fmt)
        cur.endEditBlock()

    def load(self, book):
        doc = QTextDocument(self)
        doc.setUndoRedoEnabled(False)
        doc.setDefaultFont(self.font())
        para = QTextBlockFormat()
        para.setBottomMargin(14)
        para.setLineHeight(135, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        head = QTextBlockFormat(para)
        head.setTopMargin(30)
        head.setBottomMargin(20)
        plain = QTextCharFormat()
        starts, ends, heads = [], [], []
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        for n, (heading, lo, hi) in enumerate(book.paragraphs):
            if n == 0:
                cur.setBlockFormat(head if heading else para)
            else:
                cur.insertBlock(head if heading else para, plain)
            off = first = cur.position()
            texts = book.sentences[lo:hi]
            for k, s in enumerate(texts):
                if k:
                    off += 1
                starts.append(off)
                off += _u16(s)
                ends.append(off)
            cur.insertText(" ".join(texts), plain)
            if heading:
                heads.append((first, off))
        cur.endEditBlock()
        doc.setDocumentMargin(4)
        self.setDocument(doc)
        doc.setDefaultFont(self.font())
        # Only ours: QTextEdit deletes the default document itself.
        if self.own_doc is not None:
            self.own_doc.deleteLater()
        self.own_doc = doc
        self.starts, self.ends, self.heads = starts, ends, heads
        self._format_headings()
        self.current = None
        self.setExtraSelections([])
        self._update_margins()

    def highlight(self, i, scroll, animate=True):
        if not self.starts:
            return
        i = max(0, min(i, len(self.starts) - 1))
        cur = QTextCursor(self.document())
        cur.setPosition(self.starts[i])
        cur.setPosition(self.ends[i], QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextCharFormat()
        color = QColor(ACCENT)
        color.setAlphaF(0.28)
        fmt.setBackground(color)
        sel = QTextEdit.ExtraSelection()
        sel.cursor = cur
        sel.format = fmt
        self.setExtraSelections([sel])
        self.current = i
        if scroll:
            self.scroll_to(i, animate)

    def scroll_to(self, i, animate=True):
        cur = QTextCursor(self.document())
        cur.setPosition(self.starts[i])
        bar = self.verticalScrollBar()
        target = bar.value() + self.cursorRect(cur).top() - \
            int(self.viewport().height() * 0.3)
        target = max(bar.minimum(), min(target, bar.maximum()))
        self.anim.stop()
        if abs(target - bar.value()) < 2:
            return
        if animate and abs(target - bar.value()) < self.viewport().height() * 2:
            self.anim.setStartValue(bar.value())
            self.anim.setEndValue(target)
            self.anim.start()
        else:
            bar.setValue(target)

    def _update_margins(self):
        side = max(28, (self.width() - self.MAX_WIDTH) // 2)
        self.setViewportMargins(side, 36, side, 0)
        # Room to scroll the last sentence up to the reading line.
        frame = self.document().rootFrame().frameFormat()
        if frame.bottomMargin() != 160:
            frame.setBottomMargin(160)
            self.document().rootFrame().setFrameFormat(frame)

    def resizeEvent(self, event):
        # Margins first: QTextEdit re-wraps to the viewport width in its own
        # resizeEvent, and the viewport only shrinks once they are set.
        self._update_margins()
        super().resizeEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.zoomRequested.emit(1 if delta > 0 else -1)
            return
        self.anim.stop()
        self.userScrolled.emit()
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        if _code(event.key()) in (_code(Qt.Key.Key_PageUp), _code(Qt.Key.Key_PageDown),
                                  _code(Qt.Key.Key_Up), _code(Qt.Key.Key_Down),
                                  _code(Qt.Key.Key_Home), _code(Qt.Key.Key_End)):
            self.userScrolled.emit()
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self.press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton or self.press_pos is None \
                or not self.starts:
            return
        point = event.position().toPoint()
        moved = (point - self.press_pos).manhattanLength() > 4
        self.press_pos = None
        if moved or self.textCursor().hasSelection():
            return
        pos = self.cursorForPosition(point).position()
        k = bisect.bisect_right(self.starts, pos) - 1
        if k >= 0 and pos <= self.ends[k]:
            self.sentenceClicked.emit(k)


class ReaderPane(QWidget):
    """The text with a floating "Back to Current Sentence" button."""

    def __init__(self, view, button):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)
        button.setParent(self)
        self.button = button

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.place()

    def place(self):
        b = self.button
        b.adjustSize()
        b.move((self.width() - b.width()) // 2, self.height() - b.height() - 18)
        b.raise_()


class MainWindow(QMainWindow):
    bookLoaded = Signal(str, object, str, int)
    EMPTY, LOADING, READER = range(3)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.lib = Library()
        self.player = Player()
        self.book = None
        self.pos = 0
        self.words_after = [0]
        self.follow = True
        self.syncing = False                # programmatic widget updates
        self.chapter_items = []
        self.current_chapter = -1
        self.sleep_deadline = self.sleep_chapter = None
        self.voices = None
        self.tray = None
        self.tray_hint_shown = False
        self.text_size = self.lib.setting("text_size", DEFAULT_TEXT_SIZE)
        self.icon_play = icons.icon("play", ACCENT_FG)
        self.icon_pause = icons.icon("pause", ACCENT_FG)

        self.setWindowTitle(paths.APP_NAME)
        self.setAcceptDrops(True)
        self.resize(1180, 820)
        geometry = self.lib.setting("geometry", None)
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))

        central = QWidget()
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.setCentralWidget(central)
        self._build_actions()
        column.addWidget(self._build_header())
        self.stack = QStackedWidget()
        column.addWidget(self.stack, 1)
        self._build_pages()
        self.player_bar = self._build_player_bar()
        column.addWidget(self.player_bar)
        self.toast_label = Toast(central)
        self.toast_label.above = self.player_bar

        self.save_timer = self._timer(3000, self.save_position)
        self.scale_timer = self._timer(250, lambda: self.jump_to(self.slider.value()))
        self.sleep_timer = self._timer(5000, self._sleep_tick, single=False)

        p = self.player
        p.position.connect(self._on_position)
        p.paused.connect(self._on_paused)
        p.stopped.connect(self._on_stopped)
        p.ended.connect(self._on_ended)
        p.error.connect(self.toast)
        self.bookLoaded.connect(self._book_loaded)
        app.installEventFilter(self)

        self.view.set_point_size(self.text_size)
        self._refresh_voices()
        if self._voice():
            self.player.preload(self._voice())
        self._fill_recent()
        self._show_page(self.EMPTY)

    def _timer(self, interval, slot, single=True):
        t = QTimer(self)
        t.setSingleShot(single)
        t.setInterval(interval)
        t.timeout.connect(slot)
        return t

    # -- construction --------------------------------------------------------
    def _build_actions(self):
        def act(text, slot, shortcuts=()):
            a = QAction(text, self)
            a.setShortcuts([QKeySequence(s) for s in shortcuts])
            a.triggered.connect(slot)
            self.addAction(a)
            return a

        self.act_open = act("Open Book…", self.choose_file, ["Ctrl+O"])
        self.act_close = act("Close Book", self.close_book, ["Ctrl+W"])
        self.act_sidebar = act("Chapters", lambda: self.sidebar_btn.toggle(), ["F9"])
        self.act_zoom_in = act("Larger Text", lambda: self.set_text_size(
            self.text_size + 1), ["Ctrl++", "Ctrl+="])
        self.act_zoom_out = act("Smaller Text", lambda: self.set_text_size(
            self.text_size - 1), ["Ctrl+-"])
        self.act_zoom_reset = act("Reset Text Size", lambda: self.set_text_size(
            DEFAULT_TEXT_SIZE), ["Ctrl+0"])
        self.act_voices = act("Add Voices…", self.open_voices_folder)
        self.act_quit = act("Quit", self.quit_app, ["Ctrl+Q"])

    def _tool(self, icon_name, tip, slot=None, size=20):
        b = QToolButton()
        b.setIcon(icons.icon(icon_name, FG))
        b.setIconSize(QSize(size, size))
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if slot:
            b.clicked.connect(lambda _checked=False: slot())
        return b

    def _menu_button(self, button, menu):
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        return button

    def _build_header(self):
        header = QWidget()
        header.setObjectName("header")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        grid = QGridLayout(header)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 1)

        left = QHBoxLayout()
        left.setSpacing(2)
        self.sidebar_btn = self._tool("chapters", "Chapters (F9)")
        self.sidebar_btn.setCheckable(True)
        self.sidebar_btn.setChecked(True)
        self.sidebar_btn.toggled.connect(lambda on: self.chapter_tree.setVisible(on))
        left.addWidget(self.sidebar_btn)
        left.addWidget(self._tool("open", "Open a book (Ctrl+O)", self.choose_file))
        self.recent_menu = QMenu(self)
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        left.addWidget(self._menu_button(self._tool("recent", "Recent books"),
                                         self.recent_menu))
        left.addStretch(1)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title_label = ElidedLabel(paths.APP_NAME, "title")
        self.subtitle_label = ElidedLabel("", "subtitle")
        for label in (self.title_label, self.subtitle_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            titles.addWidget(label)
        self.subtitle_label.hide()

        right = QHBoxLayout()
        right.addStretch(1)
        menu = QMenu(self)
        for a in (self.act_zoom_in, self.act_zoom_out, self.act_zoom_reset):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(self.act_voices)
        menu.addAction(self.act_close)
        menu.addSeparator()
        menu.addAction(self.act_quit)
        right.addWidget(self._menu_button(self._tool("menu", "Menu"), menu))

        grid.addLayout(left, 0, 0)
        grid.addLayout(titles, 0, 1)
        grid.addLayout(right, 0, 2)
        return header

    def _build_pages(self):
        # Nothing open.
        empty = QWidget()
        outer = QVBoxLayout(empty)
        outer.addStretch(1)
        col = QWidget()
        col.setMinimumWidth(320)
        col.setMaximumWidth(460)
        v = QVBoxLayout(col)
        v.setSpacing(10)
        art = QLabel()
        art.setPixmap(icons.pixmap("book", DIM, 72, self.devicePixelRatioF()))
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h1 = QLabel("Open a Book")
        h1.setObjectName("h1")
        desc = QLabel("EPUB or PDF, or drop a file onto this window")
        desc.setObjectName("dim")
        for label in (h1, desc):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        open_btn = QPushButton("Open Book…")
        open_btn.setObjectName("pill")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(lambda _checked=False: self.choose_file())
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(open_btn)
        row.addStretch(1)
        self.recent_heading = QLabel("Recent")
        self.recent_heading.setObjectName("heading")
        self.recent_list = QVBoxLayout()
        self.recent_list.setSpacing(6)
        v.addWidget(art)
        v.addWidget(h1)
        v.addWidget(desc)
        v.addSpacing(8)
        v.addLayout(row)
        v.addSpacing(18)
        v.addWidget(self.recent_heading)
        v.addLayout(self.recent_list)
        outer.addWidget(col, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)
        self.stack.addWidget(empty)

        # Parsing.
        loading = QWidget()
        lv = QVBoxLayout(loading)
        lv.addStretch(1)
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        bar.setFixedSize(180, 6)
        lv.addWidget(bar, 0, Qt.AlignmentFlag.AlignHCenter)
        opening = QLabel("Opening…")
        opening.setObjectName("dim")
        opening.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lv.addWidget(opening)
        lv.addStretch(1)
        self.stack.addWidget(loading)

        # Reading.
        self.view = SentenceView()
        self.view.sentenceClicked.connect(self.jump_to)
        self.view.userScrolled.connect(self._stop_follow)
        self.view.zoomRequested.connect(lambda d: self.set_text_size(self.text_size + d))
        self.follow_btn = QPushButton("Back to Current Sentence")
        self.follow_btn.setObjectName("pill")
        self.follow_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.follow_btn.clicked.connect(lambda _checked=False: self._resume_follow())
        self.follow_btn.hide()
        self.reader_pane = ReaderPane(self.view, self.follow_btn)

        self.chapter_tree = QTreeWidget()
        self.chapter_tree.setObjectName("chapters")
        self.chapter_tree.setHeaderHidden(True)
        self.chapter_tree.setRootIsDecorated(False)
        self.chapter_tree.setIndentation(16)
        self.chapter_tree.setExpandsOnDoubleClick(False)
        self.chapter_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chapter_tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.chapter_tree.setMinimumWidth(200)
        self.chapter_tree.itemClicked.connect(self._on_chapter_item)
        self.chapter_tree.itemActivated.connect(self._on_chapter_item)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.addWidget(self.chapter_tree)
        self.splitter.addWidget(self.reader_pane)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([290, 890])
        self.stack.addWidget(self.splitter)

    def _build_player_bar(self):
        bar = QWidget()
        bar.setObjectName("playerBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        v = QVBoxLayout(bar)
        v.setContentsMargins(18, 8, 18, 12)
        v.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("dim")
        self.percent_label.setMinimumWidth(40)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider.valueChanged.connect(self._on_slider)
        self.left_label = QLabel("")
        self.left_label.setObjectName("dim")
        self.left_label.setMinimumWidth(140)
        self.left_label.setAlignment(Qt.AlignmentFlag.AlignRight |
                                     Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.percent_label)
        top.addWidget(self.slider, 1)
        top.addWidget(self.left_label)

        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)

        self.sleep_btn = self._tool("alarm", "Sleep timer")
        self.sleep_btn.setText("Sleep")
        self.sleep_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        sleep_menu = QMenu(self)
        self.sleep_group = QActionGroup(self)
        for key, label in SLEEPS:
            a = sleep_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(key == "off")
            a.setData(key)
            self.sleep_group.addAction(a)
        self.sleep_group.triggered.connect(lambda a: self._on_sleep(a.data()))
        self._menu_button(self.sleep_btn, sleep_menu)

        transport = QHBoxLayout()
        transport.setSpacing(6)
        for name, tip, slot in [
                ("skip-back", "Previous chapter (Ctrl+Left)", lambda: self.step_chapter(-1)),
                ("seek-back", "Previous sentence (Left)", lambda: self.step_sentence(-1)),
                (None, None, None),
                ("seek-forward", "Next sentence (Right)", lambda: self.step_sentence(1)),
                ("skip-forward", "Next chapter (Ctrl+Right)", lambda: self.step_chapter(1))]:
            if name is None:
                self.play_btn = QToolButton()
                self.play_btn.setObjectName("playButton")
                self.play_btn.setIcon(self.icon_play)
                self.play_btn.setIconSize(QSize(28, 28))
                self.play_btn.setFixedSize(52, 52)
                self.play_btn.setToolTip("Play / pause (Space)")
                self.play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                self.play_btn.clicked.connect(lambda _checked=False: self.toggle_play())
                transport.addWidget(self.play_btn)
            else:
                transport.addWidget(self._tool(name, tip, slot, size=24))

        end = QHBoxLayout()
        end.setSpacing(6)
        end.addStretch(1)
        speed = self.lib.setting("speed", "1.0")
        self.speed_btn = QToolButton()
        self.speed_btn.setText(f"{speed}×")
        self.speed_btn.setToolTip("Reading speed")
        self.speed_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        speed_menu = QMenu(self)
        group = QActionGroup(self)
        for s in SPEEDS:
            a = speed_menu.addAction(f"{s}×")
            a.setCheckable(True)
            a.setChecked(s == speed)
            a.setData(s)
            group.addAction(a)
        group.triggered.connect(lambda a: self._on_speed(a.data()))
        self._menu_button(self.speed_btn, speed_menu)
        self.voice_combo = QComboBox()
        self.voice_combo.setToolTip("Voice")
        self.voice_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.voice_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.voice_combo.currentIndexChanged.connect(self._on_voice)
        end.addWidget(self.speed_btn)
        end.addWidget(self.voice_combo)

        grid.addWidget(self.sleep_btn, 0, 0, Qt.AlignmentFlag.AlignLeft |
                       Qt.AlignmentFlag.AlignVCenter)
        grid.addLayout(transport, 0, 1)
        grid.addLayout(end, 0, 2)
        v.addLayout(top)
        v.addLayout(grid)
        return bar

    # -- pages & books -------------------------------------------------------
    def _show_page(self, index):
        self.stack.setCurrentIndex(index)
        self.player_bar.setVisible(index == self.READER)
        self.sidebar_btn.setEnabled(index == self.READER)
        self.act_close.setEnabled(self.book is not None)

    def toast(self, text):
        self.toast_label.show_message(text)

    def _recent(self):
        return [(p, b) for p, b in self.lib.recent()
                if not self.book or p != self.book.path]

    @staticmethod
    def _progress(entry):
        total = entry.get("total") or 0
        return int(100 * entry.get("pos", 0) / total) if total else 0

    def _fill_recent(self):
        while self.recent_list.count():
            widget = self.recent_list.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        recent = self._recent()
        self.recent_heading.setVisible(bool(recent))
        for path, entry in recent:
            row = QPushButton()
            row.setObjectName("recentRow")
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            row.setMinimumHeight(58)
            lay = QVBoxLayout(row)
            lay.setContentsMargins(14, 8, 14, 8)
            lay.setSpacing(2)
            lay.addWidget(ElidedLabel(entry.get("title") or os.path.basename(path),
                                      "rowTitle"))
            lay.addWidget(ElidedLabel(f"{self._progress(entry)}% · "
                                      f"{os.path.basename(path)}", "dim"))
            row.clicked.connect(lambda _checked=False, p=path: self.load_book(p))
            self.recent_list.addWidget(row)

    def _fill_recent_menu(self):
        self.recent_menu.clear()
        recent = self._recent()
        if not recent:
            self.recent_menu.addAction("No other recent books").setEnabled(False)
            return
        for path, entry in recent:
            title = (entry.get("title") or os.path.basename(path)).replace("&", "&&")
            a = self.recent_menu.addAction(f"{title}  ·  {self._progress(entry)}%")
            a.setToolTip(path)
            a.triggered.connect(lambda _checked=False, p=path: self.load_book(p))

    def choose_file(self):
        start = self.lib.setting("last_dir", "")
        if not start or not os.path.isdir(start):
            start = str(Path.home())
        path, _filter = QFileDialog.getOpenFileName(
            self, "Open a Book", start, "Books (*.epub *.pdf);;All files (*)")
        if path:
            self.load_book(path)

    @staticmethod
    def _dropped_book(event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith((".epub", ".pdf")):
                return url.toLocalFile()
        return None

    def dragEnterEvent(self, event):
        if self._dropped_book(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._dropped_book(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = self._dropped_book(event)
        if path:
            event.acceptProposedAction()
            self.load_book(path)

    def load_book(self, path):
        path = os.path.abspath(path)
        previous = self.stack.currentIndex()
        self._show_page(self.LOADING)

        def work():
            try:
                book, err = open_book(path), ""
            except BookError as e:
                book, err = None, str(e)
            except Exception as e:           # a malformed file, not a bug
                book, err = None, f"Couldn't read this file ({e})."
            self.bookLoaded.emit(path, book, err, previous)

        QThreadPool.globalInstance().start(work)

    def _book_loaded(self, path, book, err, previous):
        if err:
            self._show_page(previous if previous != self.LOADING else self.EMPTY)
            self.toast(err)
            return
        self.save_position()
        if self.player.running:
            self.player.stop()
        self._on_paused(True)
        self._cancel_sleep()
        self.book = book
        entry = self.lib.book(path)
        total = len(book.sentences)
        self.pos = max(0, min(entry.get("pos", 0), total - 1))
        self.lib.remember(path, title=book.title, total=total,
                          opened=time.time(), pos=self.pos)
        self.lib.set_setting("last_dir", os.path.dirname(path))
        self.lib.save()
        words = list(itertools.accumulate(len(s.split()) for s in book.sentences))
        self.words_after = [words[-1] - w + len(s.split())
                            for w, s in zip(words, book.sentences)]

        self.view.load(book)
        self._fill_chapters(book)
        self.current_chapter = -1
        self.syncing = True
        self.slider.setRange(0, max(1, total - 1))
        self.syncing = False
        self.title_label.setText(book.title)
        self.setWindowTitle(f"{book.title} – {paths.APP_NAME}")
        self._show_page(self.READER)
        self.follow = True
        self.follow_btn.hide()
        self._update_position(self.pos)
        # The text has no layout yet; scroll once it has been measured.
        QTimer.singleShot(150, lambda: self.book is book and
                          self.view.highlight(self.pos, True, animate=False))

    def _fill_chapters(self, book):
        self.chapter_tree.clear()
        self.chapter_items = []
        nested = any(d > 0 for _t, d, _s in book.chapters)
        bold = QFont(self.chapter_tree.font())
        bold.setBold(True)
        parents = []                    # (depth, item)
        for n, (title, depth, _start) in enumerate(book.chapters):
            while parents and parents[-1][0] >= depth:
                parents.pop()
            item = QTreeWidgetItem(parents[-1][1] if parents else self.chapter_tree,
                                   [title])
            item.setToolTip(0, title)
            item.setData(0, Qt.ItemDataRole.UserRole, n)
            if nested and depth == 0:
                item.setFont(0, bold)
            parents.append((depth, item))
            self.chapter_items.append(item)
        self.chapter_tree.expandAll()

    def close_book(self):
        if self.book is None:
            return
        self.save_position()
        self.player.stop()
        self._cancel_sleep()
        self.book = None
        self._on_paused(True)
        self.title_label.setText(paths.APP_NAME)
        self.subtitle_label.setText("")
        self.subtitle_label.hide()
        self.setWindowTitle(paths.APP_NAME)
        self._fill_recent()
        self._show_page(self.EMPTY)

    def save_position(self):
        self.save_timer.stop()
        if self.book:
            self.lib.remember(self.book.path, pos=self.pos)
            self.lib.save()

    def set_text_size(self, size):
        self.text_size = max(9, min(size, 32))
        self.view.set_point_size(self.text_size)
        self.lib.set_setting("text_size", self.text_size)
        self.lib.save()
        if self.book and self.follow:
            QTimer.singleShot(0, lambda: self.view.highlight(self.pos, True, False))

    # -- voices --------------------------------------------------------------
    def _voice(self):
        return self.voice_combo.currentData()

    def _speed(self):
        return float(self.lib.setting("speed", "1.0"))

    def _refresh_voices(self):
        voices = paths.list_voices()
        if self.voices is not None and list(voices) == list(self.voices):
            return
        self.voices = voices
        wanted = self._voice() or self.lib.setting("voice", paths.DEFAULT_VOICE)
        self.syncing = True
        self.voice_combo.clear()
        for name in voices:
            self.voice_combo.addItem(voice_label(name), name)
        if voices:
            index = self.voice_combo.findData(wanted)
            if index < 0:
                index = max(self.voice_combo.findData(paths.DEFAULT_VOICE), 0)
            self.voice_combo.setCurrentIndex(index)
        else:
            self.voice_combo.addItem("No voices installed")
        self.voice_combo.setEnabled(bool(voices))
        self.syncing = False
        if self._voice():
            self.player.set_voice(self._voice())

    def open_voices_folder(self):
        folder = paths.user_voices_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self.toast("Put piper voices (.onnx plus its .onnx.json) in this folder - "
                   "they appear when you switch back here.")

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self._refresh_voices()

    # -- transport -----------------------------------------------------------
    def _start(self, idx):
        voice = self._voice()
        if not voice:
            self.toast("No voices installed - see Menu › Add Voices…")
            return
        self.player.start(self.book, idx, voice, self._speed())

    def toggle_play(self):
        if self.book is None:
            return
        if self.player.running:
            self.player.toggle()
        else:
            self._start(self.pos)

    def jump_to(self, i):
        if self.book is None:
            return
        i = max(0, min(i, len(self.book.sentences) - 1))
        self.follow = True
        self.follow_btn.hide()
        if self.player.running:
            self.player.jump(i)
        else:
            self.pos = i
            self._start(i)
            if not self.player.running:
                self._update_position(i)

    def step_sentence(self, delta):
        self.jump_to(self.pos + delta)

    def step_chapter(self, delta):
        if not self.book:
            return
        starts = [c[2] for c in self.book.chapters]
        cur = self.book.chapter_at(self.pos)
        if delta < 0:
            # Like a CD player: back goes to the start of this chapter first,
            # unless we are already a few sentences into it.
            if cur >= 0 and self.pos - starts[cur] > 2:
                target = starts[cur]
            else:
                target = starts[cur - 1] if cur > 0 else 0
        else:
            later = [s for s in starts if s > self.pos]
            if not later:
                return
            target = later[0]
        self.jump_to(target)

    def _on_chapter_item(self, item, _column=0):
        if self.syncing or not self.book:
            return
        self.jump_to(self.book.chapters[item.data(0, Qt.ItemDataRole.UserRole)][2])

    def _on_slider(self, value):
        if self.syncing or not self.book:
            return
        self._update_labels(value)
        # Dragging fires continuously; only jump once it settles.
        self.scale_timer.start()

    def _on_speed(self, speed):
        self.speed_btn.setText(f"{speed}×")
        self.lib.set_setting("speed", speed)
        self.lib.save()
        self.player.set_speed(float(speed))
        if self.book:
            self._update_labels(self.pos)

    def _on_voice(self, _index):
        if self.syncing or not self._voice():
            return
        self.lib.set_setting("voice", self._voice())
        self.lib.save()
        self.player.set_voice(self._voice())

    # -- sleep timer ---------------------------------------------------------
    def _on_sleep(self, key):
        self._cancel_sleep(reset=False)
        if key == "chapter" and self.book:
            self.sleep_chapter = self.book.chapter_at(self.pos)
            self.sleep_btn.setText("End of chapter")
        elif key.isdigit():
            self.sleep_deadline = time.monotonic() + int(key) * 60
            self.sleep_timer.start()
            self._sleep_tick()

    def _sleep_tick(self):
        left = self.sleep_deadline - time.monotonic()
        if left <= 0:
            self.player.set_paused(True)
            self.toast("Sleep timer: paused")
            self._cancel_sleep()
            return
        self.sleep_btn.setText(f"{int(left // 60) + 1} min")

    def _cancel_sleep(self, reset=True):
        self.sleep_timer.stop()
        self.sleep_deadline = self.sleep_chapter = None
        self.sleep_btn.setText("Sleep")
        if reset:
            for a in self.sleep_group.actions():
                a.setChecked(a.data() == "off")

    # -- player events -------------------------------------------------------
    def _on_position(self, i):
        if not self.book:
            return
        self.pos = i
        self._update_position(i)
        if self.sleep_chapter is not None and \
                self.book.chapter_at(i) != self.sleep_chapter:
            self.player.set_paused(True)
            self.toast("Sleep timer: paused at the end of the chapter")
            self._cancel_sleep()
        if not self.save_timer.isActive():
            self.save_timer.start()

    def _update_position(self, i):
        self.view.highlight(i, self.follow)
        ch = self.book.chapter_at(i)
        if ch != self.current_chapter:
            self.current_chapter = ch
            self.syncing = True
            if 0 <= ch < len(self.chapter_items):
                item = self.chapter_items[ch]
                self.chapter_tree.setCurrentItem(item)
                self.chapter_tree.scrollToItem(
                    item, QAbstractItemView.ScrollHint.EnsureVisible)
            else:
                self.chapter_tree.clearSelection()
            self.syncing = False
            title = self.book.chapters[ch][0] if ch >= 0 else ""
            self.subtitle_label.setText(title)
            self.subtitle_label.setVisible(bool(title))
        if not self.scale_timer.isActive():
            self.syncing = True
            self.slider.setValue(i)
            self.syncing = False
        self._update_labels(i)

    def _update_labels(self, i):
        total = len(self.book.sentences)
        i = max(0, min(i, total - 1))
        self.percent_label.setText(f"{int(100 * i / max(total - 1, 1))}%")
        self.left_label.setText(time_left_label(
            self.words_after[i] / (WPM * self._speed())))

    def _on_paused(self, paused):
        self.play_btn.setIcon(self.icon_play if paused else self.icon_pause)
        if self.tray:
            self.tray_play.setText("Play" if paused else "Pause")

    def _on_stopped(self):
        self._on_paused(True)
        self.save_position()
        if not self.isVisible():
            self.quit_app()

    def _on_ended(self):
        self.player.set_paused(True)
        self.save_position()
        self.toast("Finished the book")
        if not self.isVisible():
            self.quit_app()

    # -- scrolling -----------------------------------------------------------
    def _stop_follow(self):
        if self.book and self.follow:
            self.follow = False
            self.follow_btn.show()
            self.reader_pane.place()

    def _resume_follow(self):
        self.follow = True
        self.follow_btn.hide()
        self.view.highlight(self.pos, True)

    # -- keys ----------------------------------------------------------------
    def eventFilter(self, obj, event):
        # Space and the arrows drive playback wherever focus is, as long as
        # no menu or dropdown is open.
        if event.type() != QEvent.Type.KeyPress or not isinstance(obj, QWidget) \
                or obj.window() is not self or self.book is None \
                or self.stack.currentIndex() != self.READER \
                or QApplication.activePopupWidget() is not None:
            return False
        mods = event.modifiers()
        if mods & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier
                   | Qt.KeyboardModifier.MetaModifier):
            return False
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        key = _code(event.key())
        if key == _code(Qt.Key.Key_Space) and not ctrl:
            if not event.isAutoRepeat():
                self.toggle_play()
        elif key == _code(Qt.Key.Key_Left):
            self.step_chapter(-1) if ctrl else self.step_sentence(-1)
        elif key == _code(Qt.Key.Key_Right):
            self.step_chapter(1) if ctrl else self.step_sentence(1)
        else:
            return False
        return True

    # -- closing -------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.toast_label.isVisible():
            self.toast_label.place()

    def _save_geometry(self):
        self.lib.set_setting("geometry", bytes(self.saveGeometry().toBase64()).decode())
        self.lib.save()

    def closeEvent(self, event):
        self.save_position()
        self._save_geometry()
        if self.player.running and not self.player.is_paused \
                and QSystemTrayIcon.isSystemTrayAvailable():
            # Keep reading in the background from the tray.
            event.ignore()
            self.hide()
            self._show_tray()
            return
        event.accept()
        self.quit_app()

    def _show_tray(self):
        if self.tray is None:
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip(paths.APP_NAME)
            menu = QMenu(self)
            menu.addAction(f"Show {paths.APP_NAME}", self.show_window)
            self.tray_play = menu.addAction("Pause", self.toggle_play)
            menu.addSeparator()
            menu.addAction("Quit", self.quit_app)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._on_tray)
        self._on_paused(self.player.is_paused)
        self.tray.show()
        if not self.tray_hint_shown:
            self.tray_hint_shown = True
            self.tray.showMessage(paths.APP_NAME, "Still reading. Click the tray "
                                  "icon to bring the window back.",
                                  self.windowIcon(), 4000)

    def _on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def show_window(self):
        if self.tray:
            self.tray.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self.save_position()
        self.player.stop()
        if self.tray:
            self.tray.hide()
        self.app.removeEventFilter(self)
        QApplication.quit()
