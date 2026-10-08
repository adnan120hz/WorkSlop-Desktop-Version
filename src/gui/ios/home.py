from PySide6.QtCore import Qt, QCoreApplication, Slot, QTimer, QSize, QEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QSizePolicy, QScrollArea
)

from src.gui.ios.components import IOSCard, IOSPrimaryButton, IOSDangerButton
from src.gui.preset_widget import PresetWidget
from src.gui.theme import t, ColorThemeManager, theme_icon, theme_pixmap

# Feature tile icon per home card (keyed by the card title).
_FEATURE_ICONS = {
    "PosterBoard": ":/icon/photo-stack.svg",
    "Tweaks": ":/icon/toggles.svg",
    "Daemons": ":/icon/gear.svg",
    "Status Bar": ":/icon/phone.svg",
    "Custom Icon": ":/icon/brush.svg",
    "Passcode Theme": ":/icon/lock.svg",
    "MobileGestalt": ":/icon/flag.svg",
    "Liquid Glass": ":/icon/liquid-glass.svg",
    "Liquid Glass iOS 26.6.1 RC S8": ":/icon/ws-glass.svg",
    "App Data": ":/icon/folder.svg",
}



class _TileCard(IOSCard):
    """A home feature tile (icon + name). Same look as a card, plus hover."""

    def _retheme(self):
        self.setStyleSheet(t("home_tile"))


class _CardGrid(QWidget):
    """Responsive grid for the home feature tiles.

    Reflows the visible tiles into columns based on the available width, up to
    ``MAX_COLUMNS``: the tiles fill rows left to right at every window size the
    app allows (the window has a 1000px minimum and the iOS shell hides the
    sidebar, so the home page always has room for a full row).
    Tiles hidden on purpose (Status Bar on iOS 27, HotLoad-hidden features)
    are tracked via their Show/Hide events, so the grid stays correct even
    before the page itself has been shown. Hidden tiles are dropped from the
    layout entirely and collapse cleanly.
    """
    MIN_CARD_WIDTH = 140
    SPACING = 12
    MAX_COLUMNS = 6

    def __init__(self, cards, parent=None):
        super().__init__(parent)
        self._cards = cards
        self._hidden = set()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(self.SPACING)
        self._grid.setVerticalSpacing(self.SPACING)
        for card in cards:
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card.installEventFilter(self)
        self._layout_key = None
        self._reflow()

    def eventFilter(self, obj, event):
        if obj in self._cards:
            etype = event.type()
            if etype == QEvent.Hide:
                self._hidden.add(obj)
                self._reflow()
            elif etype == QEvent.Show:
                self._hidden.discard(obj)
                self._reflow()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow()

    def reflow(self):
        self._reflow()

    def _col_count(self, count: int) -> int:
        """Pick the largest column count whose tiles stay wide enough.

        Never more than ``MAX_COLUMNS``, so a wide window must not stretch the
        tiles into a long strip; narrower windows drop a column instead of
        squeezing the tiles below a readable width.
        """
        for n in range(min(count, self.MAX_COLUMNS), 0, -1):
            avail = self.width() - self.SPACING * (n - 1)
            if avail / n >= self.MIN_CARD_WIDTH:
                return n
        return 1

    def _reflow(self):
        include = [c for c in self._cards if c not in self._hidden]
        target = []
        if include:
            cols = max(1, min(len(include), self._col_count(len(include))))
            for i, card in enumerate(include):
                target.append((i // cols, i % cols, card))
        key = tuple((r, c, id(w)) for r, c, w in target)
        if key == self._layout_key:
            return
        for card in self._cards:
            self._grid.removeWidget(card)
        for col in range(self.MAX_COLUMNS):
            self._grid.setColumnStretch(col, 1 if col < len(include) else 0)
        for r, c, w in target:
            self._grid.addWidget(w, r, c)
        self._layout_key = key


class IOSHomePage(QWidget):
    # Feature tile: a big icon over the name. The tile height is left to the
    # layout so a subtitle that wraps to two lines grows the whole row.
    TILE_ICON_PX = 84

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")
        self._c = ColorThemeManager.instance().colors
        # (icon label, icon resource, title label, subtitle label) per tile
        self._tiles = []
        # locked tiles (e.g. MobileGestalt on unsupported iOS): clicking
        # shows why instead of opening the page
        self._tile_locks = {}
        self._detection_note = ""

        # Scroll area: the tile grid must never be squeezed below the tile
        # content height, so a short window scrolls instead of overlapping.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self._scroll = scroll
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # ---- Centered hero: big Apple logo + brand + device row ------------
        hero = QVBoxLayout()
        hero.setSpacing(8)
        hero.setContentsMargins(0, 30, 0, 6)

        self._hero_logo = QLabel(self)
        self._hero_logo.setFixedSize(112, 112)
        self._hero_logo.setAlignment(Qt.AlignCenter)
        hero.addWidget(self._hero_logo, 0, Qt.AlignHCenter)

        self._title = QLabel("WorkSlop", self)
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet(t("home_hero_title"))
        hero.addWidget(self._title)

        self.subtitle = QLabel(
            QCoreApplication.translate("Nugget", "iPhone (iOS —)"), self)
        self.subtitle.setAlignment(Qt.AlignCenter)
        self.subtitle.setStyleSheet(t("home_subtitle"))
        hero.addWidget(self.subtitle)

        # Developer credit block under the brand title (user order
        # 2026-10-03): the four clickable lines, colored per shell.
        from src.gui.brand_credits import make_credits_label, credits_html
        c0 = ColorThemeManager.instance().colors
        self.credits_lbl = make_credits_label(
            self, c0.text_secondary, c0.accent)
        self._credits_html = credits_html
        hero.addWidget(self.credits_lbl)

        device_row = QHBoxLayout()
        device_row.setSpacing(10)
        device_row.setContentsMargins(0, 8, 0, 0)
        device_row.addStretch(1)

        self.device_combo = QComboBox(self)
        self.device_combo.setFixedHeight(36)
        self.device_combo.setMinimumWidth(220)
        self._style_device_combo()
        self.populate_device_picker()
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        device_row.addWidget(self.device_combo)

        self._refresh_btn = QPushButton(self)
        self._refresh_btn.setFixedSize(36, 36)
        self._refresh_btn.setIconSize(QSize(18, 18))
        self._refresh_btn.setStyleSheet(t("home_icon_button"))
        self._apply_icon(self._refresh_btn, ":/icon/arrow-clockwise.svg")
        self._refresh_btn.clicked.connect(self.refresh_devices)
        device_row.addWidget(self._refresh_btn)

        self._settings_btn = QPushButton(self)
        self._settings_btn.setFixedSize(36, 36)
        self._settings_btn.setIconSize(QSize(18, 18))
        self._settings_btn.setStyleSheet(t("home_icon_button"))
        self._apply_icon(self._settings_btn, ":/icon/gear.svg")
        self._settings_btn.clicked.connect(self.open_settings)
        device_row.addWidget(self._settings_btn)

        device_row.addStretch(1)
        hero.addLayout(device_row)

        layout.addLayout(hero)
        self._paint_hero_logo()

        self.status_lbl = QLabel("", self)
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setTextFormat(Qt.RichText)
        layout.addWidget(self.status_lbl)

        cards_row = [self._make_card(
            "Tweaks", "Customize system settings", 1),
            self._make_card(
            "Liquid Glass", "Disable the glass look", 9),
            self._make_card(
            "App Data", "Browse app containers", 15),
            self._make_card(
            "MobileGestalt", "Device feature flags (iOS 26.1-)", 12),
            self._make_card(
            "PosterBoard", "Animated wallpapers & templates", 2),
            self._make_card(
            "Daemons", "Disable system daemons", 3),
            self._make_card(
            "Status Bar", "Customize the status bar", 5),
            self._make_card(
            "Custom Icon", "Themed app icons & labels", 10),
            self._make_card(
            "Passcode Theme", "Custom keypad theme (.passthm)", 11),
            self._make_card(
            "Liquid Glass iOS 26.6.1 RC S8", "Latest Keys (S8)", 16,
            route_id="latest")]
        (self.tweaks_card, self.liquidglass_card, self.appdata_card,
         self.mobilegestalt_card, self.posterboard_card, self.daemons_card,
         self.statusbar_card, self.icon_themes_card,
         self.passcode_theme_card, self.lgd_latest_card) = cards_row
        self.cards_grid = _CardGrid(cards_row)
        layout.addWidget(self.cards_grid)

        # Apply lives only in the Backup menu now — home keeps Reset only.
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(12)

        reset_btn = IOSDangerButton(QCoreApplication.translate("Nugget", "Reset Tweaks"))
        reset_btn.clicked.connect(self.reset_tweaks)
        actions.addWidget(reset_btn, 1)

        layout.addLayout(actions)

        self.preset_widget = PresetWidget(
            window=self.window, on_manage=self.open_presets_section, ios_style=True)
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

        # Paint the scroll area background for the active palette right away
        # (the shared _retheme only re-runs on a theme change).
        self._retheme()
        self.update_status()
        self.update_device_info()
        self.refresh_preset_widget()

    def _style_device_combo(self):
        c = self._c
        self.device_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {c.bg_secondary};
                border-radius: 18px;
                color: {c.text_primary};
                padding: 0 16px;
                font-size: 11.25pt;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {c.bg_secondary};
                color: {c.text_primary};
                selection-background-color: {c.accent};
            }}
        """)

    def _apply_icon(self, button, resource_path: str):
        button.setIcon(theme_icon(resource_path, self._c.text_primary))

    def _paint_hero_logo(self):
        """Big Apple logo for the home hero, tinted with the accent color."""
        c = self._c
        try:
            dpr = self.devicePixelRatioF()
        except Exception:
            dpr = 1.0
        self._hero_logo.setPixmap(
            theme_pixmap(":/icon/apple.svg", c.accent, 112, dpr))

    def _retheme(self):
        self._c = ColorThemeManager.instance().colors
        c = self._c
        # Transparent scroll: the animated sky background shows through the
        # page; cards stay solid white so text is always readable.
        self._scroll.setStyleSheet("background: transparent; border: none;")
        self._paint_hero_logo()
        self._title.setStyleSheet(t("home_hero_title"))
        self.subtitle.setStyleSheet(t("home_subtitle"))
        if hasattr(self, "credits_lbl"):
            self.credits_lbl.setText(self._credits_html(
                c.text_secondary, c.accent))
        self._style_device_combo()
        self._refresh_btn.setStyleSheet(t("home_icon_button"))
        self._apply_icon(self._refresh_btn, ":/icon/arrow-clockwise.svg")
        self._settings_btn.setStyleSheet(t("home_icon_button"))
        self._apply_icon(self._settings_btn, ":/icon/gear.svg")
        self.process_status_lbl.setStyleSheet(t("process_status_green"))
        self.update_status()
        # Feature tiles: recolor the icon and restyle the two labels
        for icon_lbl, icon_res, title_lbl, sub_lbl in self._tiles:
            self._paint_tile_icon(icon_lbl, icon_res)
            title_lbl.setStyleSheet(t("home_tile_title"))
            sub_lbl.setStyleSheet(t("home_tile_subtitle"))

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
                self.device_combo.addItem(QCoreApplication.translate("QCoreApplication", "No Device"))
        except Exception:
            self.device_combo.addItem(QCoreApplication.translate("QCoreApplication", "No Device"))
        self.device_combo.blockSignals(False)

    @Slot()
    def on_device_changed(self, index):
        if len(self.window.device_manager.devices) > 0 and index >= 0:
            self.window.change_selected_device(index)
            self.update_device_info()
            self.update_status()

    @Slot()
    def refresh_devices(self):
        self.window.refresh_devices()

    @Slot()
    def open_settings(self):
        self.window.ios_pages.setCurrentIndex(4)

    def open_presets_section(self):
        self.window.open_presets_section()

    def switch_to_ios_page(self, index: int):
        self.window.ios_pages.setCurrentIndex(index)

    def reset_tweaks(self):
        from src.gui.dialogs.reset_dialog import ResetDialog
        dialog = ResetDialog(device_manager=self.window.device_manager, apply_reset=self.window.apply_changes)
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

    def show_detection_guidance(self, text: str):
        """Integration glue (not in v4.0): surface the device-detection
        diagnostic (cable / Trust / driver) on the status line while no
        device is connected, instead of a bare "Not connected". The shell
        calls this after a refresh that found nothing; update_status()
        clears the note as soon as a device is present."""
        self._detection_note = text or ""
        self.update_status()

    def update_status(self):
        c = self._c
        try:
            if self.window.device_manager.get_current_device_udid():
                self._detection_note = ""
                if not self.window.device_manager.get_current_device_is_supported_by_fork():
                    # the fork only supports iOS 26.2+; anything older cannot
                    # be tweaked, so never show it as supported
                    status_text = QCoreApplication.translate(
                        "QCoreApplication", "Not Supported.")
                    color = c.error
                elif self.window.device_manager.get_current_device_partially_supported():
                    status_text = QCoreApplication.translate("Nugget", "Partially Supported")
                    color = c.warning
                else:
                    status_text = QCoreApplication.translate("QCoreApplication", "Supported!")
                    color = c.success
            else:
                note = getattr(self, "_detection_note", "")
                if note:
                    import html as _html
                    status_text = _html.escape(note).replace("\n", "<br>")
                    color = c.warning
                else:
                    status_text = QCoreApplication.translate("Nugget", "Not connected")
                    color = c.text_primary
        except AttributeError:
            status_text = QCoreApplication.translate("Nugget", "Not connected")
            color = c.text_primary
        self.status_lbl.setText(f"<span style='color:{color};'>{status_text}</span>")

    def update_device_info(self):
        try:
            ver = self.window.device_manager.get_current_device_version() or "—"
            build = self.window.device_manager.get_current_device_build() or "—"
            model = self.window.device_manager.get_current_device_model() or ""
            kind = "iPad" if model.startswith("iPad") else "iPhone"
            self.subtitle.setText(QCoreApplication.translate("Nugget", "{0} (iOS {1} {2})").replace("{0}", kind).replace("{1}", ver).replace("{2}", build))
        except AttributeError:
            self.subtitle.setText(QCoreApplication.translate("Nugget", "iPhone (iOS —)"))

    def refresh_device_combo(self):
        self.populate_device_picker()

    def refresh_preset_widget(self):
        self.preset_widget.refresh()

    def set_statusbar_visible(self, visible: bool):
        self.statusbar_card.setVisible(visible)
        self.cards_grid.reflow()

    def set_mobilegestalt_visible(self, visible: bool):
        self.mobilegestalt_card.setVisible(visible)
        self.cards_grid.reflow()

    def set_lgd_visible(self, visible: bool):
        """Show/hide the Liquid Glass Disable tile."""
        self.lgd_latest_card.setVisible(visible)
        self.cards_grid.reflow()

    def set_mobilegestalt_locked(self, locked: bool, device_version: str = ""):
        """Lock the MobileGestalt tile on unsupported iOS versions.

        The tile stays visible (user asked for it) but clicking explains
        the version requirement instead of opening the page.
        """
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
                QCoreApplication.translate("Nugget", "Requires iOS 16.0 – 26.2 beta 1"))
        else:
            self._tile_locks.pop(self.mobilegestalt_card, None)
            self.mobilegestalt_card.setGraphicsEffect(None)
            self.mobilegestalt_card.setCursor(Qt.PointingHandCursor)
            self.mobilegestalt_card.setToolTip(
                QCoreApplication.translate("Nugget", "Device feature flags (iOS 26.1-)"))

    def set_statusbar_locked(self, locked: bool):
        """Lock the Status Bar tile on iOS 27 builds.

        The tile stays visible but clicking explains that Status Bar is
        only open on iOS 26 and below.
        """
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
            self.statusbar_card.setToolTip(
                QCoreApplication.translate("Nugget", "Customize the status bar"))

    def _make_card(self, title: str, subtitle: str, page_index: int,
                   route_id: str = None) -> IOSCard:
        """One home feature tile: a big themed icon with the name below it."""
        card = _TileCard()
        card.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 12, 12, 14)
        card_layout.setSpacing(8)

        icon_res = _FEATURE_ICONS.get(title, ":/icon/compass.svg")
        icon_lbl = QLabel(card)
        icon_lbl.setFixedSize(self.TILE_ICON_PX, self.TILE_ICON_PX)
        icon_lbl.setAlignment(Qt.AlignCenter)
        # transparent, so the label never paints the palette window color over
        # the tile (see the home_tile_* styles)
        icon_lbl.setStyleSheet("background-color: transparent;")
        self._paint_tile_icon(icon_lbl, icon_res)
        card_layout.addWidget(icon_lbl, 0, Qt.AlignHCenter)

        title_lbl = QLabel(QCoreApplication.translate("Nugget", title), card)
        title_lbl.setWordWrap(True)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(t("home_tile_title"))
        card_layout.addWidget(title_lbl, 0, Qt.AlignHCenter)

        sub_lbl = QLabel(QCoreApplication.translate("Nugget", subtitle), card)
        sub_lbl.setWordWrap(True)
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setStyleSheet(t("home_tile_subtitle"))
        card_layout.addWidget(sub_lbl, 0, Qt.AlignHCenter)

        card_layout.addStretch(1)

        # kept for _retheme(): icons are recolored, labels restyled
        self._tiles.append((icon_lbl, icon_res, title_lbl, sub_lbl))

        card.mousePressEvent = lambda e, c=card, r=route_id: \
            self._on_tile_clicked(c, page_index, r)
        card.setCursor(Qt.PointingHandCursor)
        card.setToolTip(QCoreApplication.translate("Nugget", subtitle))
        return card

    def _on_tile_clicked(self, card: IOSCard, page_index: int,
                         route_id: str = None):
        lock_msg = self._tile_locks.get(card)
        if lock_msg:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self.window,
                QCoreApplication.translate("Nugget", "Unavailable"),
                lock_msg)
            return
        self.switch_to_ios_page(page_index)
        if route_id:
            page = getattr(self.window, "ios_lgd", None)
            focus_route = getattr(page, "focus_route", None)
            if callable(focus_route):
                focus_route(route_id)

    def _paint_tile_icon(self, label: QLabel, icon_res: str):
        """Draw a feature icon at tile size (and screen density) in the
        current text color."""
        label.setPixmap(theme_pixmap(
            icon_res, self._c.text_primary, self.TILE_ICON_PX,
            self.devicePixelRatioF()))
