"""SkyBackground: fresh light-blue animated background for WorkSlop Desktop.

Replaces the old terminal theme entirely. A calm white-blue tech canvas with
many softly-tinted Apple logos drifting in the background. The big centered
brand hero lives on the home page itself; this widget only paints the canvas
and the floating logos behind every page.

Performance notes:
  * Every floater pixmap is pre-rendered once (size + tint + opacity baked in)
    so paintEvent is just blits — no per-frame rasterization.
  * The timer skips work while the widget is hidden.
  * 60 fps via a 16 ms timer plus a real elapsed-time delta (QElapsedTimer),
    so frame pacing does not drift or stutter when the event loop is busy.
  * Logos are seeded across the left / center / right thirds of the width
    so the background never looks empty on one side.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import Qt, QRectF, QTimer, QElapsedTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

# Qt resource path (registered via resources_rc) — safe in frozen builds,
# unlike a filesystem path next to the source tree.
APPLE_SVG = ":/icon/apple.svg"

BASE_BG = "#F2F7FF"

# Soft blue tints for the drifting background logos (light enough to never
# fight with page content drawn above).
FLOAT_TINTS = ["#BFD9FA", "#A9CBF7", "#C9DFFB", "#9DC2F2", "#D4E4FC"]
FLOAT_COUNT = 30

# Target frame budget: 60 fps.
FRAME_INTERVAL_MS = 16


def _tinted_apple(size: int, color_hex: str, opacity: float,
                  dpr: float = 1.0) -> QPixmap:
    """Rasterize apple.svg at *size* px, tinted, with baked-in opacity.

    The SVG is fitted into the square (aspect preserved, centered) — never
    stretched, so the 3:4 Apple logo keeps its true proportions.
    """
    scale = max(1.0, float(dpr))
    px = max(1, int(round(size * scale)))
    pm = QPixmap(px, px)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer = QSvgRenderer(APPLE_SVG)
    vb = renderer.viewBoxF()
    if vb.isValid() and vb.width() > 0 and vb.height() > 0:
        s = min(size / vb.width(), size / vb.height())
        w, h = vb.width() * s, vb.height() * s
        target = QRectF((size - w) / 2.0, (size - h) / 2.0, w, h)
    else:
        target = QRectF(0, 0, size, size)
    renderer.render(painter, target)
    painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_SourceIn)
    col = QColor(color_hex)
    col.setAlphaF(max(0.0, min(1.0, opacity)))
    painter.fillRect(pm.rect(), col)
    painter.end()
    return pm


class _Floater:
    __slots__ = ("rx", "ry", "size", "speed", "phase", "sway", "pixmap")

    def __init__(self, pixmap: QPixmap, rx: float, ry: float,
                 speed: float, phase: float, sway: float):
        self.pixmap = pixmap
        self.rx = rx            # relative x 0..1
        self.ry = ry            # relative y 0..1 (drifts upward, wraps)
        self.size = pixmap.width()
        self.speed = speed      # relative y per second
        self.phase = phase
        self.sway = sway        # horizontal sine amplitude in px


class SkyBackground(QWidget):
    """Animated white-blue background with drifting Apple logos + hero."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._floaters: list[_Floater] = []
        self._t = 0.0
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_INTERVAL_MS)  # ~60 fps
        self._timer.timeout.connect(self._tick)
        self._seed_floaters()

    # ---- public API --------------------------------------------------------

    def start(self):
        if not self._timer.isActive():
            self._clock.start()
            self._timer.start()

    def stop(self):
        self._timer.stop()

    # ---- floaters ----------------------------------------------------------

    def _seed_floaters(self):
        rng = random.Random(20260930)
        dpr = 1.0
        thirds = [(0.02, 0.33), (0.335, 0.665), (0.67, 0.98)]
        for i in range(FLOAT_COUNT):
            size = rng.randint(26, 92)
            tint = rng.choice(FLOAT_TINTS)
            opacity = rng.uniform(0.35, 0.75)
            pm = _tinted_apple(size, tint, opacity, dpr)
            lo, hi = thirds[i % 3]  # spread evenly: left / center / right
            self._floaters.append(_Floater(
                pixmap=pm,
                rx=rng.uniform(lo, hi),
                ry=rng.random(),
                speed=rng.uniform(0.008, 0.028),
                phase=rng.uniform(0, 2 * math.pi),
                sway=rng.uniform(8, 30),
            ))

    def _tick(self):
        if not self.isVisible():
            self._clock.restart()
            return
        # Real elapsed seconds since the last tick — keeps motion smooth
        # even when the event loop delivers ticks late (no fixed-step drift).
        dt = self._clock.restart() / 1000.0
        dt = min(dt, 0.1)  # clamp: a long stall must not teleport logos
        self._t += dt
        for f in self._floaters:
            f.ry -= f.speed * dt
            if f.ry < -0.12:
                f.ry = 1.12
        self.update()

    # ---- paint -------------------------------------------------------------

    def paintEvent(self, event):  # noqa: N802
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BASE_BG))

        # Drifting logos behind everything.
        for f in self._floaters:
            x = f.rx * w + math.sin(self._t * 0.6 + f.phase) * f.sway
            y = f.ry * h + math.cos(self._t * 0.4 + f.phase) * 10
            p.drawPixmap(int(x - f.size / 2), int(y - f.size / 2), f.pixmap)
        p.end()
