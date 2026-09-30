"""WorkSlop Desktop sidebar: 7 glass pill menus + version label (Cobalt Flow).

Matches the WorkSlop Desktop mockup: translucent rounded pills, icon + label,
blue gradient on the active item, and the app version pinned at the bottom.
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
    ("themes", "Themes", ":/icon/brush.svg"),
    ("settings", "Settings", ":/icon/gear.svg"),
]

PILL_HEIGHT = 48


class WorkSlopSidebar(QWidget):
    """Left navigation rail for the Cobalt Flow shell."""

    menu_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workslopSidebar")
        self.setFixedWidth(208)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(8)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        for menu_id, label, icon_res in MENUS:
            btn = QPushButton(QCoreApplication.translate("Nugget", label), self)
            btn.setObjectName(f"menu_{menu_id}")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(PILL_HEIGHT)
            btn.clicked.connect(lambda _=False, m=menu_id: self.menu_selected.emit(m))
            self._group.addButton(btn)
            self._buttons[menu_id] = (btn, icon_res)
            layout.addWidget(btn)

        layout.addStretch(1)

        self._version_lbl = QLabel(f"v{App_Version} \u2022 Cobalt Flow", self)
        self._version_lbl.setAlignment(Qt.AlignCenter)
        self._version_lbl.setObjectName("sidebarVersion")
        layout.addWidget(self._version_lbl)

        self._gestalt_lock_msg = ""
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
        """Lock the MobileGestalt pill on unsupported iOS (stays visible)."""
        btn, _ = self._buttons["gestalt"]
        btn.setEnabled(not locked)
        if tooltip:
            btn.setToolTip(tooltip)

    # -- theming --------------------------------------------------------
    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self.setStyleSheet("background-color: transparent;")
        for menu_id, (btn, icon_res) in self._buttons.items():
            btn.setIcon(theme_icon(icon_res, c.text_primary))
            btn.setIconSize(QSize(20, 20))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(255, 255, 255, 0.07);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                    border-radius: {PILL_HEIGHT // 2}px;
                    color: {c.text_primary};
                    font-size: 13px;
                    font-weight: 500;
                    text-align: left;
                    padding-left: 18px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.13);
                }}
                QPushButton:checked {{
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #4a90e2, stop:1 #2f6fd0);
                    border: 1px solid rgba(255, 255, 255, 0.25);
                    color: #ffffff;
                    font-weight: 600;
                }}
                QPushButton:disabled {{
                    background-color: rgba(255, 255, 255, 0.03);
                    color: {c.text_secondary};
                }}
            """)
        self._version_lbl.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 11px; background: transparent;")
