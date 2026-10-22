"""Pip's speech bubble and the little box you type into.

The bubble talks like a game's dialogue box: one sentence (a "page") at a time, typed out letter by letter,
with a ▼ when there's more to come. Each page stays up long enough to read, then the next one comes.
Click the bubble to skip ahead (finish the typing, or go to the next page).
Her reply streams in from the model faster than you can read, so pages are queued and shown at reading pace.
Her *actions* aren't shown: each one is reported (the acted signal) as its page comes up, and she acts it out.
"""
import html, re
from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget
from sentences import first_end

CREAM, INK, GOLD, ROSE, GRAY = "#FFF8EC", "#3B3049", "#C8902E", "#B76E79", "#8A8296"
WIDTH = 230
TAIL = 10                # height of the bubble's little tail
TAIL_INSET = 18          # the tail never gets closer than this to the bubble's side (its rounded corner)
EDGE = 4                 # gap kept between the bubble (or input box) and the screen edge
LETTERS_PER_SECOND = 32
PAGE_MAX = 95            # a sentence longer than this is split into more pages (at a comma, or a space)
ACTION = re.compile(r"\*([^*]+)\*?")  # *an action*, or one still being written at the very end

def on_screen(anchor, x, y, width):
    """(x, y) moved so a box this wide, with its top-left at x, y, stays on the screen she's on."""
    screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
    area = screen.availableGeometry()
    x = max(area.left() + EDGE, min(x, area.right() + 1 - EDGE - width))
    return x, max(area.top() + EDGE, y)

def read_time(page):
    """How long a page stays up once it's fully typed, in seconds."""
    return 0.9 + len(page) / 22

def words_html(text):
    """Pip's words with *actions* in soft rose italics (an action still being typed counts too)."""
    parts = re.split(r"(\*[^*]+\*?)", text)
    return "".join(f'<i style="color:{ROSE}">{html.escape(p.strip("*"))}</i>' if i % 2 else html.escape(p)
                   for i, p in enumerate(parts))

def without_actions(text):
    """Her words with the *actions* taken out (they're animated instead)."""
    return re.sub(r"\s{2,}", " ", ACTION.sub("", text)).strip()

def readable(text):
    """How many letters of this you'd actually read (the *actions* aren't shown)."""
    return len(without_actions(text))

def cut_long(text):
    """Split a too-long sentence so the readable part is at most PAGE_MAX letters: after a comma if there's
    one far enough in, else at the last space that fits. Never cuts inside an *action*."""
    space = comma = None
    for gap in re.finditer(r"[,;]?\s", text):
        at = gap.start() + (1 if gap.group()[0] in ",;" else 0)
        head = text[:at]
        if head.count("*") % 2:
            continue  # inside an action
        if readable(head) > PAGE_MAX:
            break
        space = at
        if gap.group()[0] in ",;" and readable(head) > PAGE_MAX // 2:
            comma = at
    at = comma or space
    return (text[:at].strip(), text[at:].lstrip()) if at else (text[:PAGE_MAX], text[PAGE_MAX:])

class Bubble(QWidget):
    typed = Signal()     # a few more letters appeared (she's "talking": the app squishes her)
    acted = Signal(str)  # she does an *action* now (the text between the asterisks): the app animates it
    done = Signal()      # her whole reply has been shown and had time to be read

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # never steals focus from what you're doing
        self.setFixedWidth(WIDTH)
        self.label = QLabel(textFormat=Qt.RichText, wordWrap=True)
        self.label.setFont(QFont("Segoe UI", 10))
        self.label.setStyleSheet(f"color: {INK}; background: transparent;")
        self.note = QLabel(textFormat=Qt.RichText, wordWrap=True)
        self.note.setFont(QFont("Segoe UI", 8))
        self.note.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8 + TAIL)
        layout.setSpacing(2)
        self.picture = QLabel()  # a picture instead of words (the Status card): its own label, as a picture in the
        self.picture.hide()      # word-wrapping one gets no height at all (wrapping only measures text)
        layout.addWidget(self.label)
        layout.addWidget(self.picture)
        layout.addWidget(self.note)
        self.anchor = QPoint()
        self.tail_x = WIDTH // 2  # where the tail sits along the bottom (moves when the bubble meets a screen edge)

        self.active = False     # a dialogue is playing (from start() until done)
        self.streaming = False   # her reply is still arriving from the model
        self.incoming = ""       # streamed text not yet cut into pages
        self.pages = []          # pages waiting to be shown
        self.page = ""           # the page on screen
        self.shown = 0           # how many of its letters are typed out
        self.final_note = ""     # small print under the last page (quest, trust...)
        self.cancelled = False   # say() cut the dialogue short: the rest of her reply is dropped until start()
        self.typer = QTimer(self, interval=int(1000 / LETTERS_PER_SECOND), timeout=self._type)
        self.reader = QTimer(self, singleShot=True, timeout=self._next)  # waits while you read a page
        self.hider = QTimer(self, singleShot=True, timeout=self._close)

    # --- a dialogue: start(), add() as her reply streams in, finish() when it's complete ---

    def start(self):
        self.active, self.streaming, self.cancelled = True, True, False
        self.incoming, self.pages, self.page, self.shown, self.final_note = "", [], "", 0, ""
        for timer in (self.typer, self.reader, self.hider):
            timer.stop()
        self.hide()  # (nothing to read yet: she shows a "…" thought icon instead)

    def add(self, piece):
        if self.cancelled:
            return
        self.incoming += piece
        self._cut_pages(final=False)
        self._continue()

    def finish(self, note=""):
        if self.cancelled:
            return
        self.streaming, self.final_note = False, note
        self._cut_pages(final=True)
        self._continue()

    # --- a plain message (status, menus...): shown at once ---

    def say(self, text, note="", stay=None):
        """Show a whole message at once. stay = seconds before it hides (None = until replaced).
        If her reply is still playing, it's cut short: what's left of it won't type over this message."""
        if self.active:
            self.cancelled = True
            self.streaming, self.incoming, self.pages, self.page = False, "", [], ""
        self.active = False
        for timer in (self.typer, self.reader, self.hider):
            timer.stop()
        for action in ACTION.findall(text):
            self.acted.emit(action.strip())
        self._render(words_html(without_actions(text)), note)
        if stay:
            self.hider.start(int(stay * 1000))

    def show_picture(self, picture, stay=None):
        """Show a picture (like the Status card, see status.py) instead of words, the way say() shows a message."""
        self.say("", stay=stay)
        self.picture.setPixmap(picture)  # (the next say() or page hides it and shows words again)
        self.picture.show()
        self._fit()

    def follow(self, anchor):
        """Keep the tail pointing at this screen point (just above her head). Near a screen edge the bubble
        slides back onto the screen and its tail moves along it, so it still points at her."""
        self.anchor = anchor
        x, y = on_screen(anchor, anchor.x() - self.width() // 2, anchor.y() - self.height(), self.width())
        self.tail_x = max(TAIL_INSET, min(self.width() - TAIL_INSET, anchor.x() - x))
        self.move(x, y)
        self.update()

    # --- paging ---

    def _cut_pages(self, final):
        while True:
            end = first_end(self.incoming, final)  # (not after "Mr." or "St.", see sentences.py)
            if end and readable(self.incoming[:end]) <= PAGE_MAX + 20:
                page, self.incoming = self.incoming[:end].strip(), self.incoming[end:]
            elif readable(self.incoming) > PAGE_MAX + 20 or (final and readable(self.incoming) > PAGE_MAX):
                page, self.incoming = cut_long(self.incoming)
            elif final and self.incoming.strip():
                page, self.incoming = self.incoming.strip(), ""
            else:
                return
            if page:
                self.pages.append(page)

    def _continue(self):
        """Start typing the next page if the bubble is free (nothing typing, nothing waiting to be read)."""
        if self.typer.isActive() or self.reader.isActive():
            return
        if self.page and self.shown < len(self.page):
            return
        if self.pages:
            self._open_page(self.pages.pop(0))
        elif self.page and not self.streaming:
            self._last_page()

    def _open_page(self, page):
        """Start a new page: act out its *actions*, then type out its words (if it has any)."""
        for action in ACTION.findall(page):
            self.acted.emit(action.strip())
        self.page, self.shown = without_actions(page), 0
        if self.page:
            self.typer.start()
            self._draw_page()
        else:  # only an action: give the animation a moment before the next page
            self.page = " "
            self.shown = 1
            self.reader.start(900)

    def _type(self):
        self.shown += 1
        while self.shown < len(self.page) and self.page[self.shown - 1] == " ":
            self.shown += 1  # don't spend a tick on spaces
        if self.shown % 3 == 0:
            self.typed.emit()
        if self.shown >= len(self.page):
            self.shown = len(self.page)
            self.typer.stop()
            self.reader.start(int(read_time(self.page) * 1000))
        self._draw_page()

    def _next(self):
        """Done reading this page: on to the next (or wait for more of her reply)."""
        if self.pages:
            self._open_page(self.pages.pop(0))
        elif not self.streaming:
            self._last_page()
        else:
            self._draw_page()  # she's still writing: keep this page up, with the ▼

    def _last_page(self):
        self._draw_page()
        self.hider.start(int((1.5 + read_time(self.page)) * 1000))

    def _close(self):
        self.hide()
        if self.active:
            self.active = False
            self.done.emit()

    def _draw_page(self):
        if not self.page.strip():
            return  # an action-only page: nothing to read
        typing_done = self.shown >= len(self.page)
        more = typing_done and (self.pages or self.streaming)
        words = words_html(self.page[:self.shown])
        if more:
            words += f' <span style="color:{GOLD}">▼</span>'
        last = typing_done and not self.pages and not self.streaming
        self._render(words, self.final_note if last else "")

    def mousePressEvent(self, e):
        """Click to skip: finish typing this page, or go straight to the next one."""
        if not self.active:
            self.hide()
        elif self.typer.isActive():
            self.shown = len(self.page) - 1
            self._type()
        elif self.reader.isActive():
            self.reader.stop()
            self._next()
        elif self.hider.isActive():
            self.hider.stop()
            self._close()

    # --- drawing ---

    def _render(self, words, note):
        self.label.setText(words)
        self.label.setVisible(bool(words))
        self.picture.hide()
        self.note.setText(note)
        self.note.setVisible(bool(note))
        self._fit()
        self.show()
        self.update()

    def _fit(self):
        """Take exactly the height the wrapped text needs at this width, then sit above her head.
        (Not adjustSize(): it ignores how wrapping makes text taller, so the window grew later, downward,
        over her head.)"""
        layout = self.layout()
        layout.activate()
        height = layout.totalHeightForWidth(self.width())  # (-1 when nothing showing wraps, like the Status card...)
        self.setFixedHeight(height if height > 0 else layout.totalSizeHint().height())  # (...then its own size)
        self.follow(self.anchor)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(1, 1, self.width() - 2, self.height() - TAIL - 2)
        path = QPainterPath()
        path.addRoundedRect(box, 10, 10)
        tail = QPainterPath()
        mid = self.tail_x
        tail.moveTo(mid - 8, box.bottom() - 1)
        tail.lineTo(mid, self.height() - 1)
        tail.lineTo(mid + 8, box.bottom() - 1)
        path = path.united(tail)
        painter.setPen(QPen(QColor(GOLD), 2))
        painter.setBrush(QColor(CREAM))
        painter.drawPath(path)
        painter.end()

class InputBox(QWidget):
    """A small box above the character for typing to them. Enter sends, Esc closes."""
    submitted = Signal(str)
    closed = Signal()

    def __init__(self, name):  # name = who you're talking to, for the placeholder text
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(260)
        self.line = QLineEdit(placeholderText=f"Talk to {name}…  (Enter to send, Esc to close)")
        self.line.setFont(QFont("Segoe UI", 10))
        self.line.setStyleSheet(f"QLineEdit {{ background: {CREAM}; color: {INK}; border: 2px solid {GOLD};"
                                f" border-radius: 10px; padding: 5px 9px; }}")
        self.line.returnPressed.connect(self._send)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.line)
        self.adjustSize()

    def open_at(self, anchor):
        self.follow(anchor)
        self.show()
        self.raise_()
        self.activateWindow()
        self.line.setFocus()

    def follow(self, anchor):
        """Sit just above her head (the bubble then goes above this box), kept on the screen."""
        self.move(*on_screen(anchor, anchor.x() - self.width() // 2, anchor.y() - self.height(), self.width()))

    def _send(self):
        text = self.line.text().strip()
        self.line.clear()
        if text:
            self.hide()  # sent: the box goes away (click her again to say more)
            self.submitted.emit(text)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
            self.closed.emit()
        else:
            super().keyPressEvent(e)
