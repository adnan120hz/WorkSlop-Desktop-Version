"""Animated blue Apple-logo background for the Wave 10 shell.

Rebuilt from the archived v4 SkyBackground concept: pre-rendered Apple
logos drift slowly upward behind the page stack. The logos are tinted in
WorkSlop blue and kept subtle so white content surfaces stay readable.
Paint work is only pixmap blits; the timer does nothing while hidden.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap, QLinearGradient
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

APPLE_SVG = ":/icon/apple.svg"
FLOAT_COUNT = 16
FLOAT_TINTS = ["#0B65D8", "#2386E8", "#2E8FE0", "#0053A8", "#0E74DE"]


def _tinted_apple(size: int, color_hex: str, opacity: float,
                  dpr: float = 1.0) -> QPixmap:
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

    def __init__(self, pixmap, rx, ry, speed, phase, sway):
        self.pixmap = pixmap
        self.rx = rx
        self.ry = ry
        self.size = pixmap.width()
        self.speed = speed
        self.phase = phase
        self.sway = sway


class SkyBackground(QWidget):
    """Blue Apple logos floating behind the shell content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workslopSkyBackground")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self._floaters: list[_Floater] = []
        self._t = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self._seed_floaters()
        self.start()

    def start(self):
        if not self._timer.isActive():
            self._timer.start()

    def stop(self):
        self._timer.stop()

    def is_animating(self) -> bool:
        return self._timer.isActive()

    def floater_positions(self):
        return [(f.rx, f.ry) for f in self._floaters]

    def _seed_floaters(self):
        rng = random.Random(20261002)
        for _ in range(FLOAT_COUNT):
            size = rng.randint(28, 104)
            pm = _tinted_apple(
                size, rng.choice(FLOAT_TINTS), rng.uniform(0.17, 0.32), 1.0)
            self._floaters.append(_Floater(
                pixmap=pm,
                rx=rng.random(),
                ry=rng.random(),
                speed=rng.uniform(0.006, 0.020),
                phase=rng.uniform(0, 2 * math.pi),
                sway=rng.uniform(6, 24),
            ))

    def _tick(self):
        if not self.isVisible():
            return
        self._t += 0.040
        for f in self._floaters:
            f.ry -= f.speed * 0.040
            if f.ry < -0.14:
                f.ry = 1.14
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt override
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        p = QPainter(self)
        gradient = QLinearGradient(0, 0, w, h)
        gradient.setColorAt(0.0, QColor("#F2F9FF"))
        gradient.setColorAt(0.55, QColor("#E2F0FE"))
        gradient.setColorAt(1.0, QColor("#D3E9FD"))
        p.fillRect(self.rect(), gradient)
        for f in self._floaters:
            x = f.rx * w + math.sin(self._t * 0.55 + f.phase) * f.sway
            y = f.ry * h + math.cos(self._t * 0.38 + f.phase) * 8
            p.drawPixmap(int(x - f.size / 2), int(y - f.size / 2), f.pixmap)
        p.end()
