from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QColorDialog

from src.gui.theme.theme_manager import ColorThemeManager


class AccentPicker(QWidget):
    """Single circle showing the active accent color.

    Clicking it opens a color dialog so the user can pick any color;
    the choice is saved through ``ColorThemeManager.set_accent_hex``,
    which uses the same ``accent_color`` QSettings key as the presets.
    """

    accent_changed = Signal(str)

    _SIZE = 52

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tm = ColorThemeManager.instance()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._btn = QPushButton(self)
        self._btn.setFixedSize(self._SIZE, self._SIZE)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setToolTip("Choose accent color")
        self._btn.clicked.connect(self._on_click)
        layout.addWidget(self._btn)
        layout.addStretch(1)

        self._paint()
        self._tm.theme_changed.connect(self._paint)

    def _on_click(self):
        initial = QColor(self._tm.accent_hex())
        color = QColorDialog.getColor(initial, self, "Choose accent color")
        if not color.isValid():
            return
        self._tm.set_accent_hex(color.name())
        self.accent_changed.emit(color.name())

    def _paint(self):
        accent = self._tm.accent_hex()
        radius = self._SIZE // 2
        ring = self._tm.c("text_primary")
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                border-radius: {radius}px;
                border: 3px solid {ring};
            }}
            QPushButton:hover {{
                background-color: {accent};
                border: 3px solid {ring};
            }}
        """)
