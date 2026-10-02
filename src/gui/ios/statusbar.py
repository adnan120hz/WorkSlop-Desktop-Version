from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QHBoxLayout, QLabel,
    QDialog, QPushButton
)
from packaging.version import Version, InvalidVersion

from src.gui.ios.components import (
    IOSSectionHeader, IOSSwitch, IOSSettingsRow,
    TextInputDialog, NumberInputDialog
)
from src.gui.theme import ColorThemeManager
from src.tweaks.tweaks import tweaks, TweakID
from src.tweaks.status_bar.status_setter import StatusBarItem

# iOS 27 dropped the classic statusBarOverrides struct: only the carrier name
# survives, through StatusBarOverrides.archive. Everything else has no
# representation there, so it is hidden rather than shown as a switch that
# silently does nothing. See src/tweaks/status_bar/statusbar_archive.py.
FIRST_ARCHIVE_VERSION = "27.0"


class IOSStatusBarPage(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")
        self.status_manager = tweaks[TweakID.StatusBar]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)


        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._scroll = scroll
        content = QWidget()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(16, 16, 16, 32)
        self.content_layout.setSpacing(8)

        # (widget, survives iOS 27) for every card and section header, so the
        # whole page can be re-gated whenever the connected device changes.
        self._rows: list[tuple[QWidget, bool]] = []

        # Master enable switch
        self._header(QCoreApplication.translate("Nugget", "Status Bar Overrides"), survives_ios27=True)
        self.enabled_switch = self._make_switch(
            QCoreApplication.translate("Nugget", "Enable Status Bar Modifications"),
            self.status_manager.enabled,
            self._on_enabled_toggled,
            survives_ios27=True,
        )

        # Named no-SIM feature (Wave 10): one recipe combining bar count +
        # item visibility on the classic binary path. Research-only and
        # unproven on iOS 26.6.1 — the copy says so, and the row stays
        # disabled wherever the shared capability gate contains Status Bar.
        self._header(QCoreApplication.translate("Nugget", "Signal"))
        self.full_signal_switch = self._make_switch(
            QCoreApplication.translate("Nugget", "Full Signal Bars (No SIM Visual)"),
            self.status_manager.is_full_signal_bars_no_sim_enabled(),
            self._on_full_signal_toggled,
        )
        self._signal_desc = QLabel(QCoreApplication.translate(
            "Nugget",
            "Visual only. Shows filled cellular bars when no SIM is detected; "
            "it does not restore cellular service. Research-only: unverified "
            "on iOS 26.6.1."
        ))
        self._signal_desc.setWordWrap(True)
        self.content_layout.addWidget(self._signal_desc)
        self._rows.append((self._signal_desc, False))
        self._signal_note = QLabel("")
        self._signal_note.setWordWrap(True)
        self.content_layout.addWidget(self._signal_note)
        self._rows.append((self._signal_note, False))

        # Text rows
        self._header(QCoreApplication.translate("Nugget", "Text"), survives_ios27=True)
        self.time_row = self._make_text_row(
            QCoreApplication.translate("Nugget", "Change Status Bar Time Text*"),
            self.status_manager.is_time_overridden(),
            self.status_manager.get_time_override(),
            self.status_manager.get_time_override,
            self.status_manager.set_time, self.status_manager.unset_time,
        )
        self.date_row = self._make_text_row(
            QCoreApplication.translate("Nugget", "Change Status Bar Date Text"),
            self.status_manager.is_date_overridden(),
            self.status_manager.get_date_override(),
            self.status_manager.get_date_override,
            self.status_manager.set_date, self.status_manager.unset_date,
        )
        self.breadcrumb_row = self._make_text_row(
            QCoreApplication.translate("Nugget", "Change Breadcrumb Text"),
            self.status_manager.is_crumb_overridden(),
            self.status_manager.get_crumb_override(),
            self.status_manager.get_crumb_override,
            self.status_manager.set_crumb, self.status_manager.unset_crumb,
        )
        self.battery_detail_row = self._make_text_row(
            QCoreApplication.translate("Nugget", "Change Battery Detail Text"),
            self.status_manager.is_battery_detail_overridden(),
            self.status_manager.get_battery_detail_override(),
            self.status_manager.get_battery_detail_override,
            self.status_manager.set_battery_detail, self.status_manager.unset_battery_detail,
        )
        self.carrier_row = self._make_text_row(
            QCoreApplication.translate("Nugget", "Change Carrier Text"),
            self.status_manager.is_carrier_overridden(),
            self.status_manager.get_carrier_override(),
            self.status_manager.get_carrier_override,
            self.status_manager.set_carrier_override, self.status_manager.unset_carrier_override,
            survives_ios27=True,
        )
        self.badge_row = self._make_text_row(
            QCoreApplication.translate("Nugget", "Change Service Badge Text"),
            self.status_manager.is_primary_service_badge_overridden(),
            self.status_manager.get_primary_service_badge_override(),
            self.status_manager.get_primary_service_badge_override,
            self.status_manager.set_primary_service_badge, self.status_manager.unset_primary_service_badge,
        )
        self.secondary_carrier_row = self._make_text_row(
            QCoreApplication.translate("Nugget", "Secondary Carrier Name"),
            self.status_manager.is_secondary_carrier_overridden(),
            self.status_manager.get_secondary_carrier_override(),
            self.status_manager.get_secondary_carrier_override,
            self.status_manager.set_secondary_carrier_override, self.status_manager.unset_secondary_carrier_override,
            survives_ios27=True,
        )
        self.secondary_badge_row = self._make_text_row(
            QCoreApplication.translate("Nugget", "Secondary Service Badge"),
            self.status_manager.is_secondary_service_badge_overridden(),
            self.status_manager.get_secondary_service_badge_override(),
            self.status_manager.get_secondary_service_badge_override,
            self.status_manager.set_secondary_service_badge, self.status_manager.unset_secondary_service_badge,
        )

        # Number rows
        self._header(QCoreApplication.translate("Nugget", "Levels"))
        self.gsm_row = self._make_number_row(
            QCoreApplication.translate("Nugget", "Change Signal Strength"),
            self.status_manager.is_gsm_signal_strength_bars_overridden(),
            self.status_manager.get_gsm_signal_strength_bars_override(),
            self.status_manager.get_gsm_signal_strength_bars_override,
            self.status_manager.set_gsm_signal_strength_bars, self.status_manager.unset_gsm_signal_strength_bars,
            0, 5,
        )
        self.secondary_gsm_row = self._make_number_row(
            QCoreApplication.translate("Nugget", "Secondary Cellular Signal Bars"),
            self.status_manager.is_secondary_gsm_signal_strength_bars_overridden(),
            self.status_manager.get_secondary_gsm_signal_strength_bars_override(),
            self.status_manager.get_secondary_gsm_signal_strength_bars_override,
            self.status_manager.set_secondary_gsm_signal_strength_bars, self.status_manager.unset_secondary_gsm_signal_strength_bars,
            0, 5,
        )
        self.wifi_row = self._make_number_row(
            QCoreApplication.translate("Nugget", "Change Wi-Fi Signal Strength"),
            self.status_manager.is_wifi_signal_strength_bars_overridden(),
            self.status_manager.get_wifi_signal_strength_bars_override(),
            self.status_manager.get_wifi_signal_strength_bars_override,
            self.status_manager.set_wifi_signal_strength_bars, self.status_manager.unset_wifi_signal_strength_bars,
            0, 5,
        )
        self.battery_capacity_row = self._make_number_row(
            QCoreApplication.translate("Nugget", "Change Battery Icon Capacity"),
            self.status_manager.is_battery_capacity_overridden(),
            self.status_manager.get_battery_capacity_override(),
            self.status_manager.get_battery_capacity_override,
            self.status_manager.set_battery_capacity, self.status_manager.unset_battery_capacity,
            0, 100,
        )
        self.network_type_row = self._make_number_row(
            QCoreApplication.translate("Nugget", "Change Data Network Type"),
            self.status_manager.is_data_network_type_overridden(),
            self.status_manager.get_data_network_type_override(),
            self.status_manager.get_data_network_type_override,
            self.status_manager.set_data_network_type, self.status_manager.unset_data_network_type,
            0, 30,
        )
        self.secondary_network_type_row = self._make_number_row(
            QCoreApplication.translate("Nugget", "Secondary Data Network Type"),
            self.status_manager.is_secondary_data_network_type_overridden(),
            self.status_manager.get_secondary_data_network_type_override(),
            self.status_manager.get_secondary_data_network_type_override,
            self.status_manager.set_secondary_data_network_type, self.status_manager.unset_secondary_data_network_type,
            0, 30,
        )

        # Raw signal strength
        self._header(QCoreApplication.translate("Nugget", "Raw Signal Strength"))
        self._make_switch(
            QCoreApplication.translate("Nugget", "Show Numeric Cellular Strength"),
            self.status_manager.is_raw_gsm_signal_shown(),
            lambda checked: self.status_manager.show_raw_gsm_signal(checked),
        )
        self._make_switch(
            QCoreApplication.translate("Nugget", "Show Numeric Wi-Fi Strength"),
            self.status_manager.is_raw_wifi_signal_shown(),
            lambda checked: self.status_manager.show_raw_wifi_signal(checked),
        )

        # Item show/hide toggles
        self._header(QCoreApplication.translate("Nugget", "Items"))
        self._item_switches = {}
        for name, item in [
            (QCoreApplication.translate("Nugget", "Disable Focus Mode icon"), StatusBarItem.QuietModeStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable Airplane Mode icon"), StatusBarItem.AirplaneModeStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable Cellular Service icon"), StatusBarItem.CellularServiceStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable Wi-Fi icon"), StatusBarItem.CellularDataNetworkStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable Battery icon"), StatusBarItem.MainBatteryStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable Bluetooth icon"), StatusBarItem.BluetoothStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable Alarm icon"), StatusBarItem.AlarmStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable Location icon"), StatusBarItem.LocationStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable Rotation Lock icon"), StatusBarItem.RotationLockStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable AirPlay icon"), StatusBarItem.AirPlayStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable CarPlay icon"), StatusBarItem.CarPlayStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable VPN icon"), StatusBarItem.VPNStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable Voice Control icon"), StatusBarItem.VoiceControlStatusBarItem),
            (QCoreApplication.translate("Nugget", "Disable Liquid Detection Warning icon"), StatusBarItem.LiquidDetectionStatusBarItem),
        ]:
            overridden = self.status_manager.is_item_overridden(item)
            hidden = overridden and self.status_manager.get_item_override(item) == 0
            self._item_switches[item] = self._make_switch(
                name,
                hidden,
                self._make_item_handler(item),
            )

        # Silly mode
        self._header(QCoreApplication.translate("Nugget", "Extras"))
        self._make_switch(
            QCoreApplication.translate("Nugget", "Silly Mode"),
            self.status_manager.is_silly_mode_enabled(),
            lambda checked: self.status_manager.toggle_silly_mode(checked),
        )

        # Explains the trimmed page on iOS 27; hidden everywhere else.
        # The archive mechanism itself is unverified on-device (audit T19),
        # so the note says so outright instead of implying it works.
        self._ios27_note = QLabel(QCoreApplication.translate(
            "Nugget",
            "iOS 27 replaced the status bar override file, so only the carrier "
            "name can be changed here. The other options need iOS 26 or lower. "
            "Note: the iOS 27 carrier-name path is experimental and unverified "
            "on real devices — it may silently do nothing."
        ))
        self._ios27_note.setWordWrap(True)
        self.content_layout.addWidget(self._ios27_note)

        # Shared-capability containment note: on the audited iOS 26.6.1
        # target the whole classic Status Bar family is research-only in
        # the backend, so the classic rows below are disabled with this
        # reason instead of toggling into state that can never apply
        # ("half-active"). Text comes from tweak_deliverability itself.
        self._gate_note = QLabel("")
        self._gate_note.setWordWrap(True)
        self.content_layout.addWidget(self._gate_note)
        self._rows.append((self._gate_note, False))

        self.content_layout.addStretch()

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    def showEvent(self, event):
        super().showEvent(event)
        # The page outlives device changes, so re-gate every time it is shown.
        self._apply_ios27_gating()

    def _current_version(self) -> str:
        try:
            return self.window.device_manager.get_current_device_version() or ""
        except Exception:
            return ""

    def _current_build(self) -> str:
        try:
            return self.window.device_manager.get_current_device_build() or ""
        except Exception:
            return ""

    def _sync_full_signal_switch(self):
        """Reflect the backend predicate on the feature switch (no signals,
        so re-syncing can never fight the item rows over shared fields)."""
        try:
            self.full_signal_switch.blockSignals(True)
            self.full_signal_switch.setChecked(
                self.status_manager.is_full_signal_bars_no_sim_enabled())
            self.full_signal_switch.blockSignals(False)
        except Exception:
            pass

    def _refresh_full_signal_gate(self, is_ios27: bool = False):
        """Enable the named feature only where it may honestly be tried:
        master on, a connected iOS 26.x device, and the shared capability
        gate not containing Status Bar as research-only on this target."""
        version = self._current_version()
        classic_ok = False
        if version:
            try:
                classic_ok = Version("26.0") <= Version(version) < Version("27.0")
            except InvalidVersion:
                classic_ok = False
        deliverable = False
        gate_message = ""
        if classic_ok:
            try:
                from src.tweaks.capabilities import tweak_deliverability
                deliverable, _code, gate_message = tweak_deliverability(
                    TweakID.StatusBar, device_version=version,
                    device_build=self._current_build(),
                    tweak=self.status_manager)
            except Exception:
                deliverable = False
        enabled = bool(self.status_manager.enabled and classic_ok and deliverable)
        try:
            self.full_signal_switch.setEnabled(enabled)
        except Exception:
            pass
        if is_ios27:
            # Hidden with the classic rows; the iOS 27 note explains why.
            self._signal_note.setVisible(False)
        elif classic_ok and deliverable:
            self._signal_note.setText("")
            self._signal_note.setVisible(False)
        elif classic_ok and gate_message:
            # Single source of truth: the note IS the shared capability
            # gate's own message (research-only containment on this
            # target), not page-local copy that could drift from it.
            self._signal_note.setText(gate_message)
            self._signal_note.setVisible(True)
        else:
            self._signal_note.setText(QCoreApplication.translate(
                "Nugget",
                "Available on iOS 26.x with the classic status bar override "
                "file. iOS 27 is not supported yet."))
            self._signal_note.setVisible(True)
        self._sync_full_signal_switch()

    def _on_full_signal_toggled(self, checked: bool):
        if checked:
            self.status_manager.set_full_signal_bars_no_sim()
            # The feature owns index 6 as "shown"; the conflicting Disable
            # Cellular Service icon switch must visibly turn off (display
            # only — backend state stays the source of truth).
            conflict = self._item_switches.get(
                StatusBarItem.CellularServiceStatusBarItem)
            if conflict is not None:
                conflict.blockSignals(True)
                conflict.setChecked(False)
                conflict.blockSignals(False)
        else:
            self.status_manager.unset_full_signal_bars_no_sim()

    def _apply_ios27_gating(self):
        is_ios27 = False
        version = self._current_version()
        if version:
            try:
                is_ios27 = Version(version) >= Version(FIRST_ARCHIVE_VERSION)
            except InvalidVersion:
                is_ios27 = False
        for widget, survives in self._rows:
            widget.setVisible(not is_ios27 or survives)
        self._ios27_note.setVisible(is_ios27)
        if not is_ios27:
            # Honest containment for the classic family: ask the one
            # shared predicate. When it contains Status Bar on this
            # device, every classic switch card goes disabled (backend
            # would skip the family anyway) and the reason is shown.
            deliverable, gate_message = True, ""
            try:
                from src.tweaks.capabilities import tweak_deliverability
                deliverable, _code, gate_message = tweak_deliverability(
                    TweakID.StatusBar, device_version=version or "",
                    device_build=self._current_build(),
                    tweak=self.status_manager)
            except Exception:
                deliverable, gate_message = True, ""
            for widget, _survives in self._rows:
                if widget.findChild(IOSSwitch) is not None:
                    widget.setEnabled(deliverable)
            self._gate_note.setText(
                "" if deliverable else
                QCoreApplication.translate("Nugget", "Locked: ") + gate_message)
            self._gate_note.setVisible(not deliverable)
        self._refresh_full_signal_gate(is_ios27=is_ios27)

    def _header(self, title: str, survives_ios27: bool = False):
        header = IOSSectionHeader(title)
        self.content_layout.addWidget(header)
        self._rows.append((header, survives_ios27))
        return header

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self._scroll.setStyleSheet(f"background-color: {c.bg_primary}; border: none;")
        # Transparent background so it does not read as a dark box, muted text
        # because it is a note rather than a value.
        self._ios27_note.setStyleSheet(
            f"background-color: transparent; color: {c.text_secondary}; font-size: 14px;")
        self._gate_note.setStyleSheet(
            f"background-color: transparent; color: {c.error}; font-size: 14px;")
        for _lbl in (self._signal_desc, self._signal_note):
            _lbl.setStyleSheet(
                f"background-color: transparent; color: {c.text_secondary}; font-size: 14px;")
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if widget is None:
                continue
            # Style labels inside cards (switch rows, text rows, number rows)
            row = widget.findChild(QHBoxLayout)
            if row is not None:
                for j in range(row.count()):
                    child = row.itemAt(j)
                    if child is None:
                        continue
                    w = child.widget()
                    if w is None:
                        continue
                    if isinstance(w, QLabel):
                        current = w.styleSheet()
                        if "font-size: 15px" in current:
                            w.setStyleSheet(f"color: {c.text_primary}; font-size: 15px;")
                        elif "font-size: 14px" in current:
                            w.setStyleSheet(f"color: {c.text_secondary}; font-size: 14px;")
                        elif "font-size: 17px" in current:
                            w.setStyleSheet(f"color: {c.accent}; font-size: 17px;")
            # Style QPushButton (edit buttons) inside cards
            btn = widget.findChild(QPushButton) if hasattr(widget, 'findChild') else None
            if btn is not None:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: transparent;
                        border: none;
                        color: {c.accent};
                        font-size: 17px;
                    }}
                """)

    def _make_item_handler(self, item: StatusBarItem):
        def handler(checked: bool):
            if checked:
                # switch ON → the icon is disabled (forced hidden)
                self.status_manager.set_item_override(item, False)
            elif self.status_manager.is_item_overridden(item):
                # switch OFF → back to the stock default visibility
                self.status_manager.unset_item_override(item)
            # Conflict rule: hiding the cellular service item (or changing
            # the signal item) can dissolve the named no-SIM feature; the
            # feature switch must reflect the backend predicate.
            self._sync_full_signal_switch()
        return handler

    def _make_switch(self, title: str, checked: bool, on_toggled, survives_ios27: bool = False):
        c = ColorThemeManager.instance().colors
        card = QWidget()
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(12)
        label = QLabel(title)
        label.setStyleSheet(f"color: {c.text_primary}; font-size: 15px;")
        row.addWidget(label, 1)
        switch = IOSSwitch(checked)
        switch.toggled.connect(on_toggled)
        row.addWidget(switch)
        self.content_layout.addWidget(card)
        self._rows.append((card, survives_ios27))
        return switch
    def _make_text_row(self, title: str, overridden: bool, current: str, getter, setter, unsetter, survives_ios27: bool = False):
        c = ColorThemeManager.instance().colors
        card = QWidget()
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(12)

        label = QLabel(title)
        label.setStyleSheet(f"color: {c.text_primary}; font-size: 15px;")
        row.addWidget(label, 1)

        value_lbl = QLabel(current if overridden else QCoreApplication.translate("Nugget", "Default"))
        value_lbl.setStyleSheet(f"color: {c.text_secondary}; font-size: 14px;")
        row.addWidget(value_lbl)

        switch = IOSSwitch(overridden)
        switch.toggled.connect(lambda checked: self._on_text_row_toggled(checked, getter, setter, unsetter, label, value_lbl))
        row.addWidget(switch)

        edit_btn = IOSSettingsRow("")
        edit_btn.setFixedWidth(44)
        edit_btn.setText("✎")
        edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {c.accent};
                font-size: 17px;
            }}
        """)
        edit_btn.clicked.connect(lambda: self._on_text_row_edit(title, getter, setter, label, value_lbl))
        row.addWidget(edit_btn)

        self.content_layout.addWidget(card)
        self._rows.append((card, survives_ios27))
        return switch
    def _on_text_row_toggled(self, checked: bool, getter, setter, unsetter, label, value_lbl):
        # B9: read the value fresh from the tweak instead of the stale
        # closure captured when the row was built — otherwise a user edit
        # made while the switch is OFF is lost on the next OFF→ON toggle.
        current = getter()
        if checked:
            setter(current)
        else:
            unsetter()
        value_lbl.setText(current if checked else QCoreApplication.translate("Nugget", "Default"))

    def _on_text_row_edit(self, title: str, getter, setter, label, value_lbl):
        current = getter()
        dialog = TextInputDialog(title, current, self)
        if dialog.exec() == QDialog.Accepted:
            value = dialog.get_value()
            setter(value)
            value_lbl.setText(value if value else QCoreApplication.translate("Nugget", "Default"))
            label.setText(title)

    def _make_number_row(self, title: str, overridden: bool, current: int, getter, setter, unsetter, min_val: int, max_val: int, survives_ios27: bool = False):
        c = ColorThemeManager.instance().colors
        card = QWidget()
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(12)

        label = QLabel(title)
        label.setStyleSheet(f"color: {c.text_primary}; font-size: 15px;")
        row.addWidget(label, 1)

        value_lbl = QLabel(str(current) if overridden else QCoreApplication.translate("Nugget", "Default"))
        value_lbl.setStyleSheet(f"color: {c.text_secondary}; font-size: 14px;")
        row.addWidget(value_lbl)

        switch = IOSSwitch(overridden)
        switch.toggled.connect(lambda checked: self._on_number_row_toggled(checked, getter, setter, unsetter, value_lbl))
        row.addWidget(switch)

        edit_btn = QLabel("✎")
        edit_btn.setStyleSheet(f"color: {c.accent}; font-size: 17px;")
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.mousePressEvent = lambda e: self._on_number_row_edit(title, getter, setter, value_lbl, min_val, max_val)
        row.addWidget(edit_btn)

        self.content_layout.addWidget(card)
        self._rows.append((card, survives_ios27))
        return switch
    def _on_number_row_toggled(self, checked: bool, getter, setter, unsetter, value_lbl):
        # B9: same stale-closure fix as the text rows — read the current
        # value from the tweak at toggle time.
        current = getter()
        if checked:
            setter(current)
        else:
            unsetter()
        value_lbl.setText(str(current) if checked else QCoreApplication.translate("Nugget", "Default"))

    def _on_number_row_edit(self, title: str, getter, setter, value_lbl, min_val: int, max_val: int):
        current = getter()
        dialog = NumberInputDialog(title, current, min_val, max_val, self)
        if dialog.exec() == QDialog.Accepted:
            value = dialog.get_value()
            setter(value)
            value_lbl.setText(str(value))

    def _on_enabled_toggled(self, checked: bool):
        self.status_manager.set_enabled(checked)
        # Master off stops staging but must not clear owned fields; it only
        # disables the feature row like every other row's staging gate.
        self._refresh_full_signal_gate()
