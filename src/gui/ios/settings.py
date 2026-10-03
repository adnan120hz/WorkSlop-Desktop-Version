from PySide6.QtCore import Qt, QCoreApplication, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QComboBox, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QInputDialog,
    QFileDialog, QDialog, QPushButton, QButtonGroup
)
from pathlib import Path

from src.gui.ios.components import (
    IOSSectionHeader, IOSSwitch, IOSCard
)
from src.controllers.video_handler import set_ignore_frame_limit
from src.controllers.preset_manager import PresetManager
from src.controllers.hotload import HotLoad
from src.tweaks.tweaks import tweaks, TweakID
from src.gui.thread_workers.apply_worker import ResetPairingThread
from src.gui.theme import ColorThemeManager, AccentPicker
from src.gui.ios.preset_menu import (
    load_preset_flow, save_preset_flow, delete_preset_flow,
    export_preset_flow, partial_export_preset_flow, import_preset_flow,
    preset_subtitle,
)


class IOSSettingsPage(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")
        self.preset_manager = PresetManager()
        self._tm = ColorThemeManager.instance()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self.scroll_area = self._scroll
        content = QWidget()
        self._scroll.setWidget(content)
        layout.addWidget(self._scroll)

        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(16, 16, 16, 32)
        self.content_layout.setSpacing(8)

        # WorkSlop-style layout: grouped cards with icon tiles, one section
        # per concern. All handlers live in _build_settings_ui and below.
        self._build_settings_ui()

        self.refresh_presets()
        self.content_layout.addStretch()

        self._retheme()
        self._tm.theme_changed.connect(self._retheme)

    # ---------- WorkSlop-style rows (icon tile + title + control) ----------
    # Mirrors the WorkSlop iOS app's SettingsView: grouped cards, an icon
    # tile per row, dividers between rows, controls indented or right-aligned.

    def _ws_card(self):
        card = IOSCard()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(0)
        return card, lay

    def _ws_section(self, title: str):
        self.content_layout.addWidget(IOSSectionHeader(
            QCoreApplication.translate("Nugget", title)))
        card, lay = self._ws_card()
        self.content_layout.addWidget(card)
        return lay

    def _ws_divider(self, lay):
        from PySide6.QtWidgets import QFrame
        c = self._tm.colors
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(
            f"background-color: {c.border}; min-height: 1px; max-height: 1px; "
            f"margin-left: 44px; border: none;")
        lay.addWidget(line)

    def _ws_icon(self, code: str) -> QLabel:
        c = self._tm.colors
        lbl = QLabel(code)
        lbl.setFixedSize(32, 32)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"background-color: {c.bg_input}; color: {c.brand}; "
            f"font-size: 11px; font-weight: 700; border-radius: 9px;")
        return lbl

    def _ws_title(self, text: str) -> QLabel:
        c = self._tm.colors
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {c.text_primary}; font-size: 14px; font-weight: 600; "
            f"background-color: transparent;")
        return lbl

    def _ws_value(self, text: str) -> QLabel:
        c = self._tm.colors
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 13px; "
            f"background-color: transparent;")
        return lbl

    def _ws_switch_row(self, lay, code: str, title: str, checked: bool,
                       on_toggled, first=False) -> IOSSwitch:
        if not first:
            self._ws_divider(lay)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 10, 0, 10)
        h.setSpacing(12)
        h.addWidget(self._ws_icon(code))
        lbl = self._ws_title(title)
        h.addWidget(lbl, 1)
        switch = IOSSwitch(checked)
        switch.toggled.connect(on_toggled)
        h.addWidget(switch)
        lay.addWidget(row)
        return switch

    def _ws_info_row(self, lay, code: str, title: str, value: str,
                     first=False) -> QLabel:
        if not first:
            self._ws_divider(lay)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 10, 0, 10)
        h.setSpacing(12)
        h.addWidget(self._ws_icon(code))
        h.addWidget(self._ws_title(title), 1)
        val = self._ws_value(value)
        val.setAlignment(Qt.AlignRight)
        h.addWidget(val)
        lay.addWidget(row)
        return val

    def _ws_control_row(self, lay, code: str, title: str, first=False):
        """Icon + title on top, indented container below for a control."""
        if not first:
            self._ws_divider(lay)
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 10, 0, 10)
        v.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(self._ws_icon(code))
        top.addWidget(self._ws_title(title), 1)
        v.addLayout(top)
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(44, 0, 0, 0)
        body_lay.setSpacing(8)
        v.addWidget(body)
        lay.addWidget(wrap)
        return body_lay

    def _ws_action_row(self, lay, code: str, title: str, on_click,
                       first=False):
        if not first:
            self._ws_divider(lay)
        btn = QPushButton(title)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(on_click)
        c = self._tm.colors
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 9px;
                color: {c.text_primary};
                font-size: 14px; font-weight: 600;
                text-align: left;
                padding: 10px 4px;
            }}
            QPushButton:hover {{ background-color: {c.bg_input}; }}
        """)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(12)
        h.addWidget(self._ws_icon(code))
        h.addWidget(btn, 1)
        chev = QLabel("›")
        chev.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 18px; "
            f"background-color: transparent;")
        h.addWidget(chev)
        # make the whole row clickable
        row.mousePressEvent = lambda e: on_click()
        lay.addWidget(row)
        return row

    def _clear_layout(self, lay):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _build_device_rows(self):
        """(Re)build the 'This device' rows from the live device state."""
        tr = lambda s: QCoreApplication.translate("Nugget", s)
        lay = self._device_section_lay
        self._clear_layout(lay)
        dev = self.window.device_manager.data_singleton.current_device
        if dev is not None:
            self._ws_info_row(lay, "MD", tr("Model"), dev.model or "-", first=True)
            self._ws_info_row(lay, "OS", tr("iOS version"), dev.version or "-")
            self._ws_info_row(lay, "BL", tr("Build"), dev.build or "-")
        else:
            self._ws_info_row(lay, "--", tr("No device"),
                              tr("Connect an iPhone over USB"), first=True)

    def refresh(self):
        """Called when navigating to Settings — picks up device changes."""
        self._build_device_rows()
        btns = getattr(self, "interface_buttons", None)
        if btns:
            from src.gui.ios.theme_manager import ThemeManager
            current = self.window.theme_manager.current_theme
            for theme, btn in btns.items():
                if btn.isChecked() != (theme == current):
                    btn.blockSignals(True)
                    btn.setChecked(theme == current)
                    btn.blockSignals(False)

    def _build_settings_ui(self):
        tr = lambda s: QCoreApplication.translate("Nugget", s)
        pref = self.window.device_manager.pref_manager

        # --- This device ---
        dev_lay = self._ws_section("This device")
        self._device_section_lay = dev_lay
        self._build_device_rows()

        # --- Appearance ---
        ap_lay = self._ws_section("Appearance")
        body = self._ws_control_row(ap_lay, "AP", tr("Accent color"), first=True)
        self._accent_picker = AccentPicker()
        body.addWidget(self._accent_picker)
        # Interface picker (three UIs, user order 2026-10-03): WorkSlop
        # v4 is the main UI; the second UI is the Nugget shell with
        # WorkSlop icons; the third is Full Nugget — the original Nugget
        # interface with only the app name/icon changed. Mirrors the
        # first-launch InterfacePickerDialog choice (ui/theme), and the
        # Settings page stays reachable in every shell so switching back
        # always works.
        from src.gui.ios.theme_manager import ThemeManager
        ui_body = self._ws_control_row(ap_lay, "UI", tr("Interface"))
        seg_row = QWidget()
        seg = QHBoxLayout(seg_row)
        seg.setContentsMargins(0, 0, 0, 0)
        seg.setSpacing(6)
        self.interface_buttons = {}
        self._interface_group = QButtonGroup(self)
        self._interface_group.setExclusive(True)
        for label, theme in ((tr("WorkSlop"), ThemeManager.IOS),
                             (tr("Nugget"), ThemeManager.CLASSIC),
                             (tr("Full Nugget"), ThemeManager.FULL_NUGGET)):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(
                self.window.theme_manager.current_theme == theme)
            btn.clicked.connect(
                lambda _checked=False, t=theme: self.window.apply_theme(t))
            self._interface_group.addButton(btn)
            seg.addWidget(btn)
            self.interface_buttons[theme] = btn
        seg.addStretch(1)
        ui_body.addWidget(seg_row)

        # --- Safety (HotLoad) ---
        sf_lay = self._ws_section("Safety (HotLoad)")
        self._hotload = HotLoad(self.window.settings)
        self.hotload_switch = self._ws_switch_row(
            sf_lay, "SF",
            tr("Apply automatic safety rules (warns on dangerous features)"),
            self._hotload.is_enabled(), self._make_hotload_handler(),
            first=True)

        # --- Updates ---
        up_lay = self._ws_section("Updates")
        self._make_update_channel_combo(
            self._ws_control_row(up_lay, "UP", tr("Update channel"),
                                 first=True))
        self._ws_action_row(up_lay, "CK", tr("Check for Updates"),
                            self._on_check_updates_clicked)

        # (No App Language section: WorkSlop Desktop is English-only by
        # user order 2026-10-03 — the translator is locked to English and
        # the picker/restart flow was removed.)

        # --- Device ---
        dv_lay = self._ws_section("Device")
        self._ws_switch_row(
            dv_lay, "RB", tr("Auto Reboot After Applying"),
            pref.auto_reboot, self._make_setting_handler("auto_reboot"),
            first=True)
        self._ws_action_row(dv_lay, "PR", tr("Reset Device Pairing"),
                            self._on_reset_pairing_clicked)

        # --- PosterBoard ---
        pb_lay = self._ws_section("PosterBoard")
        self._ws_switch_row(
            pb_lay, "FR", tr("Ignore Posterboard Frame Limit"),
            bool(self.window.settings.value("ignore_pb_frame_limit", False, type=bool)),
            lambda checked: (
                set_ignore_frame_limit(checked),
                self.window.settings.setValue("ignore_pb_frame_limit", checked),
                self.window._sync_settings(),
            ), first=True)
        self._ws_switch_row(
            pb_lay, "TD", tr("Disable Tendies Limit"),
            pref.disable_tendies_limit,
            self._make_setting_handler("disable_tendies_limit"))
        self._ws_switch_row(
            pb_lay, "RF", tr("Force PosterBoard Refresh"),
            pref.auto_refresh_posterboard,
            self._make_setting_handler("auto_refresh_posterboard"))

        # --- Backup ---
        bk_lay = self._ws_section("Backup")
        cache_switch = self._ws_switch_row(
            bk_lay, "FC", tr("Use Fast Backup Cache (Experimental)"),
            pref.use_backup_cache,
            lambda checked: self._on_backup_cache_toggled(checked, cache_switch),
            first=True)
        encrypted_switch = self._ws_switch_row(
            bk_lay, "EN", tr("Use Encrypted Backups (Experimental)"),
            pref.use_encrypted_backup,
            lambda checked: self._on_encrypted_backup_toggled(checked, encrypted_switch))
        afc_media_switch = self._ws_switch_row(
            bk_lay, "AM", tr("Backup Photos Over AFC (Parallel)"),
            pref.use_afc_media,
            lambda checked: self._on_afc_media_toggled(checked, afc_media_switch))
        self._make_backup_location_rows(bk_lay)
        self._ws_action_row(bk_lay, "RS", tr("Restore Backup"),
                            self._on_restore_data_clicked)
        self._ws_action_row(bk_lay, "FB", tr("Full Backup"),
                            self._on_full_backup_clicked)

        # --- Setup ---
        st_lay = self._ws_section("Setup")
        self._ws_switch_row(
            st_lay, "SK", tr("Skip Setup * (non-exploit files only)"),
            pref.skip_setup, self._make_setting_handler("skip_setup"),
            first=True)
        self._ws_switch_row(
            st_lay, "SV", tr("Enable Supervision * (requires Skip Setup)"),
            pref.supervised, self._make_setting_handler("supervised"))
        self._make_org_name_row(st_lay)

        # --- Presets ---
        pr_lay = self._ws_section("Presets")
        self.autosave_switch = self._ws_switch_row(
            pr_lay, "AS", tr("Save Tweaks Automatically"),
            self.window.device_manager.pref_manager.tweak_autosave,
            self._on_autosave_toggled, first=True)
        hint = self._ws_value(tr(
            "Saves your tweak selection to a built-in \"AutoSave\" preset "
            "and restores it on the next launch. Turn off to keep changes "
            "for this session only."))
        hint.setContentsMargins(44, 4, 0, 4)
        pr_lay.addWidget(hint)
        self._make_preset_rows(pr_lay)

        # --- About ---
        ab_lay = self._ws_section("About")
        self._ws_action_row(ab_lay, "AB", tr("About WorkSlop Desktop"),
                            self.show_about, first=True)

    def _make_update_channel_combo(self, lay):
        from src.controllers.web_request_handler import (
            CHANNEL_BETA, CHANNEL_STABLE, get_update_channel,
            set_update_channel)
        tr = lambda s: QCoreApplication.translate("Nugget", s)
        self.update_channel_drp = QComboBox()
        self._update_channels = [CHANNEL_STABLE, CHANNEL_BETA]
        # Static literals only — the translation extractor cannot match a
        # variable argument (see AGENTS.md i18n rules).
        self.update_channel_drp.addItem(tr("Release"))
        self.update_channel_drp.addItem(tr("All releases"))
        try:
            self.update_channel_drp.setCurrentIndex(
                self._update_channels.index(get_update_channel()))
        except ValueError:
            self.update_channel_drp.setCurrentIndex(0)
        self.update_channel_drp.currentIndexChanged.connect(
            lambda idx: set_update_channel(self._update_channels[idx]))
        lay.addWidget(self.update_channel_drp)

    def _on_check_updates_clicked(self):
        # Manual check: network runs on a worker thread, never the GUI
        # thread; dedupe is bypassed so the outcome is always reported.
        # The shared runner owns the QThread lifecycle (fresh thread per
        # check, result delivered on the GUI thread), so repeat clicks —
        # including after a finished check — cannot crash on a deleted
        # C++ QThread the way the old hand-rolled pattern did.
        runner = getattr(self, "_update_runner", None)
        if runner is None:
            from src.gui.update_check import UpdateCheckRunner
            runner = UpdateCheckRunner(self)
            runner.result_ready.connect(self._report_update_result)
            self._update_runner = runner
        runner.start()

    def _report_update_result(self, result):
        tr = lambda s: QCoreApplication.translate("Nugget", s)
        if result is not None and result.outcome == "update_available":
            from src.gui.dialogs import UpdateAppDialog
            UpdateAppDialog(result, self).exec()
        elif result is not None and result.outcome == "up_to_date":
            QMessageBox.information(self, tr("Check for Updates"),
                                    tr("You are up to date."))
        else:
            QMessageBox.warning(self, tr("Check for Updates"),
                                tr("Couldn't check for updates. "
                                   "Please try again later."))

    def _on_text_row_edit(self, title: str, on_submit):
        c = self._tm.colors
        dialog = QInputDialog(self)
        dialog.setWindowTitle(title)
        dialog.setLabelText(QCoreApplication.translate("Nugget", "Enter value:"))
        dialog.setTextValue(self.window.device_manager.pref_manager.organization_name)
        dialog.setStyleSheet(f"""
            QDialog, QInputDialog {{ background-color: {c.bg_primary}; }}
            QLabel {{ color: {c.text_primary}; font-size: 15px; }}
            QLineEdit {{
                background-color: {c.bg_input};
                border: none;
                border-radius: 10px;
                color: {c.text_primary};
                font-size: 15px;
                padding: 10px 14px;
            }}
            QPushButton {{
                background-color: {c.accent};
                border-radius: 10px;
                color: {c.text_primary};
                font-size: 15px;
                font-weight: 600;
                padding: 10px 20px;
                border: none;
            }}
        """)
        if dialog.exec() == QDialog.Accepted:
            text = dialog.textValue()
            on_submit(text)
            self.org_value_lbl.setText(text if text else QCoreApplication.translate("MainWindow", "None"))

    def _on_org_name_edited(self, text: str):
        pref = self.window.device_manager.pref_manager
        pref.organization_name = text
        self.window.settings.setValue("organization_name", text)
        self.window._sync_settings()

    def _make_backup_location_rows(self, lay):
        tr = lambda s: QCoreApplication.translate("Nugget", s)
        body = self._ws_control_row(lay, "LC", tr("Backup/Cache Location"))
        custom = self._custom_backup_dir_value()
        self.backup_location_lbl = self._ws_value(
            custom if custom else self._default_backup_dir_text())
        self.backup_location_lbl.setWordWrap(True)
        body.addWidget(self.backup_location_lbl)
        hint = self._ws_value(tr(
            "The protective backup cache, AFC media cache and temporary "
            "backup/restore files for iOS 27 are stored here. Useful when "
            "the system drive is small (e.g. C: 28 GB)."))
        body.addWidget(hint)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        browse_btn = self._make_mini_button(tr("Browse"))
        browse_btn.clicked.connect(self._on_backup_location_browse)
        btns.addWidget(browse_btn)
        btns.addStretch(1)
        body.addLayout(btns)

    def _make_org_name_row(self, lay):
        tr = lambda s: QCoreApplication.translate("Nugget", s)
        c = self._tm.colors
        pref = self.window.device_manager.pref_manager
        self._ws_divider(lay)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 10, 0, 10)
        h.setSpacing(12)
        h.addWidget(self._ws_icon("ON"))
        h.addWidget(self._ws_title(tr("Enter Organization Name")), 1)
        self.org_value_lbl = self._ws_value(
            pref.organization_name if pref.organization_name
            else QCoreApplication.translate("MainWindow", "None"))
        h.addWidget(self.org_value_lbl)
        edit_btn = QLabel("\u270e")
        edit_btn.setStyleSheet(
            f"color: {c.brand}; font-size: 17px; background-color: transparent;")
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.mousePressEvent = lambda e: self._on_text_row_edit(
            tr("Enter Organization Name"), self._on_org_name_edited)
        h.addWidget(edit_btn)
        lay.addWidget(row)

    def _make_preset_rows(self, lay):
        tr = lambda s: QCoreApplication.translate("Nugget", s)
        body = self._ws_control_row(lay, "PS", tr("Preset Manager"))
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self.preset_name_txt = QLineEdit()
        self._preset_name_txt = self.preset_name_txt
        self.preset_name_txt.setPlaceholderText(tr("Preset name"))
        self.preset_desc_txt = QLineEdit()
        self._preset_desc_txt = self.preset_desc_txt
        self.preset_desc_txt.setPlaceholderText(tr("Description (optional)"))
        name_row.addWidget(self.preset_name_txt, 2)
        name_row.addWidget(self.preset_desc_txt, 3)
        body.addLayout(name_row)
        save_btn = self._make_mini_button(tr("Save Preset"))
        save_btn.clicked.connect(self._on_preset_save)
        body.addWidget(save_btn)
        self.preset_list = QListWidget()
        self._preset_list = self.preset_list
        self.preset_list.setMinimumHeight(120)
        body.addWidget(self.preset_list)
        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)
        for title, handler in [
            (tr("Load"), self._on_preset_load),
            (tr("Delete"), self._on_preset_delete),
            (tr("Refresh"), self.refresh_presets),
            (tr("Export"), self._on_preset_export),
            (tr("Partial Export"), self._on_preset_partial_export),
            (tr("Import"), self._on_preset_import),
        ]:
            btn = self._make_mini_button(title)
            btn.clicked.connect(handler)
            btns_row.addWidget(btn)
        body.addLayout(btns_row)

    def _retheme(self):
        c = self._tm.colors
        self._scroll.setStyleSheet(
            f"background-color: {c.bg_primary}; border: none;"
        )
        self._accent_picker.setStyleSheet(
            f"background-color: {c.bg_primary};"
        )
        if hasattr(self, '_preset_name_txt'):
            self._retheme_preset_inputs()
        if hasattr(self, '_preset_list'):
            self._retheme_preset_list()

    def _retheme_preset_inputs(self):
        c = self._tm.colors
        for edit in (self._preset_name_txt, self._preset_desc_txt):
            edit.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {c.bg_input};
                    border: none;
                    border-radius: 10px;
                    color: {c.text_primary};
                    font-size: 14px;
                    padding: 10px 14px;
                }}
            """)

    def _retheme_preset_list(self):
        c = self._tm.colors
        self._preset_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {c.bg_input};
                border: none;
                border-radius: 8px;
                color: {c.text_primary};
                font-size: 13px;
                padding: 4px;
            }}
            QListWidget::item {{ padding: 8px; }}
            QListWidget::item:selected {{ background-color: {c.scrollbar_pressed}; color: {c.text_primary}; }}
        """)

    # ---------- helpers ----------

    def _make_setting_handler(self, pref_attr: str):
        pref = self.window.device_manager.pref_manager
        def handler(checked: bool):
            setattr(pref, pref_attr, checked)
            self.window.settings.setValue(pref_attr, checked)
            self.window._sync_settings()
        return handler

    def _make_hotload_handler(self):
        def handler(checked: bool):
            self._hotload.set_enabled(checked)
        return handler

    def _on_autosave_toggled(self, checked: bool):
        """Persist the AutoSave option and re-label the home preset banner.

        Nothing is written or deleted here: an existing AutoSave preset stays
        on disk and remains loadable from the preset list, it just stops being
        updated and loaded at startup.
        """
        pref = self.window.device_manager.pref_manager
        pref.tweak_autosave = checked
        self.window.settings.setValue("tweak_autosave", checked)
        self.window._sync_settings()
        try:
            self.window._refresh_preset_widgets()
        except Exception:
            # a banner refresh must never break the switch itself
            pass

    def _on_reset_pairing_clicked(self):
        if self.window.device_manager.data_singleton.current_device is None:
            QMessageBox.information(
                self.window,
                QCoreApplication.translate("Nugget", "Pairing Reset"),
                QCoreApplication.translate("Nugget", "No device selected."),
            )
            return
        current = getattr(self, "_reset_pairing_thread", None)
        if current is not None and getattr(current, "isRunning", lambda: False)():
            # already resetting — never spawn a second thread over the device
            return
        thread = ResetPairingThread(self.window.device_manager)
        # Hold the thread on this page like the other workers (ApplyThread,
        # RefreshDevicesThread, RestoreCacheThread, PasscodeThemeWriteThread):
        # a bare local reference lets the Python wrapper be garbage-collected
        # while the native thread is still running, which Qt reports as
        # "QThread: Destroyed while thread '' is still running" and aborts.
        self._reset_pairing_thread = thread
        thread.done.connect(self._on_reset_pairing_done)
        thread.finished.connect(self._on_reset_pairing_thread_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_reset_pairing_thread_finished(self):
        # run() returned, so the native thread is done; drop the page's
        # reference (deleteLater is already queued via the other connection).
        try:
            self._reset_pairing_thread = None
        except Exception:
            pass

    def _on_reset_pairing_done(self, ok: bool, error: str):
        title = QCoreApplication.translate("Nugget", "Pairing Reset")
        if ok:
            QMessageBox.information(
                self.window,
                title,
                QCoreApplication.translate(
                    "Nugget", "Your device's pairing was successfully reset. "
                    "Refresh the device list before applying.")
            )
        else:
            QMessageBox.critical(
                self.window,
                title,
                QCoreApplication.translate(
                    "Nugget", "Failed to reset device pairing: %1").replace("%1", error)
            )

    def _on_restore_data_clicked(self):
        # WorkSlop: Restore Backup menu — 2 formats.
        mbox = QMessageBox(self.window)
        mbox.setWindowTitle("Restore Backup")
        mbox.setText("Choose the backup format to restore:")
        mbox.setInformativeText(
            "Full Backup: a standard iPhone backup folder in iTunes/Finder "
            "format (Manifest.db/Manifest.plist + Info.plist).\n\n"
            "WorkSlop Backup: the selective protective backup this app "
            "keeps on this computer (only restorable from this app).")
        full_btn = mbox.addButton(
            QCoreApplication.translate("Nugget", "Full Backup..."),
            QMessageBox.ButtonRole.ActionRole)
        gn_btn = mbox.addButton(
            QCoreApplication.translate("Nugget", "WorkSlop Backup"),
            QMessageBox.ButtonRole.ActionRole)
        mbox.addButton(QMessageBox.StandardButton.Cancel)
        mbox.exec()
        clicked = mbox.clickedButton()
        if clicked == full_btn:
            self._on_restore_full_backup_clicked()
        elif clicked == gn_btn:
            self._on_restore_workslop_backup_clicked()

    def _on_restore_full_backup_clicked(self):
        folder = QFileDialog.getExistingDirectory(
            self.window,
            QCoreApplication.translate("Nugget", "Select Full Backup Folder"),
            "",
            QFileDialog.Option.ShowDirsOnly)
        if not folder:
            return
        reply = QMessageBox.question(
            self.window,
            "Restore Full Backup?",
            "This restores the selected backup to the connected iPhone, "
            "then reboots it.\n\n"
            "Make sure the iPhone is connected, unlocked and awake, "
            "then do you want to continue?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.window._start_full_backup_restore(folder)

    def _on_restore_workslop_backup_clicked(self):
        # Original GoldenNugget protective-backup restore, unchanged.
        reply = QMessageBox.question(
            self.window,
            "Restore Data From Backup?",
            "This restores photos, messages, contacts and settings from the "
            "last protective backup on this computer.\n\n"
            "Applied tweaks and wallpapers are KEPT.\n\n"
            "Make sure the iPhone is connected, unlocked and awake, "
            "then do you want to continue?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.window._start_cache_restore()

    def _on_full_backup_clicked(self):
        # WorkSlop: real full backup, the iTunes way (mobilebackup2 full).
        reply = QMessageBox.warning(
            self.window,
            QCoreApplication.translate("Nugget", "Full Backup"),
            QCoreApplication.translate(
                "Nugget",
                "This creates a COMPLETE backup of the iPhone, the way "
                "iTunes/Finder does.\n\n"
                "Make sure this computer has enough free storage — the backup "
                "can be as large as the used storage on the iPhone — and note "
                "this takes much longer than the protective backup.\n\n"
                "Continue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        folder = QFileDialog.getExistingDirectory(
            self.window,
            QCoreApplication.translate("Nugget", "Where to save the full backup"),
            "",
            QFileDialog.Option.ShowDirsOnly)
        if not folder:
            return
        self.window._start_full_backup(folder)

    def _on_backup_cache_toggled(self, checked: bool, switch):
        pref = self.window.device_manager.pref_manager
        if checked:
            reply = QMessageBox.question(
                self.window,
                "Enable Fast Backup Cache?",
                "WARNING: The cached backup feature is experimental and, when it "
                "fails, can leave your device without wallpaper data or on the "
                "Setup screen.\n\n"
                "Enable the fast backup cache anyway?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                switch.blockSignals(True)
                switch.setChecked(False)
                switch.blockSignals(False)
                return
        pref.use_backup_cache = checked
        self.window.settings.setValue("use_backup_cache", checked)
        self.window._sync_settings()

    def _on_encrypted_backup_toggled(self, checked: bool, switch):
        pref = self.window.device_manager.pref_manager
        if checked:
            reply = QMessageBox.question(
                self.window,
                "Enable Encrypted Backups?",
                "WARNING: Using encrypted backups with WorkSlop Desktop is experimental "
                "and may cause DATA LOSS or leave your device stuck on the Setup "
                "screen after applying tweaks.\n\n"
                "Make sure you know your backup password before continuing.\n\n"
                "Enable encrypted backups anyway?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                switch.blockSignals(True)
                switch.setChecked(False)
                switch.blockSignals(False)
                return
        pref.use_encrypted_backup = checked
        self.window.settings.setValue("use_encrypted_backup", checked)
        self.window._sync_settings()

    def _on_afc_media_toggled(self, checked: bool, switch):
        pref = self.window.device_manager.pref_manager
        if checked and pref.use_backup_cache:
            QMessageBox.warning(
                self.window,
                "Fast Backup Cache is on",
                "The Fast Backup Cache also uses the AFC (parallel) media "
                "channel for photos, so this switch has no effect while the "
                "cache is on. Turn the cache off to use it on the standard "
                "backup path.",
            )
        pref.use_afc_media = checked
        self.window.settings.setValue("use_afc_media", checked)
        self.window._sync_settings()

    def _custom_backup_dir_value(self) -> str:
        try:
            return str(self.window.settings.value("backup_storage_dir", "", type=str)).strip()
        except Exception:
            return ""

    def _default_backup_dir_text(self) -> str:
        try:
            from src.restore.storage import cache_base
            return str(cache_base())
        except Exception:
            return QCoreApplication.translate("Nugget", "Default (system drive)")

    def _on_backup_location_browse(self):
        current = self._custom_backup_dir_value()
        folder = QFileDialog.getExistingDirectory(
            self.window,
            QCoreApplication.translate("Nugget", "Choose Backup/Cache Location"),
            current if current else str(Path.home()),
        )
        if not folder:
            return
        self.window.settings.setValue("backup_storage_dir", folder)
        self.window._sync_settings()
        self._refresh_backup_location_row()

    # REAUDIT FIX: removed dead _on_backup_location_reset() — no button ever
    # connected to it (only Browse exists), so it was unreachable code.

    def _refresh_backup_location_row(self):
        custom = self._custom_backup_dir_value()
        if hasattr(self, "backup_location_lbl"):
            self.backup_location_lbl.setText(
                custom if custom else self._default_backup_dir_text())

    def _make_mini_button(self, title: str):
        from PySide6.QtWidgets import QPushButton
        c = self._tm.colors
        btn = QPushButton(title)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {c.scrollbar};
                border: none;
                border-radius: 10px;
                color: {c.text_primary};
                font-size: 13px;
                padding: 8px 12px;
            }}
            QPushButton:hover {{ background-color: {c.surface_hover}; }}
        """)
        return btn

    def scroll_to_presets(self):
        if self.scroll_area is not None:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())

    def refresh_presets(self):
        self.preset_list.clear()
        for meta in self.preset_manager.list_presets_with_metadata():
            name = meta["name"]
            desc = meta.get("description", "")
            sub = preset_subtitle(meta)
            if desc:
                item_text = f"{name}\n  {desc}  ({sub})"
            else:
                item_text = f"{name}  ({sub})"
            item = QListWidgetItem(item_text)
            self.preset_list.addItem(item)
            item.setData(Qt.UserRole, name)


    def _on_preset_save(self):
        if save_preset_flow(
                self, self.window, self.preset_manager,
                self.preset_name_txt.text(), self.preset_desc_txt.text()):
            self.preset_name_txt.clear()
            self.preset_desc_txt.clear()
            self.refresh_presets()

    def _on_preset_load(self):
        if self.preset_list.currentRow() < 0:
            QMessageBox.warning(
                self, QCoreApplication.translate("Nugget", "Load Preset"),
                QCoreApplication.translate("Nugget", "Select a preset to load first."))
            return
        name = self._selected_preset_name()
        if not name:
            return
        load_preset_flow(self, self.window, self.preset_manager, name)

    def _selected_preset_name(self) -> str:
        """Name of the preset selected in the list ("" when nothing is)."""
        item = self.preset_list.currentItem()
        if item is None:
            return ""
        return item.data(Qt.UserRole) or item.text().split("\n")[0].strip()

    def _require_selection(self, title: str, message: str) -> str:
        name = self._selected_preset_name()
        if not name:
            QMessageBox.warning(
                self, QCoreApplication.translate("Nugget", title),
                QCoreApplication.translate("Nugget", message))
            return ""
        return name


    def _on_preset_delete(self):
        name = self._require_selection(
            "Delete Preset", "Select a preset to delete first.")
        if name and delete_preset_flow(self, self.preset_manager, name):
            self.refresh_presets()

    def _on_preset_export(self):
        name = self._require_selection(
            "Export Preset", "Select a preset to export first.")
        if name:
            export_preset_flow(self, self.preset_manager, name)

    def _on_preset_partial_export(self):
        name = self._require_selection(
            "Partial Export", "Select a preset to export first.")
        if name:
            partial_export_preset_flow(self, self.preset_manager, name)

    def _on_preset_import(self):
        if import_preset_flow(self, self.preset_manager):
            self.refresh_presets()

    # ---------- about ----------

    def show_about(self):
        from src.gui.dialogs import AboutProgramDialog
        dialog = AboutProgramDialog(self.window)
        dialog.exec()
