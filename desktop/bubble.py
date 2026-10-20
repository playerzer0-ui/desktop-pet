"""Pip's speech bubble (her words appear as she writes them) and the little box you type into."""
import html, re
from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

CREAM, INK, GOLD, ROSE, GRAY = "#FFF8EC", "#3B3049", "#C8902E", "#B76E79", "#8A8296"
WIDTH = 300
TAIL = 12  # height of the bubble's little tail

def words_html(text):
    """Pip's words with *actions* in soft rose italics."""
    parts = re.split(r"(\*[^*]+\*?)", text)
    return "".join(f'<i style="color:{ROSE}">{html.escape(p.strip("*"))}</i>' if i % 2 else html.escape(p)
                   for i, p in enumerate(parts))

class Bubble(QWidget):
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
        layout.setContentsMargins(14, 10, 14, 10 + TAIL)
        layout.addWidget(self.label)
        layout.addWidget(self.note)
        self.text = ""
        self.anchor = QPoint()
        self.hide_timer = QTimer(self, singleShot=True, timeout=self.hide)

    def say(self, text, note="", stay=None):
        """Show a whole message at once. stay = seconds before it hides (None = until replaced)."""
        self.text = text
        self._show(words_html(text), note)
        self._hide_later(stay)

    def start(self):
        """She's about to speak: an empty bubble with a little '...' until the words come."""
        self.text = ""
        self.hide_timer.stop()
        self._show(f'<span style="color:{GRAY}">…</span>', "")

    def add(self, piece):
        self.text += piece
        self._show(words_html(self.text), self.note.text())

    def finish(self, note=""):
        """She's done: keep the bubble up long enough to read, then hide it."""
        self._show(words_html(self.text), note)
        self._hide_later(4 + len(self.text) / 14)

    def follow(self, anchor):
        """Keep the tail pointing at this screen point (just above her head)."""
        self.anchor = anchor
        self.move(anchor.x() - self.width() // 2, anchor.y() - self.height())

    def _show(self, words, note):
        self.label.setText(words)
        self.note.setText(note)
        self.note.setVisible(bool(note))
        self.adjustSize()
        self.follow(self.anchor)
        self.show()
        self.update()

    def _hide_later(self, seconds):
        self.hide_timer.stop()
        if seconds:
            self.hide_timer.start(int(seconds * 1000))

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(1, 1, self.width() - 2, self.height() - TAIL - 2)
        path = QPainterPath()
        path.addRoundedRect(box, 12, 12)
        tail = QPainterPath()
        mid = self.width() / 2
        tail.moveTo(mid - 9, box.bottom() - 1)
        tail.lineTo(mid, self.height() - 1)
        tail.lineTo(mid + 9, box.bottom() - 1)
        path = path.united(tail)
        painter.setPen(QPen(QColor(GOLD), 2))
        painter.setBrush(QColor(CREAM))
        painter.drawPath(path)
        painter.end()

class InputBox(QWidget):
    """A small box above Pip for typing to her. Enter sends, Esc closes."""
    submitted = Signal(str)
    closed = Signal()

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(WIDTH)
        self.line = QLineEdit(placeholderText="Talk to Pip…  (Enter to send, Esc to close)")
        self.line.setFont(QFont("Segoe UI", 10))
        self.line.setStyleSheet(f"QLineEdit {{ background: {CREAM}; color: {INK}; border: 2px solid {GOLD};"
                                f" border-radius: 10px; padding: 6px 10px; }}")
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
        """Sit just above her head (the bubble then goes above this box)."""
        self.move(anchor.x() - self.width() // 2, anchor.y() - self.height())

    def _send(self):
        text = self.line.text().strip()
        self.line.clear()
        if text:
            self.submitted.emit(text)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
            self.closed.emit()
        else:
            super().keyPressEvent(e)
