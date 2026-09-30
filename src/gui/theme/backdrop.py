"""Cobalt Flow bubble backdrop.

A lightweight, static backdrop painted behind the main window content: soft
translucent circles ("bubbles") over the cobalt gradient. Positions are
derived from a seeded RNG keyed on the widget size, so they are stable and
never flicker; there is no animation timer and no per-frame cost — it only
repaints on resize or retheme.

The widget is transparent to mouse events and is meant to be installed as a
child of the central widget and lowered below every other child.
"""

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

import random

_BUBBLE_COUNT = 16


class CobaltBackdrop(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # No focus, no tab stop — purely decorative.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._bubble_color = QColor("rgba(140, 175, 255, 26)")
        self._highlight_color = QColor("rgba(180, 205, 255, 40)")
        if parent is not None:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())
            self.lower()

    # -- public -----------------------------------------------------------

    def set_colors(self, bubble: str, highlight: str) -> None:
        self._bubble_color = QColor(bubble)
        self._highlight_color = QColor(highlight)
        self.update()

    # -- internals --------------------------------------------------------

    def eventFilter(self, obj, event):  # noqa: N802 (Qt naming)
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parent().rect())
            self.lower()
        return super().eventFilter(obj, event)

    def _bubbles(self):
        """Deterministic bubble layout for the current size."""
        w, h = max(1, self.width()), max(1, self.height())
        rng = random.Random((w // 8) * 100003 + (h // 8))
        for _ in range(_BUBBLE_COUNT):
            r = rng.uniform(14, 90)
            x = rng.uniform(-r, w + r)
            y = rng.uniform(-r, h + r)
            yield x, y, r

    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for x, y, r in self._bubbles():
            painter.setPen(QPen(self._highlight_color, max(1.0, r * 0.03)))
            painter.setBrush(self._bubble_color)
            painter.drawEllipse(int(x - r), int(y - r), int(r * 2), int(r * 2))
        painter.end()
