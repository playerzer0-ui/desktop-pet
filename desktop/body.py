"""Pip on the desktop: her sprite, and how she moves.

Everything moves with squash and stretch, like the units in King God Castle:
    walking   little hops: squashed flat as she lands, stretched tall in the air
    talking   a squish for every few letters she says (call squish())
    standing  breathing and fidgeting that changes with her mood (moves.idle_shape)
    acting    one-off moves for her *actions*: hop, bow, shiver, bonk... (call play(); see moves.py)
    dropped   if you drag her somewhere, she falls back to the floor and lands with a squash
Little emote icons pop up beside her head (call emote()): ♥ ! ? ♪ sweat, anger, zzz, ✦, and … while she thinks.
She wanders along the bottom of the screen on her own, and stops while she's talking or you're typing.
"""
import math, os, random, time
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget
from load import HERE
from desktop import moves

SPRITES = os.path.join(HERE, "character", "pip", "sprites")
SCALE = 2                    # 64px sprites drawn at SCALE times their size, crisp (no smoothing)
SIZE = 64 * SCALE
W, H = SIZE + 80, SIZE + 60  # the window is a little bigger than her, so stretching and hopping never clip
FEET = H - 8                 # where her feet touch the floor, inside the window

WALK_SPEED = 60              # pixels per second
STEP = 0.34                  # seconds per hop
HOP = 10                     # how high each hop goes, in pixels
SQUASH = 0.11                # how much a hop squashes / stretches her
IDLE_SECONDS = (4, 12)       # how long she stands around before wandering again
GRAVITY = 2600               # pixels per second², when she's dropped

EMOTE_SECONDS = 1.8
INK = "#3B3049"

def _glyph(text, color, size=1.0, font="Segoe UI Symbol"):
    def draw(painter, cx, cy, r, now):
        painter.setPen(QColor(color))
        painter.setFont(QFont(font, max(6, int(r * 0.95 * size)), QFont.Bold))
        painter.drawText(QRectF(cx - r, cy - r, 2 * r, 2 * r), Qt.AlignCenter, text)
    return draw

def _sweat(painter, cx, cy, r, now):
    drop = QPainterPath()
    drop.moveTo(cx, cy - r * 0.65)
    drop.cubicTo(cx + r * 0.6, cy + r * 0.1, cx + r * 0.45, cy + r * 0.6, cx, cy + r * 0.6)
    drop.cubicTo(cx - r * 0.45, cy + r * 0.6, cx - r * 0.6, cy + r * 0.1, cx, cy - r * 0.65)
    painter.setPen(QPen(QColor("#2E6FB0"), 1.5))
    painter.setBrush(QColor("#7FC3F0"))
    painter.drawPath(drop)

def _anger(painter, cx, cy, r, now):
    painter.setPen(QPen(QColor("#D23C3C"), max(2.0, r * 0.18), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush)
    g, s = r * 0.18, r * 0.5
    for fx, fy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):  # four little bulging corners
        corner = QPainterPath()
        corner.moveTo(cx + fx * g, cy + fy * s)
        corner.quadTo(cx + fx * g, cy + fy * g, cx + fx * s, cy + fy * g)
        painter.drawPath(corner)

def _think(painter, cx, cy, r, now):
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#8A8296"))
    shown = int(now * 3) % 4  # 0 to 3 dots, over and over
    for i in range(shown):
        painter.drawEllipse(QPointF(cx + (i - 1) * r * 0.55, cy + r * 0.1), r * 0.16, r * 0.16)

def _dizzy(painter, cx, cy, r, now):
    painter.save()
    painter.translate(cx, cy)
    painter.rotate(now * 360 % 360)
    _glyph("✦", "#E8B04B")(painter, 0, 0, r, now)
    painter.restore()

EMOTES = {
    "heart": _glyph("♥", "#E0507A"), "exclaim": _glyph("!", "#E07A1F", font="Segoe UI"),
    "question": _glyph("?", "#7A5BC8", font="Segoe UI"), "note": _glyph("♪", "#C8902E"),
    "zzz": _glyph("z", "#4A7FC8", 0.85, font="Segoe UI"), "sparkle": _glyph("✦", "#E8B04B"),
    "sweat": _sweat, "anger": _anger, "think": _think, "dizzy": _dizzy,
}

class Body(QWidget):
    clicked = Signal()               # left click (without dragging)
    menu_requested = Signal(QPoint)  # right click, at this screen position
    moved = Signal()                 # she moved (the bubble follows her)

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(W, H)
        self.sprites = {name[:-4]: self._load(name) for name in os.listdir(SPRITES) if name.endswith(".png")}
        self.mood = "neutral"
        self.held = False            # True while she's talking or you're typing: no wandering

        floor = self._screen().bottom()
        self.foot_x = float(self._screen().left() + self._screen().width() * random.uniform(0.6, 0.85))
        self.foot_y = float(floor)   # where her feet are, in screen coordinates (not x/y: QWidget has those)
        self.vy = 0.0
        self.mode = "idle"           # idle, walk, drag or fall
        self.facing = 1              # 1 = walking right, -1 = left
        self.target = self.foot_x
        self.phase = 0.0             # walk cycle: each whole number is one hop
        self.idle_until = time.time() + random.uniform(*IDLE_SECONDS)
        self.pulse_at = -10.0        # when the last squish started
        self.pulse_size = 0.0
        self.drag_from = None
        self.move_name, self.move_at = None, 0.0    # the one-off move playing (see moves.PRESETS)
        self.emote_name, self.emote_at = None, 0.0  # the emote icon showing
        self.thinking = False                       # shows a "…" thought icon while the model writes

        self.last = time.time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)
        self._place()

    # --- things the app calls ---

    def set_mood(self, mood):
        if mood in self.sprites:
            self.mood = mood
            self.update()

    def squish(self, size=1.0):
        """A quick squash-and-bounce, like a little jelly wobble (used while she talks)."""
        self.pulse_at, self.pulse_size = time.time(), size

    def play(self, name):
        """Play one of moves.PRESETS (hop, bow, shiver, bonk...)."""
        if name in moves.PRESETS:
            self.move_name, self.move_at = name, time.time()

    def emote(self, name):
        """Pop up an emote icon beside her head: heart, exclaim, question, note, sweat, anger, zzz, sparkle, dizzy."""
        if name:
            self.emote_name, self.emote_at = name, time.time()

    def think(self, on):
        """Show (or stop showing) the "…" thought icon while the model is writing her reply."""
        if on and not self.thinking:
            self.emote_name, self.emote_at = "think", time.time()
        elif not on and self.emote_name == "think":
            self.emote_name = None
        self.thinking = on

    def head(self):
        """The screen point just above her head (where the speech bubble's tail points)."""
        return QPoint(int(self.foot_x), int(self.foot_y - SIZE - 4))

    def hold(self, held):
        self.held = held
        if held and self.mode == "walk":
            self.target = self.foot_x  # finish this hop, then stand still

    # --- movement ---

    def _tick(self):
        now = time.time()
        dt, self.last = min(now - self.last, 0.05), now
        floor = self._screen().bottom()

        if self.mode == "idle" and not self.held and now > self.idle_until:
            left, right = self._screen().left() + SIZE / 2, self._screen().right() - SIZE / 2
            self.target = max(left, min(right, self.foot_x + random.choice([-1, 1]) * random.uniform(120, 420)))
            self.facing = 1 if self.target > self.foot_x else -1
            self.mode, self.phase = "walk", 0.0

        elif self.mode == "walk":
            self.phase += dt / STEP
            if abs(self.target - self.foot_x) > 1:
                self.foot_x += self.facing * min(WALK_SPEED * dt, abs(self.target - self.foot_x))
            elif self.phase % 1 < dt / STEP:  # arrived, and this hop just landed
                self.mode, self.phase = "idle", 0.0
                self.idle_until = now + random.uniform(*IDLE_SECONDS)
                self.squish(0.6)

        elif self.mode == "fall":
            self.vy += GRAVITY * dt
            self.foot_y += self.vy * dt
            if self.foot_y >= floor:
                self.foot_y, self.vy, self.mode = floor, 0.0, "idle"
                self.idle_until = now + random.uniform(*IDLE_SECONDS)
                self.squish(1.3)

        if self.mode in ("idle", "walk"):
            self.foot_y = floor
        self._place()
        self.update()

    def _place(self):
        pos = QPoint(int(self.foot_x - W / 2), int(self.foot_y - FEET))
        if pos != self.pos():
            self.move(pos)
            self.moved.emit()

    def _shape(self):
        """(stretch sideways, stretch upward, tilt in degrees, shift right, shift down) for this moment."""
        sx = sy = 1.0
        rot = dx = dy = 0.0
        if self.mode == "walk":
            t = self.phase % 1                          # 0 = landing, 0.5 = top of the hop
            dy = -HOP * math.sin(math.pi * t)
            c = math.cos(2 * math.pi * t)               # 1 when landing (squash), -1 in the air (stretch)
            sx, sy = 1 + SQUASH * c, 1 - SQUASH * c
        elif self.mode == "drag":
            sx, sy = 0.92, 1.1                          # dangling a little when held
        elif self.mode == "fall":
            sx, sy = 0.9, 1.12
        else:
            sx, sy, rot, dx, dy = moves.idle_shape(self.mood, time.time())

        if self.move_name:                              # a one-off move on top
            seconds, shape = moves.PRESETS[self.move_name]
            progress = (time.time() - self.move_at) / seconds
            if progress >= 1:
                self.move_name = None
            else:
                msx, msy, mrot, mdx, mdy = shape(progress)
                k = SCALE / 3                           # (moves are measured at 3x size)
                sx, sy, rot, dx, dy = sx * msx, sy * msy, rot + mrot, dx + mdx * k, dy + mdy * k

        age = time.time() - self.pulse_at               # a squish: squash, then a small bounce back
        if age < 0.6:
            p = self.pulse_size * math.exp(-6 * age) * math.cos(18 * age)
            sx, sy = sx * (1 + 0.12 * p), sy * (1 - 0.14 * p)
        return sx, sy, rot, dx, dy

    def paintEvent(self, _):
        sx, sy, rot, dx, dy = self._shape()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)  # keep the pixel art crisp
        painter.save()
        painter.translate(W / 2 + dx, FEET + dy)                      # her feet are the anchor point
        painter.rotate(rot)
        painter.scale(sx * (-1 if self.facing < 0 and self.mode == "walk" else 1), sy)
        sprite = self.sprites.get(self.mood) or self.sprites["neutral"]
        painter.drawPixmap(QPointF(-SIZE / 2, -SIZE), sprite)
        painter.restore()
        self._draw_emote(painter, dx, dy)
        painter.end()

    # --- emote icons ---

    def _draw_emote(self, painter, dx, dy):
        now = time.time()
        if self.thinking:
            name, age = "think", now - self.emote_at if self.emote_name == "think" else 1.0
        elif self.emote_name and now - self.emote_at < EMOTE_SECONDS:
            name, age = self.emote_name, now - self.emote_at
        else:
            return
        pop = min(1.0, age / 0.12) * (1 + 0.25 * math.sin(math.pi * min(1.0, age / 0.3)))  # pops in, overshoots
        fade = 1.0 if name == "think" else max(0.0, min(1.0, (EMOTE_SECONDS - age) / 0.4))
        r = 11 * SCALE / 2 * pop                                   # badge radius
        cx = W / 2 + dx + SIZE * 0.34                              # beside her head, on the right
        cy = FEET + dy - SIZE * 0.86 - 6 * min(1.0, age / EMOTE_SECONDS)  # floats up a little
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(fade)
        painter.setPen(QPen(QColor(INK), 2))
        painter.setBrush(QColor("#FFFDF7"))
        painter.drawEllipse(QPointF(cx, cy), r, r)
        draw = EMOTES.get(name)
        if draw:
            draw(painter, cx, cy, r, now)
        painter.setOpacity(1.0)

    # --- the mouse: click to talk, right click for the menu, drag to move her ---

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.menu_requested.emit(e.globalPosition().toPoint())
        elif e.button() == Qt.LeftButton:
            self.drag_from = e.globalPosition()

    def mouseMoveEvent(self, e):
        if self.drag_from is None:
            return
        pos = e.globalPosition()
        if self.mode != "drag" and (pos - self.drag_from).manhattanLength() > 6:
            self.mode = "drag"
        if self.mode == "drag":
            self.foot_x, self.foot_y = pos.x(), pos.y() + SIZE * 0.35  # held by the shoulders, roughly
            self._place()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self.drag_from is None:
            return
        self.drag_from = None
        self.move_name, self.move_at = None, 0.0    # the one-off move playing (see moves.PRESETS)
        self.emote_name, self.emote_at = None, 0.0  # the emote icon showing
        self.thinking = False                       # shows a "…" thought icon while the model writes
        if self.mode == "drag":
            self.mode, self.vy = "fall", 0.0
        else:
            self.clicked.emit()

    # --- helpers ---

    def _load(self, name):
        pixmap = QPixmap(os.path.join(SPRITES, name))
        return pixmap.scaled(pixmap.width() * SCALE, pixmap.height() * SCALE,
                             Qt.IgnoreAspectRatio, Qt.FastTransformation)  # nearest neighbour: crisp pixels

    def _screen(self):
        """The usable area of the screen she's on (above the taskbar)."""
        screen = QGuiApplication.screenAt(QPoint(int(getattr(self, "foot_x", 0)), int(getattr(self, "foot_y", 0)) - 10))
        return (screen or QGuiApplication.primaryScreen()).availableGeometry()
