"""WorkSlop Desktop left white sidebar.

Modern reference layout: the connected device name sits in a dropdown at
the top, then a clean icon menu maps to the existing WorkSlop pages. The
sidebar is presentation/navigation only; device switching reuses the
window's existing ``change_selected_device`` path.
"""
from PySide6.QtCore import Qt, QCoreApplication, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QButtonGroup, QSizePolicy, QScrollArea,
)

from src.gui.theme import ColorThemeManager, t, theme_icon

PANEL_WIDTH = 200

# menu id -> (label, icon resource)
NAV_ITEMS = [
    ("home", "Info", ":/icon/phone.svg"),
    ("tweaks", "Tweaks", ":/icon/toggles.svg"),
    ("liquidglass", "Liquid Glass", ":/icon/liquid-glass.svg"),
    ("springboard", "SpringBoard", ":/icon/app-indicator.svg"),
    ("internal", "Internal", ":/icon/hdd.svg"),
    ("statusbar", "Status Bar", ":/icon/wifi.svg"),
    ("posterboard", "PosterBoard", ":/icon/wallpaper.svg"),
    ("daemons", "Daemons", ":/icon/gear.svg"),
    ("gestalt", "MobileGestalt", ":/icon/iphone-island.svg"),
    ("settings", "Settings", ":/icon/gear.svg"),
]


class WorkSlopDevicePanel(QWidget):
    """White left sidebar: device dropdown header + page menu."""

    menu_selected = Signal(str)

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("workslopDevicePanel")
        self.setFixedWidth(PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 12)
        layout.setSpacing(6)

        # First row is the selected device name itself (dropdown), like the
        # reference — no "CONNECTED DEVICE" header, no boxed combo look.
        self._device_header = QLabel(
            QCoreApplication.translate("Nugget", "CONNECTED DEVICE"), self)
        self._device_header.hide()
        self.device_combo = QComboBox(self)
        self.device_combo.setObjectName("sidebarDeviceCombo")
        self.device_combo.setFixedHeight(36)
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        layout.addWidget(self.device_combo)

        # Kept for compatibility with refresh call sites; not displayed —
        # the device iOS/connection lives on the Home info table.
        self._connection_lbl = QLabel("—", self)
        self._connection_lbl.hide()

        nav_scroll = QScrollArea(self)
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        nav_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }")
        nav_host = QWidget(nav_scroll)
        nav_host.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 4, 0, 0)
        nav_layout.setSpacing(3)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        for menu_id, label, icon_res in NAV_ITEMS:
            btn = QPushButton(QCoreApplication.translate("Nugget", label), nav_host)
            btn.setObjectName(f"side_{menu_id}")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(36)
            btn.setIconSize(QSize(17, 17))
            btn.clicked.connect(lambda _=False, m=menu_id: self.menu_selected.emit(m))
            btn.toggled.connect(lambda _c, m=menu_id: self._tint_nav_icon(m))
            self._group.addButton(btn)
            self._buttons[menu_id] = (btn, icon_res)
            nav_layout.addWidget(btn)
        nav_layout.addStretch(1)
        nav_scroll.setWidget(nav_host)
        layout.addWidget(nav_scroll, 1)

        self._hint = QLabel(
            QCoreApplication.translate(
                "Nugget", "Select a device, then choose a tool."),
            self)
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(t("device_row_meta"))
        layout.addWidget(self._hint)

        # Compatibility aliases for older refresh/gating call sites.
        self._rows = []
        self._empty_lbl = self._connection_lbl

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)
        self.refresh_devices()
        self.select("home")

    # -- data -----------------------------------------------------------------
    def refresh_devices(self):
        """Refresh the device dropdown from the device manager."""
        devices = []
        current_index = 0
        try:
            devices = list(self.window.device_manager.devices or [])
            current_index = int(
                getattr(self.window.device_manager, "current_device_index", 0) or 0)
        except Exception:
            devices = []
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        if devices:
            for device in devices:
                self.device_combo.addItem(getattr(device, "name", "") or "iPhone")
            if 0 <= current_index < len(devices):
                self.device_combo.setCurrentIndex(current_index)
            device = devices[self.device_combo.currentIndex()]
            tag = "USB" if getattr(device, "connected_via_usb", False) else "Wi-Fi"
            version = getattr(device, "version", "") or "—"
            build = getattr(device, "build", "") or "—"
            self._connection_lbl.setText(f"iOS {version} ({build})  •  {tag}")
            self._hint.setText(
                QCoreApplication.translate(
                    "Nugget", "Select a device, then choose a tool."))
        else:
            self.device_combo.addItem(
                QCoreApplication.translate("Nugget", "No device connected"))
            self._connection_lbl.setText(
                QCoreApplication.translate(
                    "Nugget", "Connect an iPhone via USB."))
            # Honest no-device guidance (Windows especially): detection
            # goes through the Apple Mobile Device service via usbmux, and
            # an empty list with no error usually means the driver/service
            # is missing or the iPhone has not trusted this computer yet.
            # Say so instead of sitting silently on "No device".
            self._hint.setText(
                QCoreApplication.translate(
                    "Nugget",
                    "No device detected. Check the USB cable, unlock the "
                    "iPhone and tap Trust, and on Windows make sure the "
                    "Apple Mobile Device driver is installed (Apple Devices "
                    "app from the Microsoft Store, or iTunes from Apple)."))
        self.device_combo.blockSignals(False)
        self._rows = []

    # -- public API --------------------------------------------------------------
    def select(self, menu_id: str):
        btn = self._buttons.get(menu_id)
        if btn is not None:
            btn[0].setChecked(True)

    def set_menu_enabled(self, menu_id: str, enabled: bool):
        btn = self._buttons.get(menu_id)
        if btn is not None:
            btn[0].setEnabled(enabled)

    def set_gestalt_locked(self, locked: bool, tooltip: str = ""):
        btn, _ = self._buttons["gestalt"]
        btn.setEnabled(not locked)
        if tooltip:
            btn.setToolTip(tooltip)

    # -- actions ------------------------------------------------------------------
    def _on_device_changed(self, index: int):
        try:
            devices = list(self.window.device_manager.devices or [])
        except Exception:
            devices = []
        if devices and 0 <= index < len(devices):
            try:
                self.window.change_selected_device(index)
            except Exception:
                pass
        self.refresh_devices()

    # -- theming --------------------------------------------------------------------
    def _tint_nav_icon(self, menu_id: str):
        """Thin outline icons: muted blue-grey when idle, brand blue on the
        active pill — one consistent 17px outline set, like the reference."""
        entry = self._buttons.get(menu_id)
        if entry is None:
            return
        btn, icon_res = entry
        color = "#0B65D8" if btn.isChecked() else "#64798F"
        btn.setIcon(theme_icon(icon_res, color))

    def _retheme(self):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(t("device_side_panel"))
        self._device_header.setStyleSheet(t("sidebar_device_header"))
        self._connection_lbl.setStyleSheet(t("device_row_meta"))
        self._hint.setStyleSheet(t("device_row_meta"))
        self.device_combo.setStyleSheet(t("sidebar_device_combo"))
        for menu_id, (btn, icon_res) in self._buttons.items():
            btn.setStyleSheet(t("sidebar_nav_button"))
            self._tint_nav_icon(menu_id)
