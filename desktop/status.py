"""The Status card, drawn as a little picture for the speech bubble:

    Trust ■■■□□□□□□□      one box per trust level (out of 10)
    exp   ━━━━━──────      how far she is from this trust level to the next (with a ✻ while her major quest
                                                                          holds trust back)
    [talk] 5/10   [clock] 139/240 min    talks today (out of the daily cap), and minutes together today
                                         (out of her daily limit, if she has one: visits.py)

The icons are talk.png and clock.png (16 px) in character/, next to portal.png.
"""
import os
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap
from config import HERE
from desktop.bubble import CREAM, GRAY, GOLD, INK, ROSE

ART = os.path.join(HERE, "character")
WIDTH, HEIGHT = 206, 64  # (the bubble's width, inside its margins)
LEFT = 50                # where the boxes and the exp bar start, after "Trust" / "exp"
TRACK = "#EADFCB"        # the empty part of the exp bar

def card(summary):
    """The Status picture for trust.summary(...)."""
    ratio = QGuiApplication.primaryScreen().devicePixelRatio()  # drawn at the screen's real pixels: crisp text
    picture = QPixmap(int(WIDTH * ratio), int(HEIGHT * ratio))
    picture.setDevicePixelRatio(ratio)
    picture.fill(Qt.transparent)
    p = QPainter(picture)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    p.setPen(QColor(INK))                                   # Trust ■■■□□□□□□□
    p.setFont(QFont("Segoe UI", 11))
    p.drawText(QRectF(0, 0, LEFT, 22), Qt.AlignLeft | Qt.AlignVCenter, "Trust")
    box, gap = 12, (WIDTH - LEFT - 2 - 10 * 12) / 9  # (2: room for the last box's outline)
    for i in range(10):
        filled = i < summary["trust"]
        p.setPen(QPen(QColor(INK if filled else GRAY), 1.5))
        p.setBrush(QColor(ROSE if filled else CREAM))
        p.drawRoundedRect(QRectF(LEFT + 1 + i * (box + gap), 4, box, 14), 2, 2)

    p.setPen(QColor(GRAY))                                  # exp ━━━━━──────
    p.setFont(QFont("Segoe UI", 8))
    p.drawText(QRectF(0, 24, LEFT, 14), Qt.AlignLeft | Qt.AlignVCenter, "exp")
    gated = summary.get("gated")  # trust is held back by her major quest: a ✻ at the end of the bar
    bar = QRectF(LEFT, 28, WIDTH - LEFT - 1 - (16 if gated else 0), 6)
    if gated:
        p.setPen(QColor(GOLD))
        p.setFont(QFont("Segoe UI Symbol", 10, QFont.Bold))
        p.drawText(QRectF(WIDTH - 14, 22, 14, 18), Qt.AlignCenter, "✻")
        p.setPen(Qt.NoPen)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(TRACK))
    p.drawRoundedRect(bar, 3, 3)
    done = max(0.0, min(1.0, summary["progress"]))
    if done > 0:
        p.setBrush(QColor(GOLD))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(bar.height(), bar.width() * done), bar.height()), 3, 3)

    p.setFont(QFont("Segoe UI", 10))                        # [talk] 5/10   [clock] 139 min
    _stat(p, "talk.png", 0, f"{summary['talk_today']}/{summary['talk_cap']}")
    _stat(p, "clock.png", 100, clock_text(summary))  # (100: room for "240/240 min", 72 px in Segoe UI 10, inside 206)
    p.end()
    return picture

def clock_text(summary):
    """Minutes together today, out of her daily time if she has a limit (visits.py): "139/240 min" or "139 min"."""
    limit = summary.get("daily_minutes")
    return f"{summary['minutes_today']:.0f}/{limit} min" if limit else f"{summary['minutes_today']:.0f} min"

def _stat(p, icon, x, text):
    p.setRenderHint(QPainter.SmoothPixmapTransform, False)  # keep the pixel-art icons crisp
    p.drawPixmap(QPointF(x, 44), QPixmap(os.path.join(ART, icon)))
    p.setPen(QColor(INK))
    p.drawText(QRectF(x + 22, 42, 90, 20), Qt.AlignLeft | Qt.AlignVCenter, text)
