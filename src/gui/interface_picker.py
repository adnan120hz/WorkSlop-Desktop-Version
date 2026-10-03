from PySide6.QtCore import Qt, QCoreApplication, QRectF
from PySide6.QtGui import QPixmap, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QFrame
)

import os

from src.gui.theme import ColorThemeManager

_ICON_DIR = os.path.join(os.path.dirname(__file__), "..", "qt", "icon")


def _render_svg(path: str, width: int, height: int) -> QPixmap:
    """Render an SVG file into a monochrome-friendly QPixmap (no QtSvg widget needed)."""
    renderer = QSvgRenderer(path)
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    return QPixmap.fromImage(image)


class InterfacePickerDialog(QDialog):
    """First-launch dialog: pick WorkSlop (Main), WorkSlop 2, or Nugget UI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(QCoreApplication.translate("Nugget", "Choose Interface"))
        self.setFixedWidth(420)
        self.choice = None  # "ios" | "classic" | "full_nugget"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(QCoreApplication.translate("Nugget", "Welcome to WorkSlop Desktop"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._subtitle = QLabel(QCoreApplication.translate(
            "Nugget", "Choose your interface style"))
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._subtitle)

        layout.addSpacing(8)

        self._frames = []
        self._descs = []
        for art, name, desc, choice in (
            ("ui_ios.svg", "WorkSlop (Main)",
             "The WorkSlop v4 interface (main UI)", "ios"),
            ("ui_classic.svg", "WorkSlop 2",
             "Classic desktop sidebar layout with WorkSlop icons", "classic"),
            ("ui_classic.svg", "Nugget",
             "The original Nugget interface — only the app name and icon are WorkSlop",
             "full_nugget"),
        ):
            frame = QFrame()
            frame_lay = QVBoxLayout(frame)
            frame_lay.setContentsMargins(16, 12, 16, 12)
            art_lbl = QLabel()
            art_lbl.setPixmap(_render_svg(
                os.path.join(_ICON_DIR, art), 340, 160))
            art_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            art_lbl.setStyleSheet("border: none; background: transparent;")
            frame_lay.addWidget(art_lbl)
            title_lbl = QLabel(QCoreApplication.translate("Nugget", name))
            title_lbl.setStyleSheet("font-size: 16px; font-weight: 600; border: none;")
            desc_lbl = QLabel(QCoreApplication.translate("Nugget", desc))
            desc_lbl.setWordWrap(True)
            frame_lay.addWidget(title_lbl)
            frame_lay.addWidget(desc_lbl)
            frame.setCursor(Qt.CursorShape.PointingHandCursor)
            frame.mousePressEvent = lambda e, ch=choice: self._pick(ch)
            layout.addWidget(frame)
            self._frames.append(frame)
            self._descs.append(desc_lbl)

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c.bg_elevated}; }}
            QLabel {{ color: {c.text_primary}; background: transparent; }}
        """)
        self._subtitle.setStyleSheet(f"color: {c.text_secondary}; font-size: 14px;")
        for frame in self._frames:
            frame.setStyleSheet(f"""
                QFrame {{ background-color: {c.surface_hover}; border-radius: 12px; }}
                QFrame:hover {{ background-color: {c.border}; }}
            """)
        for desc in self._descs:
            desc.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px; border: none;")

    def _pick(self, choice: str):
        self.choice = choice
        self.accept()
