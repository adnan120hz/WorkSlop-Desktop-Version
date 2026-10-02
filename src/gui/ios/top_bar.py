"""WorkSlop Desktop modern blue top bar.

Reference layout: a bright-blue header, a white WorkSlop mark in a rounded
square inside the logo block at left, five centered icon-over-label tabs,
and a compact update control at right. Tab ids are category ids; signals
emit the legacy menu ids the shell navigation already understands.
"""
from PySide6.QtCore import Qt, QCoreApplication, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QButtonGroup, QToolButton,
    QSizePolicy,
)

from src.gui.theme import ColorThemeManager, theme_icon

HEADER_HEIGHT = 64
LOGO_BLOCK_WIDTH = 200

# tab_id -> (label, icon resource, emitted legacy menu id)
TABS = [
    ("idevice", "Device", ":/icon/ws-device.svg", "home"),
    ("apps", "Tweaks", ":/icon/ws-apps.svg", "tweaks"),
    ("rtwp", "PosterBoard", ":/icon/ws-wallpaper.svg", "posterboard"),
    ("smartflash", "MobileGestalt", ":/icon/ws-flash.svg", "gestalt"),
    ("toolbox", "Settings", ":/icon/ws-toolbox.svg", "settings"),
]

_TAB_BY_LEGACY = {
    "home": "idevice", "idevice": "idevice",
    "tweaks": "apps", "apps": "apps", "themes": "apps",
    "posterboard": "rtwp", "rtwp": "rtwp", "wallpaper": "rtwp",
    "gestalt": "smartflash", "smartflash": "smartflash",
    "settings": "toolbox", "toolbox": "toolbox",
    "liquidglass": "apps", "springboard": "apps", "internal": "apps",
    "statusbar": "apps", "daemons": "apps", "backup": "idevice",
    "appdata": "idevice",
}

_BLUE = "#0B65D8"
_BLUE_DARK = "#005CB8"
_BLUE_DEEP = "#004A94"
_BLUE_LIGHT = "#2386E8"


class WorkSlopTopBar(QWidget):
    """Bright-blue reference header with centered category tabs."""

    tab_selected = Signal(str)
    menu_selected = Signal(str)
    update_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workslopTopBar")
        self.setFixedHeight(HEADER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(4)

        logo_block = QWidget(self)
        logo_block.setObjectName("topBarLogoBlock")
        logo_block.setFixedWidth(LOGO_BLOCK_WIDTH)
        logo_layout = QHBoxLayout(logo_block)
        logo_layout.setContentsMargins(16, 0, 12, 0)
        logo_layout.setSpacing(11)
        self._logo_mark = QLabel("WS", logo_block)
        self._logo_mark.setAlignment(Qt.AlignCenter)
        self._logo_mark.setFixedSize(38, 38)
        logo_layout.addWidget(self._logo_mark)
        logo_copy = QVBoxLayout()
        logo_copy.setContentsMargins(0, 0, 0, 0)
        logo_copy.setSpacing(1)
        self._logo_name = QLabel("WorkSlop", logo_block)
        self._logo_sub = QLabel("DESKTOP", logo_block)
        logo_copy.addWidget(self._logo_name)
        logo_copy.addWidget(self._logo_sub)
        logo_layout.addLayout(logo_copy)
        logo_layout.addStretch(1)
        layout.addWidget(logo_block)

        layout.addStretch(1)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        self._legacy_by_tab = {}
        for tab_id, label, icon_res, legacy_id in TABS:
            btn = QToolButton(self)
            btn.setObjectName(f"tab_{tab_id}")
            btn.setText(QCoreApplication.translate("Nugget", label))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(HEADER_HEIGHT - 14)
            btn.setMinimumWidth(92)
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _=False, m=legacy_id: self._emit(m))
            btn.toggled.connect(
                lambda checked, b=btn, r=icon_res: self._update_icon(b, r, checked))
            self._group.addButton(btn)
            self._buttons[tab_id] = (btn, icon_res)
            self._legacy_by_tab[tab_id] = legacy_id
            layout.addWidget(btn)
        layout.addStretch(1)

        # Existing-control shortcut: same update checker as the footer.
        self._update_btn = QToolButton(self)
        self._update_btn.setObjectName("topBarUpdateButton")
        self._update_btn.setToolTip(
            QCoreApplication.translate("Nugget", "Check Update"))
        self._update_btn.setFixedSize(38, 38)
        self._update_btn.setCursor(Qt.PointingHandCursor)
        self._update_btn.clicked.connect(self.update_requested.emit)
        layout.addWidget(self._update_btn)

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    # -- public API ---------------------------------------------------------
    def select(self, tab_id: str):
        canonical = _TAB_BY_LEGACY.get(tab_id, tab_id)
        btn = self._buttons.get(canonical)
        if btn is not None:
            btn[0].setChecked(True)

    def set_menu_enabled(self, tab_id: str, enabled: bool):
        canonical = _TAB_BY_LEGACY.get(tab_id, tab_id)
        btn = self._buttons.get(canonical)
        if btn is not None:
            btn[0].setEnabled(enabled)

    def set_gestalt_locked(self, locked: bool, tooltip: str = ""):
        btn, _ = self._buttons["smartflash"]
        btn.setEnabled(not locked)
        if tooltip:
            btn.setToolTip(tooltip)

    # -- internals ------------------------------------------------------------
    def _emit(self, legacy_id: str):
        self.tab_selected.emit(legacy_id)
        self.menu_selected.emit(legacy_id)

    def _update_icon(self, btn: QToolButton, icon_res: str, checked: bool):
        btn.setIcon(theme_icon(icon_res, "#FFFFFF"))

    def _retheme(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"WorkSlopTopBar {{ background-color: {_BLUE}; "
            f"border-bottom: 1px solid {_BLUE_DEEP}; }}")
        logo_block = self.findChild(QWidget, "topBarLogoBlock")
        if logo_block is not None:
            logo_block.setStyleSheet(
                f"background-color: {_BLUE}; "
                "border-right: 1px solid rgba(255, 255, 255, 0.14);")
        self._logo_mark.setStyleSheet(
            "background-color: #FFFFFF; color: #0B65D8; font-size: 15px; "
            "font-weight: 900; border-radius: 10px;")
        self._logo_name.setStyleSheet(
            "color: #FFFFFF; font-size: 19px; font-weight: 900; "
            "letter-spacing: 0.2px; background: transparent;")
        self._logo_sub.setStyleSheet(
            "color: #BFE0FF; font-size: 9px; font-weight: 800; "
            "letter-spacing: 2.4px; background: transparent;")
        for tab_id, (btn, icon_res) in self._buttons.items():
            btn.setIcon(theme_icon(icon_res, "#FFFFFF"))
            btn.setIconSize(QSize(23, 23))
            btn.setStyleSheet(f"""
                QToolButton {{
                    background-color: transparent;
                    border: none;
                    border-radius: 14px;
                    color: #EAF6FF;
                    font-size: 11px;
                    font-weight: 600;
                    padding-top: 4px;
                    padding-bottom: 2px;
                    margin: 5px 2px;
                }}
                QToolButton:hover {{ background-color: rgba(255, 255, 255, 0.13); color: #FFFFFF; }}
                QToolButton:checked {{
                    background-color: {_BLUE_LIGHT};
                    color: #FFFFFF;
                    font-weight: 800;
                }}
                QToolButton:disabled {{ color: rgba(255, 255, 255, 0.45); }}
            """)
        self._update_btn.setIcon(theme_icon(":/icon/ws-refresh.svg", "#FFFFFF"))
        self._update_btn.setIconSize(QSize(19, 19))
        self._update_btn.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.35);
                border-radius: 19px;
            }
            QToolButton:hover { background-color: rgba(255, 255, 255, 0.22); }
        """)
