"""WorkSlop Desktop Themes hub: Icon Themes + Passcode Themes in one menu.

The two theme pages already exist (ios pages 10 and 11); this hub only gives
the single "Themes" sidebar entry somewhere to land.
"""
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
)

from src.gui.ios.components import (
    IOSCard, IOSPrimaryButton, IOSSectionHeader, apply_full_nugget_chrome)
from src.gui.theme import t, ColorThemeManager
from src.gui.theme.colors import NUGGET_DARK
from src.gui.theme.styles import STYLES, FONT_FAMILY


def tr(text: str) -> str:
    return QCoreApplication.translate("Nugget", text)


def _qss(style_key: str, colors) -> str:
    """Render a global stylesheet template against an explicit palette."""
    payload = dict(colors.__dict__)
    payload["font_family"] = FONT_FAMILY
    return STYLES[style_key].format_map(payload)


def _nugget_primary_qss(c) -> str:
    """Primary-button recipe for the Full Nugget palette (the global
    template keys its background off text_primary, which is white in
    the Nugget palette — upstream Nugget primaries are accent blue)."""
    return (
        f"QPushButton {{ background-color: {c.accent}; border: none;"
        " border-radius: 14px; color: #FFFFFF; font-size: 15px;"
        " font-weight: 700; padding: 12px 20px; }"
        f"QPushButton:hover {{ background-color: {c.accent_hover}; color: #FFFFFF; }}"
        f"QPushButton:pressed {{ background-color: {c.accent_pressed}; color: #FFFFFF; }}"
        f"QPushButton:disabled {{ background-color: {c.bg_tertiary};"
        f" color: {c.text_disabled}; }}")


class IOSThemesHubPage(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")
        self._tm = ColorThemeManager.instance()
        self._full_nugget = False
        self._fn_styled = []   # (widget, qss_fn) palette-baked labels
        self._fn_buttons = []  # IOSPrimaryButton instances to repalette

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

        content_layout.addWidget(self._make_card(
            tr("iOS 18 Icons"),
            tr("Stock iOS 18 app icons (Light and Dark) ready to add "
               "to Icon Themes."),
            tr("Open iOS 18 Icons"),
            lambda: window.show_ios_page(17)))

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

        def title_qss(c):
            return (f"color: {c.text_primary}; font-size: 15px;"
                    " font-weight: 600; background-color: transparent;")

        def desc_qss(c):
            return (f"color: {c.text_secondary}; font-size: 14px;"
                    " background-color: transparent;")
        title_lbl = QLabel(tr(title))
        title_lbl.setStyleSheet(title_qss(self._palette()))
        self._fn_styled.append((title_lbl, title_qss))
        lay.addWidget(title_lbl)
        desc_lbl = QLabel(tr(desc))
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(desc_qss(self._palette()))
        self._fn_styled.append((desc_lbl, desc_qss))
        lay.addWidget(desc_lbl)
        row = QHBoxLayout()
        row.addStretch(1)
        btn = IOSPrimaryButton(tr(btn_text))
        btn.clicked.connect(handler)
        self._fn_buttons.append(btn)
        row.addWidget(btn)
        lay.addLayout(row)
        return card

    def refresh(self):
        pass

    # ---------- Full Nugget palette (third interface) ----------

    def _palette(self):
        """Active colors: upstream Nugget dark in the Full Nugget
        interface, the themed WorkSlop palette everywhere else."""
        if getattr(self, "_full_nugget", False):
            return NUGGET_DARK
        return self._tm.colors

    def set_full_nugget(self, enabled: bool):
        """Full Nugget (third interface) restyle: this page takes the
        Nugget-original dark palette like the other hosted pages
        (Daemons / Posterboard / Settings); the other interfaces keep
        the themed look untouched. Widgets and behavior are identical
        — colors only."""
        self._full_nugget = bool(enabled)
        self._retheme()

    def _retheme(self):
        c = self._palette()
        self._scroll.setStyleSheet(
            f"background-color: {c.bg_primary}; border: none;")
        for widget, qss_fn in self._fn_styled:
            try:
                widget.setStyleSheet(qss_fn(c))
            except Exception:
                pass
        for btn in self._fn_buttons:
            try:
                btn.setStyleSheet(
                    _nugget_primary_qss(c) if self._full_nugget
                    else _qss("primary_button", c))
            except Exception:
                pass
        apply_full_nugget_chrome(self, self._full_nugget)
