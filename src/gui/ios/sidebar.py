"""WorkSlop Desktop sidebar: light navigation rail.

Sky theme: solid white rail on the light-blue app body, clean labels with
icons. The active item is a solid Apple-blue pill with white text. No
translucency, no gradients — everything is opaque so text stays crisp.
"""
from PySide6.QtCore import Qt, QCoreApplication, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QButtonGroup, QSizePolicy,
)

from src.gui.theme import ColorThemeManager, theme_icon
from src.version import App_Version

# menu_id -> (label, icon resource)
MENUS = [
    ("home", "Home", ":/icon/house.svg"),
    ("tweaks", "Tweaks", ":/icon/toggles.svg"),
    ("gestalt", "MobileGestalt", ":/icon/iphone-island.svg"),
    ("wallpaper", "Wallpaper", ":/icon/wallpaper.svg"),
    ("backup", "Backup", ":/icon/shippingbox.svg"),
    ("sideload", "Sideload", ":/icon/app-indicator.svg"),
    ("appdata", "App Data", ":/icon/hdd.svg"),
    ("themes", "Themes", ":/icon/brush.svg"),
    ("settings", "Settings", ":/icon/gear.svg"),
]

PILL_HEIGHT = 46
SIDEBAR_WIDTH = 216


class WorkSlopSidebar(QWidget):
    """Left navigation rail for the Sky shell."""

    menu_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workslopSidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(6)

        # Wordmark.
        self._brand = QLabel("WORKSLOP", self)
        self._brand.setObjectName("sidebarBrand")
        self._brand.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._brand)
        self._brand_sub = QLabel("desktop", self)
        self._brand_sub.setObjectName("sidebarBrandSub")
        layout.addWidget(self._brand_sub)
        layout.addSpacing(10)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        for menu_id, label, icon_res in MENUS:
            btn = QPushButton(QCoreApplication.translate('Nugget', label), self)
            btn.setObjectName(f"menu_{menu_id}")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(PILL_HEIGHT)
            btn.clicked.connect(lambda _=False, m=menu_id: self.menu_selected.emit(m))
            btn.toggled.connect(
                lambda checked, b=btn, r=icon_res: self._update_icon(b, r, checked))
            self._group.addButton(btn)
            self._buttons[menu_id] = (btn, icon_res)
            layout.addWidget(btn)

        layout.addStretch(1)

        self._version_lbl = QLabel(f"WorkSlop Desktop v{App_Version}", self)
        self._version_lbl.setAlignment(Qt.AlignCenter)
        self._version_lbl.setObjectName("sidebarVersion")
        layout.addWidget(self._version_lbl)

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    # -- public API -----------------------------------------------------
    def select(self, menu_id: str):
        btn = self._buttons.get(menu_id)
        if btn is not None:
            btn[0].setChecked(True)

    def set_menu_enabled(self, menu_id: str, enabled: bool):
        btn = self._buttons.get(menu_id)
        if btn is not None:
            btn[0].setEnabled(enabled)

    def set_gestalt_locked(self, locked: bool, tooltip: str = ""):
        """Lock the MobileGestalt entry on unsupported iOS (stays visible)."""
        btn, _ = self._buttons["gestalt"]
        btn.setEnabled(not locked)
        if tooltip:
            btn.setToolTip(tooltip)

    def _update_icon(self, btn: QPushButton, icon_res: str, checked: bool):
        c = ColorThemeManager.instance().colors
        color = c.menu_active_text if checked else c.menu_text
        btn.setIcon(theme_icon(icon_res, color))

    # -- theming --------------------------------------------------------
    def _retheme(self):
        c = ColorThemeManager.instance().colors
        # White rail on the light-blue body: the menu_* palette entries are
        # dark-on-white, so the rail must be menu_bg (white).
        rail_bg = c.menu_bg
        self.setStyleSheet(
            f"WorkSlopSidebar {{ background-color: {rail_bg}; "
            f"border-right: 1px solid {c.divider}; }}")
        # Ensure the stylesheet background actually paints on this custom QWidget.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._brand.setStyleSheet(
            f"color: {c.accent}; font-size: 20px; font-weight: 800; "
            f"letter-spacing: 3px; background: transparent;")
        self._brand_sub.setStyleSheet(
            f"color: {c.menu_dim}; font-size: 12px; background: transparent;")
        for menu_id, (btn, icon_res) in self._buttons.items():
            btn.setIcon(theme_icon(icon_res, c.menu_text))
            btn.setIconSize(QSize(18, 18))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    border-radius: 14px;
                    color: {c.menu_text};
                    font-size: 14px;
                    font-weight: 600;
                    text-align: left;
                    padding-left: 16px;
                }}
                QPushButton:hover {{
                    background-color: {c.surface_hover};
                }}
                QPushButton:checked {{
                    background-color: {c.menu_active_bg};
                    color: {c.menu_active_text};
                    font-weight: 700;
                }}
                QPushButton:disabled {{
                    color: {c.menu_dim};
                }}
            """)
            # Keep the icon readable on the inverted (blue) active pill.
            btn.setProperty("iconColor", c.menu_text)
        self._version_lbl.setStyleSheet(
            f"color: {c.menu_dim}; font-size: 11px; background: transparent;")
