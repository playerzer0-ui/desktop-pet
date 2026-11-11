"""The Status card, drawn as a little picture for the speech bubble:

    Trust ■■■□□□□□□□          trust level, out of 10
    exp   ━━━━━──────         progress to the next level (✻ while her major quest holds it back)
    [talk] 5/10   [clock] 139/240 min
    context ━━━━──┆── 34%     how full her context is; the tick is where she starts forgetting
"""
import os
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap
from engine.config import HERE, FORGET_AT
from desktop.bubble import CREAM, GRAY, GOLD, INK, ROSE

ART = os.path.join(HERE, "character")
WIDTH, HEIGHT = 206, 82  # the bubble's width, inside its margins
LEFT = 50                # where the bars start, after their labels
TRACK = "#EADFCB"        # the empty part of a bar

def card(summary):
    """The Status picture for trust.summary(...)."""
    ratio = QGuiApplication.primaryScreen().devicePixelRatio()  # real pixels: crisp text
    picture = QPixmap(int(WIDTH * ratio), int(HEIGHT * ratio))
    picture.setDevicePixelRatio(ratio)
    picture.fill(Qt.transparent)
    p = QPainter(picture)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    p.setPen(QColor(INK))                                   # Trust ■■■□□□□□□□
    p.setFont(QFont("Segoe UI", 11))
    p.drawText(QRectF(0, 0, LEFT, 22), Qt.AlignLeft | Qt.AlignVCenter, "Trust")
    box, gap = 12, (WIDTH - LEFT - 2 - 10 * 12) / 9
    for i in range(10):
        filled = i < summary["trust"]
        p.setPen(QPen(QColor(INK if filled else GRAY), 1.5))
        p.setBrush(QColor(ROSE if filled else CREAM))
        p.drawRoundedRect(QRectF(LEFT + 1 + i * (box + gap), 4, box, 14), 2, 2)

    p.setPen(QColor(GRAY))                                  # exp ━━━━━──────
    p.setFont(QFont("Segoe UI", 8))
    p.drawText(QRectF(0, 24, LEFT, 14), Qt.AlignLeft | Qt.AlignVCenter, "exp")
    gated = summary.get("gated")
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
    _stat(p, "clock.png", 100, clock_text(summary))  # 100: room for "240/240 min"

    p.setPen(QColor(GRAY))                                  # context ━━━━──┆── 34%
    p.setFont(QFont("Segoe UI", 8))
    p.drawText(QRectF(0, 66, LEFT, 14), Qt.AlignLeft | Qt.AlignVCenter, "context")
    full = context_full(summary)
    p.setPen(QColor(INK))
    p.drawText(QRectF(WIDTH - 32, 66, 32, 14), Qt.AlignRight | Qt.AlignVCenter,
               "…" if full is None else f"{full:.0%}")
    bar = QRectF(LEFT, 70, WIDTH - LEFT - 36, 6)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(TRACK))
    p.drawRoundedRect(bar, 3, 3)
    if full:
        p.setBrush(QColor(ROSE if full >= FORGET_AT else GRAY))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(bar.height(), bar.width() * min(1.0, full)),
                                 bar.height()), 3, 3)
    p.setPen(QPen(QColor(INK), 1))  # where she starts forgetting
    tick = bar.left() + bar.width() * FORGET_AT
    p.drawLine(QPointF(tick, bar.top() - 2), QPointF(tick, bar.bottom() + 2))
    p.end()
    return picture

def clock_text(summary):
    """"139/240 min", or "139 min" with no daily limit."""
    limit = summary.get("daily_minutes")
    return f"{summary['minutes_today']:.0f}/{limit} min" if limit else f"{summary['minutes_today']:.0f} min"

def context_full(summary):
    """How full her context is (0-1), or None before it's known."""
    used, size = summary.get("context") or (0, 0)
    return used / size if used and size else None

def _stat(p, icon, x, text):
    p.setRenderHint(QPainter.SmoothPixmapTransform, False)  # keep pixel-art icons crisp
    p.drawPixmap(QPointF(x, 44), QPixmap(os.path.join(ART, icon)))
    p.setPen(QColor(INK))
    p.drawText(QRectF(x + 22, 42, 90, 20), Qt.AlignLeft | Qt.AlignVCenter, text)
