"""WorkSlop Desktop sidebar: deep-ink command rail.

The Wave 10 shell uses a dark graphite rail with grouped navigation, a
mint brand mark, and a solid accent selection state. It is a desktop-tool
rail, not a floating mobile menu: dense, labeled, and always visible.
"""
from PySide6.QtCore import Qt, QCoreApplication, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QButtonGroup,
    QSizePolicy,
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
    ("appdata", "App Data", ":/icon/hdd.svg"),
    ("themes", "Themes", ":/icon/brush.svg"),
    ("settings", "Settings", ":/icon/gear.svg"),
]

PILL_HEIGHT = 44
SIDEBAR_WIDTH = 248

_MENU_GROUPS = [
    ("WORKSPACE", ("home", "tweaks")),
    ("DEVICE TOOLS", ("gestalt", "wallpaper", "backup", "appdata", "themes")),
    ("SYSTEM", ("settings",)),
]


class WorkSlopSidebar(QWidget):
    """Left command rail for the Wave 10 WorkSlop shell."""

    menu_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workslopSidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(7)

        # Brand lockup: compact WS mark + product wordmark. The rail is the
        # permanent identity surface, so it carries the version footer too.
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(11)
        self._brand_mark = QLabel("WS", self)
        self._brand_mark.setObjectName("sidebarBrandMark")
        self._brand_mark.setAlignment(Qt.AlignCenter)
        self._brand_mark.setFixedSize(42, 42)
        brand_row.addWidget(self._brand_mark)
        brand_copy = QVBoxLayout()
        brand_copy.setContentsMargins(0, 0, 0, 0)
        brand_copy.setSpacing(0)
        self._brand = QLabel("WORKSLOP", self)
        self._brand.setObjectName("sidebarBrand")
        self._brand.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        brand_copy.addWidget(self._brand)
        self._brand_sub = QLabel("DESKTOP", self)
        self._brand_sub.setObjectName("sidebarBrandSub")
        brand_copy.addWidget(self._brand_sub)
        brand_row.addLayout(brand_copy)
        brand_row.addStretch(1)
        layout.addLayout(brand_row)
        layout.addSpacing(12)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        self._group_labels = []
        menu_by_id = {menu_id: (label, icon_res)
                      for menu_id, label, icon_res in MENUS}
        for group_title, menu_ids in _MENU_GROUPS:
            group_lbl = QLabel(group_title, self)
            group_lbl.setObjectName("sidebarGroupLabel")
            self._group_labels.append(group_lbl)
            layout.addWidget(group_lbl)
            for menu_id in menu_ids:
                label, icon_res = menu_by_id[menu_id]
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
            layout.addSpacing(7)

        layout.addStretch(1)

        self._version_lbl = QLabel(f"WorkSlop Desktop  v{App_Version}", self)
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
        color = c.menu_active_text if checked else c.brand_dim
        btn.setIcon(theme_icon(icon_res, color))

    # -- theming --------------------------------------------------------
    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self.setStyleSheet(
            f"WorkSlopSidebar {{ background-color: {c.menu_bg}; "
            f"border-right: 1px solid #1D2A3D; }}")
        # Ensure the stylesheet background actually paints on this custom QWidget.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._brand_mark.setStyleSheet(
            f"background-color: {c.brand}; color: #05251F; "
            "font-size: 13px; font-weight: 900; letter-spacing: 0.5px; "
            "border-radius: 11px;")
        self._brand.setStyleSheet(
            f"color: #FFFFFF; font-size: 17px; font-weight: 900; "
            f"letter-spacing: 2.4px; background: transparent;")
        self._brand_sub.setStyleSheet(
            f"color: {c.brand_dim}; font-size: 9px; font-weight: 800; "
            "letter-spacing: 3.2px; background: transparent;")
        for group_lbl in self._group_labels:
            group_lbl.setStyleSheet(
                f"color: {c.menu_dim}; font-size: 9px; font-weight: 800; "
                "letter-spacing: 1.8px; padding: 7px 2px 2px 2px; "
                "background: transparent;")
        for menu_id, (btn, icon_res) in self._buttons.items():
            checked = btn.isChecked()
            btn.setIcon(theme_icon(
                icon_res, c.menu_active_text if checked else c.brand_dim))
            btn.setIconSize(QSize(19, 19))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-left: 3px solid transparent;
                    border-radius: 10px;
                    color: {c.menu_text};
                    font-size: 13.5px;
                    font-weight: 650;
                    text-align: left;
                    padding-left: 13px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.07);
                    border-color: rgba(255, 255, 255, 0.10);
                    color: #FFFFFF;
                }}
                QPushButton:checked {{
                    background-color: {c.menu_active_bg};
                    border-color: {c.accent_pressed};
                    border-left: 3px solid {c.brand};
                    color: {c.menu_active_text};
                    font-weight: 800;
                }}
                QPushButton:disabled {{
                    color: {c.menu_dim};
                }}
            """)
            btn.setProperty("iconColor", c.menu_text)
        self._version_lbl.setStyleSheet(
            f"color: {c.menu_dim}; font-size: 10.5px; font-weight: 600; "
            f"background-color: rgba(255,255,255,0.05); "
            f"border: 1px solid rgba(255,255,255,0.09); border-radius: 9px; "
            "padding: 9px 6px;")
