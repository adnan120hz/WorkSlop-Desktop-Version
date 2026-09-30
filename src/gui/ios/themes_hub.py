"""WorkSlop Desktop Themes hub: Icon Themes + Passcode Themes in one menu.

The two theme pages already exist (ios pages 10 and 11); this hub only gives
the single "Themes" sidebar entry somewhere to land.
"""
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
)

from src.gui.ios.components import IOSCard, IOSPrimaryButton, IOSSectionHeader
from src.gui.theme import t, ColorThemeManager


def tr(text: str) -> str:
    return QCoreApplication.translate("Nugget", text)


class IOSThemesHubPage(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")
        self._tm = ColorThemeManager.instance()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self._scroll = scroll
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 24)
        content_layout.setSpacing(12)

        content_layout.addWidget(IOSSectionHeader(tr("Themes")))

        content_layout.addWidget(self._make_card(
            tr("Icon Themes"),
            tr("Replace app icons with a custom icon pack."),
            tr("Open Icon Themes"),
            lambda: window.show_ios_page(10)))

        content_layout.addWidget(self._make_card(
            tr("Passcode Themes"),
            tr("Customize the passcode keypad buttons."),
            tr("Open Passcode Themes"),
            lambda: window.show_ios_page(11)))

        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._retheme()
        self._tm.theme_changed.connect(self._retheme)

    def _make_card(self, title, desc, btn_text, handler):
        card = IOSCard()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        title_lbl = QLabel(tr(title))
        title_lbl.setStyleSheet(
            "font-size: 15px; font-weight: 600; background-color: transparent;")
        lay.addWidget(title_lbl)
        desc_lbl = QLabel(tr(desc))
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(t("value_label") + " background-color: transparent;")
        lay.addWidget(desc_lbl)
        row = QHBoxLayout()
        row.addStretch(1)
        btn = IOSPrimaryButton(tr(btn_text))
        btn.clicked.connect(handler)
        row.addWidget(btn)
        lay.addLayout(row)
        return card

    def refresh(self):
        pass

    def _retheme(self):
        c = self._tm.colors
        self._scroll.setStyleSheet(
            f"background-color: {c.bg_primary}; border: none;")
