"""Pip on the desktop: her sprite, and how she moves.

Everything moves with squash and stretch, like the units in King God Castle:
    walking   little hops: squashed flat as she lands, stretched tall in the air
    talking   a squish for every bit of speech that arrives (call squish())
    standing  a slow breathing bob
    dropped   if you drag her somewhere, she falls back to the floor and lands with a squash
She wanders along the bottom of the screen on her own, and stops while she's talking or you're typing.
"""
import math, os, random, time
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QWidget
from load import HERE

SPRITES = os.path.join(HERE, "character", "pip", "sprites")
SCALE = 2                    # 64px sprites drawn at 192px, crisp (no smoothing)
SIZE = 64 * SCALE
W, H = SIZE + 80, SIZE + 60  # the window is a little bigger than her, so stretching and hopping never clip
FEET = H - 8                 # where her feet touch the floor, inside the window

WALK_SPEED = 60              # pixels per second
STEP = 0.34                  # seconds per hop
HOP = 10                     # how high each hop goes, in pixels
SQUASH = 0.11                # how much a hop squashes / stretches her
IDLE_SECONDS = (4, 12)       # how long she stands around before wandering again
GRAVITY = 2600               # pixels per second², when she's dropped

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
        """(stretch sideways, stretch upward, lift off the floor) for this moment."""
        sx = sy = 1.0
        lift = 0.0
        if self.mode == "walk":
            t = self.phase % 1                          # 0 = landing, 0.5 = top of the hop
            lift = HOP * math.sin(math.pi * t)
            c = math.cos(2 * math.pi * t)               # 1 when landing (squash), -1 in the air (stretch)
            sx, sy = 1 + SQUASH * c, 1 - SQUASH * c
        elif self.mode == "drag":
            sx, sy = 0.92, 1.1                          # dangling a little when held
        elif self.mode == "fall":
            sx, sy = 0.9, 1.12
        else:
            b = math.sin(2 * math.pi * time.time() / 2.6)  # breathing
            sx, sy = 1 - 0.015 * b, 1 + 0.015 * b

        age = time.time() - self.pulse_at               # a squish: squash, then a small bounce back
        if age < 0.6:
            p = self.pulse_size * math.exp(-6 * age) * math.cos(18 * age)
            sx, sy = sx * (1 + 0.12 * p), sy * (1 - 0.14 * p)
        return sx, sy, lift

    def paintEvent(self, _):
        sx, sy, lift = self._shape()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)  # keep the pixel art crisp
        painter.translate(W / 2, FEET - lift)                         # her feet are the anchor point
        painter.scale(sx * (-1 if self.facing < 0 and self.mode == "walk" else 1), sy)
        sprite = self.sprites.get(self.mood) or self.sprites["neutral"]
        painter.drawPixmap(QPointF(-SIZE / 2, -SIZE), sprite)
        painter.end()

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
