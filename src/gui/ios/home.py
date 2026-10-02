"""WorkSlop Desktop Home: reference-layout device page.

Modeled 1:1 on the classic desktop device-tool layout the user picked:
a realistic phone (frame + real home screen, cutout matched to the
detected device) center-left, a dense two-column device-info table to
its right, storage bars under the table, and a row of colorful rounded
action tiles along the bottom. All values come from the existing
DeviceManager getters — unknown data shows "—", nothing is invented.
The registry-derived tweak catalogue lives below the tiles.
"""
from PySide6.QtCore import Qt, QCoreApplication, Slot, QTimer, QSize
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QSizePolicy, QScrollArea, QProgressBar, QFrame,
    QGraphicsDropShadowEffect,
)

from src.gui.ios.components import IOSCard, IOSDangerButton
from src.gui.preset_widget import PresetWidget
from src.gui.theme import t, ColorThemeManager, theme_icon, theme_pixmap
from src.tweaks.capabilities import is_audit_user_retained
from src.tweaks.registry import Section, home_tweak_catalogue

# Action tile: (title, subtitle, page_index, tile color, icon resource).
# Navigation targets are the existing ios_pages indices. "Refresh" is a
# pseudo-page handled separately (page_index None -> refresh handler).
_ACTION_TILES = [
    ("Refresh", "Scan devices", None, "#0B65D8", ":/icon/ws-refresh.svg"),
    ("Backup / Restore", "Open backup tools", 13, "#0E74DE", ":/icon/ws-backup.svg"),
    ("Tweaks", "Customize system settings", 1, "#0959B4", ":/icon/ws-sliders.svg"),
    ("Liquid Glass", "Disable the glass look", 9, "#2386E8", ":/icon/ws-glass.svg"),
    ("Status Bar", "Customize the status bar", 5, "#0B65D8", ":/icon/ws-signal.svg"),
    ("PosterBoard", "Animated wallpapers", 2, "#0E74DE", ":/icon/ws-poster.svg"),
    ("Daemons", "Disable system daemons", 3, "#0959B4", ":/icon/ws-gear.svg"),
    ("MobileGestalt", "Device feature flags", 12, "#2386E8", ":/icon/ws-chip.svg"),
    ("Reset Tweaks", "Remove applied tweaks", -1, "#0959B4", ":/icon/ws-trash.svg"),
]


def _make_glossy_apple(size: int, dpr: float = 1.0) -> QPixmap:
    """White Apple logo with a glossy finish for the deep-blue brand panel.

    The base pictogram is rendered white, then a soft top-light gradient
    and a radial highlight are composited over it (clipped to the logo's
    alpha) so it reads as polished/glossy rather than flat. Honest limit:
    this is a 2D gloss treatment of the monochrome logo, not a 3D render.
    """
    base = theme_pixmap(":/icon/apple.svg", "#FFFFFF", size, dpr)
    if base.isNull():
        return base
    out = QPixmap(base.size())
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.drawPixmap(0, 0, base)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    grad = QLinearGradient(0, 0, 0, out.height())
    grad.setColorAt(0.0, QColor(255, 255, 255, 255))
    grad.setColorAt(0.45, QColor(235, 244, 255, 235))
    grad.setColorAt(1.0, QColor(190, 216, 245, 225))
    painter.fillRect(out.rect(), grad)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    highlight = QRadialGradient(out.width() * 0.38, out.height() * 0.16,
                                out.width() * 0.55)
    highlight.setColorAt(0.0, QColor(255, 255, 255, 120))
    highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(out.rect(), highlight)
    painter.end()
    return out


def _soft_shadow(widget):
    """Very soft card shadow like the reference's floating white cards."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(14)
    effect.setOffset(0, 2)
    effect.setColor(QColor(31, 78, 121, 22))
    widget.setGraphicsEffect(effect)
    return widget


class _CatalogueCard(IOSCard):
    """Registry catalogue surface below the action tiles."""

    def _retheme(self):
        self.setStyleSheet(t("catalogue_card"))


class _ActionTile(QWidget):
    """Colorful rounded-square action tile with a label underneath."""

    def __init__(self, title, subtitle, color, icon_res, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(QCoreApplication.translate("Nugget", subtitle))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(5)
        self._chip = QLabel(self)
        self._chip.setFixedSize(58, 58)
        self._chip.setAlignment(Qt.AlignCenter)
        self._chip_color = color
        self._icon_res = icon_res
        layout.addWidget(self._chip, 0, Qt.AlignHCenter)
        self._label = QLabel(QCoreApplication.translate("Nugget", title), self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(t("action_tile_label"))
        layout.addWidget(self._label)
        self._paint()

    def _paint(self):
        self._chip.setStyleSheet(
            f"background-color: {self._chip_color}; border-radius: 16px;")
        try:
            dpr = self.devicePixelRatioF()
        except Exception:
            dpr = 1.0
        self._chip.setPixmap(theme_pixmap(self._icon_res, "#FFFFFF", 28, dpr))

    def _retheme(self):
        self._label.setStyleSheet(t("action_tile_label"))
        self._paint()


class _TileRow(QWidget):
    """Horizontal action-tile row (stands in for the old card grid)."""

    def __init__(self, tiles, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(14)
        for tile in tiles:
            self._layout.addWidget(tile)
        self._layout.addStretch(1)

    def reflow(self):
        self.updateGeometry()


class IOSHomePage(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")
        self._c = ColorThemeManager.instance().colors
        # locked tiles (e.g. MobileGestalt on unsupported iOS): clicking
        # shows why instead of opening the page
        self._tile_locks = {}
        self._tiles = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self._scroll = scroll
        content = QWidget()
        self._scroll_content = content
        scroll.setWidget(content)
        outer.addWidget(scroll)

        content.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(14)

        # (The old top-left device-name chip row was removed 2026-10-03 by
        # user order — a leftover of the pre-rebuild Home header. The
        # device name lives in the sidebar and the title card below.)

        # Compatibility controls: the sidebar owns device selection now, but
        # existing Home refresh paths still use this combo/buttons.
        self._title = QLabel("WorkSlop Desktop", self)
        self._title.hide()
        self.device_combo = QComboBox(self)
        self.device_combo.setFixedHeight(34)
        self.device_combo.setMinimumWidth(200)
        self._style_device_combo()
        self.populate_device_picker()
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        self.device_combo.hide()
        self._refresh_btn = QPushButton(self)
        self._refresh_btn.setFixedSize(34, 34)
        self._refresh_btn.setIconSize(QSize(16, 16))
        self._refresh_btn.setStyleSheet(t("home_icon_button"))
        self._apply_icon(self._refresh_btn, ":/icon/arrow-clockwise.svg")
        self._refresh_btn.clicked.connect(self.refresh_devices)
        self._refresh_btn.hide()
        self._settings_btn = QPushButton(self)
        self._settings_btn.setFixedSize(34, 34)
        self._settings_btn.setIconSize(QSize(16, 16))
        self._settings_btn.setStyleSheet(t("home_icon_button"))
        self._apply_icon(self._settings_btn, ":/icon/gear.svg")
        self._settings_btn.clicked.connect(self.open_settings)
        self._settings_btn.hide()

        # ---- Main row: phone visual + info table -----------------------------
        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(22)

        # Brand visual (user revision 2026-10-03): glossy WHITE Apple logo
        # on a deep-blue rounded panel, in every state (connected or not).
        # The panel is the brand block; the logo gets a subtle highlight
        # gradient plus a soft drop shadow so it reads glossy, not flat.
        phone_col = QVBoxLayout()
        phone_col.setContentsMargins(0, 0, 0, 0)
        phone_col.setSpacing(6)
        self._brand_panel = QFrame(self)
        self._brand_panel.setObjectName("brandLogoPanel")
        self._brand_panel.setFixedSize(240, 300)
        self._brand_panel.setStyleSheet(
            "QFrame#brandLogoPanel { background: qlineargradient("
            "x1:0, y1:0, x2:0, y2:1, stop:0 #1273E6, stop:1 #064A9E); "
            "border: 1px solid #0A5BC4; border-radius: 24px; }")
        _soft_shadow(self._brand_panel)
        _brand_layout = QVBoxLayout(self._brand_panel)
        _brand_layout.setContentsMargins(10, 10, 10, 10)
        self._brand_logo = QLabel(self._brand_panel)
        self._brand_logo.setAlignment(Qt.AlignCenter)
        self._brand_logo.setStyleSheet("background-color: transparent;")
        try:
            _logo_dpr = self.devicePixelRatioF()
        except Exception:
            _logo_dpr = 1.0
        self._brand_logo.setPixmap(_make_glossy_apple(190, _logo_dpr))
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor as _QColor
        _glow = QGraphicsDropShadowEffect(self._brand_logo)
        _glow.setBlurRadius(28)
        _glow.setOffset(0, 4)
        _glow.setColor(_QColor(255, 255, 255, 110))
        self._brand_logo.setGraphicsEffect(_glow)
        _brand_layout.addWidget(self._brand_logo, 1)
        phone_col.addWidget(self._brand_panel, 0, Qt.AlignHCenter)
        self._phone_caption = QLabel("iPhone", self)
        self._phone_caption.setAlignment(Qt.AlignCenter)
        self._phone_caption.setStyleSheet(t("phone_caption"))
        phone_col.addWidget(self._phone_caption)
        phone_links = QHBoxLayout()
        phone_links.setContentsMargins(0, 0, 0, 0)
        phone_links.setSpacing(2)
        phone_links.addStretch(1)
        self._reboot_link = QPushButton(
            QCoreApplication.translate("Nugget", "Reboot"), self)
        self._reboot_link.setStyleSheet(t("phone_link_button"))
        self._reboot_link.hide()  # no existing device-power handler
        phone_links.addWidget(self._reboot_link)
        self._turnoff_link = QPushButton(
            QCoreApplication.translate("Nugget", "Turn Off"), self)
        self._turnoff_link.setStyleSheet(t("phone_link_button"))
        self._turnoff_link.hide()  # no existing device-power handler
        phone_links.addWidget(self._turnoff_link)
        self._refresh_link = QPushButton(
            QCoreApplication.translate("Nugget", "Refresh"), self)
        self._refresh_link.setStyleSheet(t("phone_link_button"))
        self._refresh_link.clicked.connect(self.refresh_devices)
        phone_links.addWidget(self._refresh_link)
        phone_links.addStretch(1)
        phone_col.addLayout(phone_links)
        phone_col.addStretch(1)
        main_row.addLayout(phone_col)

        # Info table column.
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(10)

        # Title card: name + capacity chip + color + charging/battery.
        self._title_card = QFrame(self)
        self._title_card.setObjectName("deviceTitleCard")
        self._title_card.setStyleSheet(t("modern_card"))
        _soft_shadow(self._title_card)
        title_layout = QHBoxLayout(self._title_card)
        title_layout.setContentsMargins(16, 12, 16, 12)
        title_layout.setSpacing(10)
        self._device_title = QLabel("No device connected", self._title_card)
        self._device_title.setStyleSheet(t("info_header"))
        title_layout.addWidget(self._device_title)
        self._capacity_chip = QLabel("—", self._title_card)
        self._capacity_chip.setStyleSheet(t("capacity_chip"))
        self._capacity_chip.setMinimumWidth(58)
        self._capacity_chip.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(self._capacity_chip)
        self._color_value = QLabel("Color —", self._title_card)
        self._color_value.setStyleSheet(t("home_subtitle"))
        title_layout.addWidget(self._color_value)
        title_layout.addStretch(1)
        self._battery_value = QLabel("Battery —", self._title_card)
        self._battery_value.setStyleSheet(t("info_value"))
        title_layout.addWidget(self._battery_value)
        self.subtitle = QLabel(
            QCoreApplication.translate("Nugget", "iPhone (iOS —)"), self)
        self.subtitle.hide()
        self.status_lbl = QLabel("", self)
        self.status_lbl.setTextFormat(Qt.RichText)
        self.status_lbl.setStyleSheet("background-color: transparent;")
        self.status_lbl.hide()
        info_col.addWidget(self._title_card)

        # Detailed info card: plain label:value rows with light separators,
        # two columns — no boxed input look (reference style).
        self._details_card = QFrame(self)
        self._details_card.setObjectName("deviceDetailsCard")
        self._details_card.setStyleSheet(t("modern_card"))
        _soft_shadow(self._details_card)
        details_layout = QVBoxLayout(self._details_card)
        details_layout.setContentsMargins(18, 10, 18, 12)
        details_layout.setSpacing(0)
        self._info_values = {}
        self._info_rows = {}
        left_fields = [
            ("ios", "iOS Version"),
            ("model", "Product Type"),
            ("build", "Build"),
            ("connection", "Connection"),
            ("serial", "Serial Number"),
        ]
        right_fields = [
            ("support", "Support"),
            ("gestalt", "MobileGestalt"),
            ("statusbar", "Status Bar"),
            ("udid", "UDID"),
            ("storage", "Storage"),
        ]

        def _info_row(key, label_text, last=False):
            row = QFrame(self._details_card)
            row.setFrameShape(QFrame.NoFrame)
            if not last:
                row.setStyleSheet(
                    ".QFrame { background: transparent; border: none; "
                    "border-bottom: 1px solid #EDF2F7; }")
            else:
                row.setStyleSheet(
                    ".QFrame { background: transparent; border: none; }")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 7, 0, 7)
            row_layout.setSpacing(12)
            lbl = QLabel(QCoreApplication.translate("Nugget", label_text), row)
            lbl.setStyleSheet(t("info_label"))
            lbl.setMinimumWidth(118)
            row_layout.addWidget(lbl)
            val = QLabel("—", row)
            val.setStyleSheet(t("info_value"))
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._info_values[key] = val
            self._info_rows[key] = row
            row.hide()  # shown by _set_info only when real data exists
            row_layout.addWidget(val, 1)
            return row

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(30)
        for fields in (left_fields, right_fields):
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            for i, (key, label_text) in enumerate(fields):
                col.addWidget(_info_row(key, label_text,
                                        last=i == len(fields) - 1))
            columns.addLayout(col, 1)
        details_layout.addLayout(columns)
        info_col.addWidget(self._details_card)

        # Mirror attributes used by refresh paths / older callers.
        self._device_ios_value = self._info_values.get("ios")
        self._device_build_value = self._info_values.get("build")
        self._device_connection_value = self._info_values.get("connection")
        self._device_support_value = self._info_values.get("support")

        # No big blue action buttons here (reference uses tiny text links
        # under the phone). The handlers stay wired on hidden controls so
        # existing refresh/settings paths keep working.
        self._refresh_info_btn = QPushButton(
            QCoreApplication.translate("Nugget", "Refresh Device Info"), self)
        self._refresh_info_btn.setStyleSheet(t("primary_button"))
        self._refresh_info_btn.clicked.connect(self.refresh_devices)
        self._refresh_info_btn.hide()
        self._details_btn = QPushButton(
            QCoreApplication.translate("Nugget", "Device Settings"), self)
        self._details_btn.setStyleSheet(t("primary_button"))
        self._details_btn.clicked.connect(self.open_settings)
        self._details_btn.hide()

        # Tweak list card (user change 2026-10-02, replaces the old Hard
        # Disk Capacity card): the build's tweak catalogue lives in the
        # right column under the device info card, derived live from the
        # registry with research-only / user-retained / device-test badges.
        self._catalogue_card = _CatalogueCard(self)
        self._catalogue_card.setObjectName("tweakListCard")
        catalogue_layout = QVBoxLayout(self._catalogue_card)
        catalogue_layout.setContentsMargins(16, 14, 16, 14)
        catalogue_layout.setSpacing(7)
        self._catalogue_header = QLabel(
            QCoreApplication.translate("Nugget", "TWEAKS IN THIS BUILD"),
            self._catalogue_card)
        self._catalogue_header.setStyleSheet(t("home_section_title"))
        catalogue_layout.addWidget(self._catalogue_header)
        self._catalogue_rows_box = QWidget(self._catalogue_card)
        self._catalogue_rows_layout = QVBoxLayout(self._catalogue_rows_box)
        self._catalogue_rows_layout.setContentsMargins(2, 2, 2, 2)
        self._catalogue_rows_layout.setSpacing(6)
        catalogue_layout.addWidget(self._catalogue_rows_box)
        self.tweak_catalogue_entries = ()
        # Plain-text mirror of the chip rows (kept hidden; tests and
        # accessibility read the names from here).
        self.tweak_catalogue_lbl = QLabel("", self._catalogue_card)
        self.tweak_catalogue_lbl.hide()
        info_col.addWidget(self._catalogue_card)
        info_col.addStretch(1)
        main_row.addLayout(info_col, 1)
        layout.addLayout(main_row)

        # Divider + bottom action tiles (reference).
        divider = QFrame(self)
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"color: {self._c.divider};")
        layout.addWidget(divider)

        tile_widgets = []
        self._tile_by_title = {}
        for title, sub, page_index, color, icon_res in _ACTION_TILES:
            tile = _ActionTile(title, sub, color, icon_res, self)
            tile.mousePressEvent = (
                lambda e, pg=page_index, tl=tile: self._on_tile_clicked(tl, pg))
            self._tile_by_title[title] = tile
            tile_widgets.append(tile)
            self._tiles.append(tile)
        self.cards_grid = _TileRow(tile_widgets, self)
        layout.addWidget(self.cards_grid)

        # Named handles kept for the gating code in the shell mixins.
        self.tweaks_card = self._tile_by_title["Tweaks"]
        self.liquidglass_card = self._tile_by_title["Liquid Glass"]
        self.posterboard_card = self._tile_by_title["PosterBoard"]
        self.daemons_card = self._tile_by_title["Daemons"]
        self.statusbar_card = self._tile_by_title["Status Bar"]
        self.mobilegestalt_card = self._tile_by_title["MobileGestalt"]
        self.appdata_card = self._tile_by_title["Backup / Restore"]
        self.icon_themes_card = self._tile_by_title["Tweaks"]
        self.passcode_theme_card = self._tile_by_title["Tweaks"]

        # The tweak catalogue card lives in the right column (built with
        # the info cards above); refresh it now that the page exists.
        self.refresh_tweak_catalogue()

        # Session controls: reset + presets.
        self._session_title = QLabel("SESSION CONTROLS", self)
        self._session_title.setStyleSheet(t("home_section_title"))
        layout.addWidget(self._session_title)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(12)
        reset_btn = IOSDangerButton(
            QCoreApplication.translate("Nugget", "Reset Tweaks"))
        reset_btn.clicked.connect(self.reset_tweaks)
        actions.addWidget(reset_btn, 1)
        layout.addLayout(actions)

        self.preset_widget = PresetWidget(
            window=self.window, on_manage=self.open_presets_section,
            ios_style=True)
        layout.addWidget(self.preset_widget)

        self.process_status_lbl = QLabel("", self)
        self.process_status_lbl.setWordWrap(True)
        self.process_status_lbl.setAlignment(Qt.AlignCenter)
        self.process_status_lbl.setStyleSheet(t("process_status_green"))
        self.process_status_lbl.hide()
        layout.addWidget(self.process_status_lbl)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_process_status)

        layout.addStretch()

        self._retheme()
        self.update_status()
        self.update_device_info()
        self.refresh_preset_widget()

    def _style_device_combo(self):
        self.device_combo.setStyleSheet(t("home_combo"))

    def _apply_icon(self, button, resource_path: str):
        c = ColorThemeManager.instance().colors
        button.setIcon(theme_icon(resource_path, c.accent))

    def _retheme(self):
        self._c = ColorThemeManager.instance().colors
        c = self._c
        self._scroll.setStyleSheet(t("scroll_area_transparent"))
        self._title.setStyleSheet(t("home_title"))
        self.subtitle.setStyleSheet(t("home_subtitle"))
        self._device_title.setStyleSheet(t("info_header"))
        if hasattr(self, "_title_card"):
            self._title_card.setStyleSheet(t("modern_card"))
        if hasattr(self, "_details_card"):
            self._details_card.setStyleSheet(t("modern_card"))
        if hasattr(self, "_capacity_card"):
            self._capacity_card.setStyleSheet(t("modern_card"))
        if hasattr(self, "_capacity_chip"):
            self._capacity_chip.setStyleSheet(t("capacity_chip"))
        if hasattr(self, "_refresh_link"):
            self._refresh_link.setStyleSheet(t("phone_link_button"))
        self._phone_caption.setStyleSheet(t("phone_caption"))
        self._style_device_combo()
        self._refresh_btn.setStyleSheet(t("home_icon_button"))
        self._apply_icon(self._refresh_btn, ":/icon/arrow-clockwise.svg")
        self._settings_btn.setStyleSheet(t("home_icon_button"))
        self._apply_icon(self._settings_btn, ":/icon/gear.svg")
        self._refresh_info_btn.setStyleSheet(t("primary_button"))
        self._details_btn.setStyleSheet(t("primary_button"))
        for tile in self._tiles:
            tile._retheme()
        if hasattr(self, "_catalogue_header"):
            self._catalogue_header.setStyleSheet(t("home_section_title"))
        if hasattr(self, "_session_title"):
            self._session_title.setStyleSheet(t("home_section_title"))
        if hasattr(self, "tweak_catalogue_lbl"):
            self.tweak_catalogue_lbl.setStyleSheet(
                f"font-size: 12.5px; line-height: 1.35; color: {c.text_secondary};"
                " background-color: transparent;")
        self.process_status_lbl.setStyleSheet(t("process_status_green"))
        self.update_status()

    def populate_device_picker(self):
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        try:
            devices = self.window.device_manager.devices
            if devices:
                for device in devices:
                    tag = " (@ USB)" if device.connected_via_usb else " (@ WiFi)"
                    self.device_combo.addItem(f"{device.name}{tag}")
            else:
                self.device_combo.addItem(
                    QCoreApplication.translate("QCoreApplication", "No Device"))
        except Exception:
            self.device_combo.addItem(
                QCoreApplication.translate("QCoreApplication", "No Device"))
        self.device_combo.blockSignals(False)

    @Slot()
    def on_device_changed(self, index):
        if len(self.window.device_manager.devices) > 0 and index >= 0:
            self.window.change_selected_device(index)
            self.update_device_info()
            self.update_status()

    # -- layout health -----------------------------------------------------
    def _sync_scroll_content_height(self):
        """Pin the scroll content to its natural (uncompressed) height.

        Without this the scroll area squeezes the whole page into the
        viewport instead of scrolling: the bottom tiles were cropped and
        the catalogue chips collapsed to 0px in real windows (user
        reports 2026-10-03). Deferred so layouts have settled.
        """
        try:
            content = self._scroll_content
            lay = content.layout()
            hint = lay.sizeHint().height() if lay is not None \
                else content.sizeHint().height()
            if hint > 0:
                content.setMinimumHeight(hint)
        except Exception:
            pass

    @Slot()
    def refresh_devices(self):
        self.window.refresh_devices()

    def show_detection_guidance(self, text: str):
        """Show WHY nothing was detected (cable/Trust/driver) in the
        no-device state — under the brand panel, where the user looks."""
        note = str(text or "").strip()
        if note and hasattr(self, "_phone_caption"):
            self._phone_caption.setWordWrap(True)
            self._phone_caption.setText(note)

    @Slot()
    def open_settings(self):
        self.window.ios_pages.setCurrentIndex(4)

    def open_presets_section(self):
        self.window.open_presets_section()

    def switch_to_ios_page(self, index: int):
        self.window.ios_pages.setCurrentIndex(index)

    def reset_tweaks(self):
        from src.gui.dialogs.reset_dialog import ResetDialog
        dialog = ResetDialog(device_manager=self.window.device_manager,
                             apply_reset=self.window.apply_changes)
        dialog.exec()

    def show_process_status(self, text: str, success: bool = None):
        c = self._c
        if success is True:
            color = c.success
        elif success is False:
            color = c.error
        else:
            color = c.accent
        self.process_status_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {color};")
        self.process_status_lbl.setText(text)
        self.process_status_lbl.show()
        self._hide_timer.start(6000)

    def hide_process_status(self):
        self.process_status_lbl.hide()

    def _set_info(self, key, text):
        lbl = self._info_values.get(key)
        if lbl is None:
            return
        text = "" if text is None else str(text)
        lbl.setText(text)
        # Unknown values are hidden, not shown as a stray "—": the whole
        # row disappears until real data exists (user instruction).
        row = getattr(self, "_info_rows", {}).get(key)
        if row is not None:
            row.setVisible(bool(text) and text != "—")

    def update_status(self):
        c = self._c
        try:
            if self.window.device_manager.get_current_device_udid():
                if not self.window.device_manager.get_current_device_is_supported_by_fork():
                    status_text = QCoreApplication.translate(
                        "QCoreApplication", "Not Supported.")
                    color = c.error
                elif self.window.device_manager.get_current_device_partially_supported():
                    status_text = QCoreApplication.translate(
                        "Nugget", "Partially Supported")
                    color = c.warning
                else:
                    status_text = QCoreApplication.translate(
                        "QCoreApplication", "Supported!")
                    color = c.success
            else:
                status_text = QCoreApplication.translate(
                    "Nugget", "Not connected")
                color = c.text_secondary
        except AttributeError:
            status_text = QCoreApplication.translate("Nugget", "Not connected")
            color = c.text_secondary
        self.status_lbl.setText(f"<span style='color:{color};'>{status_text}</span>")
        # The Support row is a per-device verdict: with nothing connected
        # it must not render a status at all (user report — pre-device
        # statuses looked like real answers). The status label above the
        # card still says "Not connected".
        try:
            has_device = bool(self.window.device_manager.get_current_device_udid())
        except Exception:
            has_device = False
        self._set_info("support", status_text if has_device else "")

    def update_device_info(self):
        ver = "—"
        build = "—"
        try:
            ver = self.window.device_manager.get_current_device_version() or "—"
            build = self.window.device_manager.get_current_device_build() or "—"
            self.subtitle.setText(QCoreApplication.translate(
                "Nugget", "iPhone (iOS {0} {1})").format(ver, build))
        except AttributeError:
            self.subtitle.setText(
                QCoreApplication.translate("Nugget", "iPhone (iOS —)"))
        self._set_info("ios", str(ver))
        self._set_info("build", str(build))

        device_name = ""
        model = "—"
        udid = "—"
        try:
            getter = getattr(self.window.device_manager,
                             "get_current_device_name", None)
            if callable(getter):
                device_name = getter() or ""
            model = self.window.device_manager.get_current_device_model() or "—"
            udid = self.window.device_manager.get_current_device_udid() or "—"
        except Exception:
            pass
        if not device_name and hasattr(self, "device_combo"):
            device_name = self.device_combo.currentText().split(" (@", 1)[0]
        self._device_title.setText(device_name or "No device connected")
        # No real capacity / color / battery source exists yet: hide those
        # title-card elements instead of showing placeholder "—" text.
        if hasattr(self, "_capacity_chip"):
            self._capacity_chip.hide()
        if hasattr(self, "_color_value"):
            self._color_value.hide()
        if hasattr(self, "_battery_value"):
            self._battery_value.hide()
        self._phone_caption.setText(device_name or "iPhone")
        self._set_info("device_name", device_name or "—")
        self._set_info("model", str(model))
        if udid and udid != "—" and len(str(udid)) > 18:
            udid = str(udid)[:8] + "…" + str(udid)[-6:]
        self._set_info("udid", str(udid))

        connection = "Not connected"
        try:
            devices = self.window.device_manager.devices
            index = self.device_combo.currentIndex()
            if devices and 0 <= index < len(devices):
                connection = "USB" if devices[index].connected_via_usb else "Wi-Fi"
        except Exception:
            pass
        self._set_info("connection", connection)

        gestalt_text = ""
        statusbar_text = ""
        try:
            devices_now = self.window.device_manager.devices
        except Exception:
            devices_now = []
        if devices_now:
            try:
                from src.devicemanagement.constants import (
                    is_ios27_build, mobilegestalt_decision)
                build_str = "" if build == "—" else str(build)
                ver_str = "" if ver == "—" else str(ver)
                # The MobileGestalt row must report the SAME shared
                # decision that gates the MobileGestalt page/backend
                # (fail-closed on iOS 26.6.1 builds 23G82/23G83) — never a
                # separate guess. Support/Status Bar rows likewise only
                # exist once a real device supplied the inputs.
                decision = mobilegestalt_decision(build_str, ver_str)
                gestalt_text = "Supported" if decision.supported else "Locked"
                statusbar_text = "Locked (iOS 27)" if is_ios27_build(build_str) else "Available"
            except Exception:
                gestalt_text = ""
                statusbar_text = ""
        # No device: gestalt/statusbar stay empty, so _set_info hides the
        # rows entirely instead of showing a misleading pre-computed
        # "Locked"/"Available" with nothing connected.
        self._set_info("gestalt", gestalt_text)
        self._set_info("statusbar", statusbar_text)
        self._set_info("storage", "—")
        if hasattr(self, "tweak_catalogue_lbl"):
            self.refresh_tweak_catalogue()
        QTimer.singleShot(0, self._sync_scroll_content_height)

    def refresh_device_combo(self):
        self.populate_device_picker()

    def refresh_preset_widget(self):
        self.preset_widget.refresh()

    def refresh_tweak_catalogue(self):
        """Rebuild the Home tweak catalogue from the live registry.

        Presentation (user 2026-10-03): one row per section — small bold
        section title, ONE status badge for the whole section (never a
        repeated "(research only)" on every item), then short name chips.
        No descriptions here; detail lives on the Tweaks page. The hidden
        ``tweak_catalogue_lbl`` keeps a plain-text mirror (name lines) for
        tests/accessibility.
        """
        entries = home_tweak_catalogue()
        try:
            from src.tweaks.hidden import current_hidden_tweak_names
            hidden_names = current_hidden_tweak_names()
        except Exception:
            hidden_names = set()
        entries = tuple(
            entry for entry in entries
            if entry["id_name"] not in hidden_names)
        self.tweak_catalogue_entries = entries

        from src.tweaks.capabilities import is_device_test_candidate
        grouped = {section: [] for section in Section}
        plain = {section: [] for section in Section}
        for entry in entries:
            label = QCoreApplication.translate("Nugget", entry["title"])
            grouped[entry["section"]].append((label, entry))
            plain[entry["section"]].append(label)

        # Rebuild the rows box from scratch: deleting the old container
        # wholesale avoids stale-chip/layout residue entirely.
        old_box = getattr(self, "_catalogue_rows_box", None)
        if old_box is not None:
            parent_layout = old_box.parentWidget().layout() \
                if old_box.parentWidget() is not None else None
            if parent_layout is not None:
                parent_layout.removeWidget(old_box)
            old_box.setParent(None)
            old_box.deleteLater()
        self._catalogue_rows_box = QWidget(self._catalogue_card)
        rows_layout = QVBoxLayout(self._catalogue_rows_box)
        rows_layout.setContentsMargins(2, 2, 2, 2)
        rows_layout.setSpacing(6)
        self._catalogue_rows_layout = rows_layout
        card_layout = self._catalogue_card.layout()
        if card_layout is not None:
            card_layout.addWidget(self._catalogue_rows_box)
        lines = []
        for section in Section:
            items = grouped[section]
            if not items:
                continue
            lines.append(section.value + ": " + " · ".join(plain[section]))
            if rows_layout is None:
                continue
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            title = QLabel(section.value, self._catalogue_rows_box)
            title.setStyleSheet(t("catalogue_section"))
            row.addWidget(title)
            candidates = [e for (_l, e) in items
                          if is_device_test_candidate(e["id"])]
            retained = [e for (_l, e) in items
                        if is_audit_user_retained(e["id"])]
            badge_text = ""
            if candidates and len(candidates) == len(items):
                badge_text = QCoreApplication.translate(
                    "Nugget", "UNPROVEN — device test")
            elif candidates:
                badge_text = QCoreApplication.translate(
                    "Nugget", "some UNPROVEN — device test")
            elif retained:
                badge_text = QCoreApplication.translate(
                    "Nugget", "user-retained")
            if badge_text:
                badge = QLabel(badge_text, self._catalogue_rows_box)
                badge.setStyleSheet(t("catalogue_badge"))
                row.addWidget(badge)
            row.addStretch(1)
            rows_layout.addLayout(row)
            chips = QGridLayout()
            chips.setContentsMargins(0, 0, 0, 2)
            chips.setHorizontalSpacing(6)
            chips.setVerticalSpacing(6)
            for index, (label, _entry) in enumerate(items):
                chip_text = label if len(label) <= 32 else label[:30] + "…"
                chip = QLabel(chip_text, self._catalogue_rows_box)
                chip.setToolTip(label)
                chip.setStyleSheet(t("catalogue_chip"))
                chips.addWidget(chip, index // 2, index % 2)
            rows_layout.addLayout(chips)
        self.tweak_catalogue_lbl.setText("\n".join(lines))
        QTimer.singleShot(0, self._sync_scroll_content_height)

    def set_statusbar_visible(self, visible: bool):
        self.statusbar_card.setVisible(visible)
        self.cards_grid.reflow()

    def set_mobilegestalt_visible(self, visible: bool):
        self.mobilegestalt_card.setVisible(visible)
        self.cards_grid.reflow()

    def set_mobilegestalt_locked(self, locked: bool, device_version: str = ""):
        """Lock the MobileGestalt entry on unsupported iOS versions."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        if locked:
            msg = QCoreApplication.translate(
                "Nugget",
                "MobileGestalt is supported on iOS 16.0 – 26.2 beta 1 only.\n\n"
                "This device is on iOS {ver}, so MobileGestalt is locked."
            ).replace("{ver}", device_version or "—")
            self._tile_locks[self.mobilegestalt_card] = msg
            effect = QGraphicsOpacityEffect(self.mobilegestalt_card)
            effect.setOpacity(0.45)
            self.mobilegestalt_card.setGraphicsEffect(effect)
            self.mobilegestalt_card.setCursor(Qt.ArrowCursor)
            self.mobilegestalt_card.setToolTip(
                QCoreApplication.translate(
                    "Nugget", "Requires iOS 16.0 – 26.2 beta 1"))
        else:
            self._tile_locks.pop(self.mobilegestalt_card, None)
            self.mobilegestalt_card.setGraphicsEffect(None)
            self.mobilegestalt_card.setCursor(Qt.PointingHandCursor)
            self.mobilegestalt_card.setToolTip(
                QCoreApplication.translate(
                    "Nugget", "Device feature flags (iOS 16.0 – 26.2b1)"))

    def set_statusbar_locked(self, locked: bool):
        """Lock the Status Bar entry on iOS 27 builds."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        if locked:
            msg = QCoreApplication.translate(
                "Nugget",
                "Status Bar is locked on iOS 27.\n\n"
                "It is only open on iOS 26 and below."
            )
            self._tile_locks[self.statusbar_card] = msg
            effect = QGraphicsOpacityEffect(self.statusbar_card)
            effect.setOpacity(0.45)
            self.statusbar_card.setGraphicsEffect(effect)
            self.statusbar_card.setCursor(Qt.ArrowCursor)
            self.statusbar_card.setToolTip(
                QCoreApplication.translate("Nugget", "Requires iOS 26 or below"))
        else:
            self._tile_locks.pop(self.statusbar_card, None)
            self.statusbar_card.setGraphicsEffect(None)
            self.statusbar_card.setCursor(Qt.PointingHandCursor)
            self.statusbar_card.setToolTip("")

    def _on_tile_clicked(self, tile, page_index):
        lock_msg = self._tile_locks.get(tile)
        if lock_msg:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self.window,
                QCoreApplication.translate("Nugget", "Unavailable"),
                lock_msg)
            return
        if page_index is None:
            self.refresh_devices()
            return
        if page_index == -1:
            self.reset_tweaks()
            return
        self.switch_to_ios_page(page_index)
