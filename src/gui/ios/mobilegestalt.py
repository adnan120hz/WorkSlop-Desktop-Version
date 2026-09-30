"""MobileGestalt page (iOS style).

Tweak logic is ported verbatim from leminlimez/Nugget; this file only renders
it in the WorkSlop iOS interface. Build rule (user decision 2026-09-30):
MobileGestalt is open on iOS 16.0 through iOS 26.2 beta 1, locked after that.
"""
import plistlib

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QComboBox,
    QLineEdit, QFileDialog, QMessageBox, QSizePolicy, QToolButton,
)

from src.gui.ios.components import (
    IOSSectionHeader, IOSCard, IOSSwitch, IOSPrimaryButton, IOSDangerButton,
)
from src.gui.theme import ColorThemeManager, t
from src.tweaks.tweaks import tweaks, TweakID
from src.tweaks.tweak_loader import load_mobilegestalt
from src.tweaks.custom_gestalt_tweaks import CustomGestaltTweaks, ValueTypeStrings
from src.devicemanagement.constants import is_gestalt_supported_build


def tr(s: str) -> str:
    return QCoreApplication.translate("Nugget", s)


# Dynamic Island option labels, identical to Nugget's retranslateUi strings.
_DI_LABELS = [
    "None",
    "2436 (iPhone X Gestures for SE phones)",
    "2556 (iPhone 14 Pro Dynamic Island)",
    "2796 (iPhone 14 Pro Max Dynamic Island)",
    "2622 (iPhone 16 Pro Dynamic Island)",
    "2868 (iPhone 16 Pro Max Dynamic Island)",
]


class IOSMobileGestaltPage(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(t("scroll_area"))
        self._scroll = scroll
        self.content = _GestaltContent(window, self)
        scroll.setWidget(self.content)
        layout.addWidget(scroll)

    def refresh(self):
        self.content.refresh()

    def _retheme(self):
        self._scroll.setStyleSheet(t("scroll_area"))
        self.content._retheme()


class _GestaltContent(QWidget):
    def __init__(self, window, page):
        super().__init__(page)
        self.window = window
        self._page = page

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 24)
        self._layout.setSpacing(12)

        # Support banner: always visible, states the supported iOS range.
        self._support_card = IOSCard()
        support_layout = QHBoxLayout(self._support_card)
        support_layout.setContentsMargins(16, 12, 16, 12)
        self._support_lbl = QLabel()
        self._support_lbl.setWordWrap(True)
        support_layout.addWidget(self._support_lbl)
        self._layout.addWidget(self._support_card)

        self._notice_card = IOSCard()
        notice_layout = QHBoxLayout(self._notice_card)
        notice_layout.setContentsMargins(16, 12, 16, 12)
        self._notice_lbl = QLabel()
        self._notice_lbl.setWordWrap(True)
        notice_layout.addWidget(self._notice_lbl)
        self._layout.addWidget(self._notice_card)
        self._notice_card.hide()

        # MobileGestalt file card
        self._file_card = IOSCard()
        file_layout = QVBoxLayout(self._file_card)
        file_layout.setContentsMargins(16, 12, 16, 12)
        file_layout.setSpacing(8)
        file_title = QLabel(tr("MobileGestalt File"))
        file_title.setStyleSheet("font-size: 15px; font-weight: 600; background-color: transparent;")
        file_layout.addWidget(file_title)
        file_hint = QLabel(tr(
            "Grab your device's own com.apple.MobileGestalt.plist with Nugget's "
            "\u201cSave MobileGestalt\u201d shortcut first. The file is remembered "
            "per device; pick it once."))
        file_hint.setWordWrap(True)
        file_hint.setStyleSheet(t("value_label") + " background-color: transparent;")
        file_layout.addWidget(file_hint)
        self._mga_status = QLabel()
        self._mga_status.setWordWrap(True)
        self._mga_status.setStyleSheet(t("value_label") + " background-color: transparent;")
        file_layout.addWidget(self._mga_status)
        file_btns = QHBoxLayout()
        file_btns.setSpacing(8)
        self._choose_btn = IOSPrimaryButton(tr("Choose File"))
        self._choose_btn.clicked.connect(self._on_choose_file)
        file_btns.addWidget(self._choose_btn)
        self._forget_btn = IOSDangerButton(tr("Forget Saved"))
        self._forget_btn.clicked.connect(self._on_forget_file)
        file_btns.addWidget(self._forget_btn)
        file_btns.addStretch(1)
        file_layout.addLayout(file_btns)
        self._layout.addWidget(self._file_card)

        self._tweaks_section = QWidget()
        self._tweaks_layout = QVBoxLayout(self._tweaks_section)
        self._tweaks_layout.setContentsMargins(0, 0, 0, 0)
        self._tweaks_layout.setSpacing(12)
        self._layout.addWidget(self._tweaks_section)

        self._apply_btn = IOSPrimaryButton(tr("Apply MobileGestalt Tweaks"))
        self._apply_btn.clicked.connect(self._on_apply)
        self._layout.addWidget(self._apply_btn)
        self._layout.addStretch(1)

        self._lineedit_style_fn = None
        self._switches = {}
        self._built = False

    # -- page lifecycle ----------------------------------------------------
    def refresh(self):
        dm = self.window.device_manager
        device = dm.data_singleton.current_device
        version = device.version if device is not None else ""
        build = device.build if device is not None else ""
        gestalt_ok = is_gestalt_supported_build(build)
        load_mobilegestalt(build)
        self._build_tweaks_ui()
        self._update_mga_label()
        self._sync_switches()
        self._update_support_banner(version, build)

        if device is None:
            self._show_notice(tr("Connect a device to use MobileGestalt tweaks."))
        elif not gestalt_ok:
            # Device is connected but its build is outside iOS 16.0 - 26.2b1.
            # (Checked separately from device_available so a connected device
            # on an unsupported build gets the build reason, not "connect".)
            self._show_notice(tr(
                "MobileGestalt tweaks are not supported on this iOS build. "
                "MobileGestalt is open on iOS 16.0 through iOS 26.2 beta 1 only."))
        else:
            self._notice_card.hide()
        self._set_controls_enabled(device is not None and gestalt_ok)

    def _retheme(self):
        for combo in self.findChildren(QComboBox):
            combo.setStyleSheet(t("combo_dropdown"))
        for edit in self.findChildren(QLineEdit):
            edit.setStyleSheet(self._lineedit_style())

    # -- UI construction ---------------------------------------------------
    def _lineedit_style(self) -> str:
        c = ColorThemeManager.instance().colors
        return (
            "QLineEdit {"
            f" background-color: {c.bg_input}; border: none; border-radius: 8px;"
            f" color: {c.text_primary}; font-size: 14px; padding: 8px 10px; }}"
        )

    def _row_card(self) -> tuple:
        card = IOSCard()
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)
        return card, lay

    def _add_switch(self, title: str, tweak_id, on_change=None, section_layout=None):
        card, lay = self._row_card()
        lbl = QLabel(tr(title))
        lbl.setStyleSheet("font-size: 15px; background-color: transparent;")
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)
        sw = IOSSwitch()
        sw.toggled.connect(lambda checked, tid=tweak_id: self._on_switch(tid, checked, on_change))
        lay.addWidget(sw)
        (section_layout or self._tweaks_layout).addWidget(card)
        self._switches[tweak_id] = sw
        return sw

    def _on_switch(self, tweak_id, checked: bool, on_change):
        if tweak_id in tweaks:
            tweaks[tweak_id].set_enabled(checked)
        if on_change:
            on_change(checked)
        self._sync_switches()

    def _build_tweaks_ui(self):
        if self._built:
            return
        self._built = True

        # Dynamic Island (dropdown + rdar-style behaviour from Nugget)
        self._tweaks_layout.addWidget(IOSSectionHeader(tr("Dynamic Island")))
        di_card, di_lay = self._row_card()
        di_lbl = QLabel(tr("Dynamic Island"))
        di_lbl.setStyleSheet("font-size: 15px; background-color: transparent;")
        di_lay.addWidget(di_lbl, 1)
        self._di_combo = QComboBox()
        self._di_combo.addItems([tr(x) for x in _DI_LABELS])
        self._di_combo.setStyleSheet(t("combo_dropdown"))
        self._di_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._di_combo.activated.connect(self._on_di_activated)
        di_lay.addWidget(self._di_combo, 2)
        self._tweaks_layout.addWidget(di_card)

        self._add_switch("Supports Dynamic Island", TweakID.SupportsDynamicIsland)

        # Custom model name
        name_card, name_lay = self._row_card()
        name_lbl = QLabel(tr("Custom Model Name"))
        name_lbl.setStyleSheet("font-size: 15px; background-color: transparent;")
        name_lay.addWidget(name_lbl, 1)
        self._model_name_edit = QLineEdit()
        self._model_name_edit.setPlaceholderText(tr("Model name"))
        self._model_name_edit.setStyleSheet(self._lineedit_style())
        self._model_name_edit.textEdited.connect(
            lambda text: tweaks[TweakID.ModelName].set_value(text, toggle_enabled=False)
            if TweakID.ModelName in tweaks else None)
        name_lay.addWidget(self._model_name_edit, 2)
        name_sw = IOSSwitch()
        name_sw.toggled.connect(lambda c: self._on_switch(TweakID.ModelName, c))
        name_lay.addWidget(name_sw)
        self._tweaks_layout.addWidget(name_card)
        self._switches[TweakID.ModelName] = name_sw

        self._tweaks_layout.addWidget(IOSSectionHeader(tr("Features")))
        self._add_switch("Boot Chime", TweakID.BootChime)
        self._add_switch("Charge Limit", TweakID.ChargeLimit)
        self._add_switch("Tap to Wake", TweakID.TapToWake)
        self._add_switch("Camera Button (iPhone 16 Settings)", TweakID.CameraButton)
        self._add_switch("Disable Parallax", TweakID.Parallax)
        self._add_switch("Stage Manager", TweakID.StageManager)
        self._add_switch("Enable iPadOS", TweakID.iPadOS,
                         on_change=lambda c: tweaks[TweakID.iPadOSCacheData].set_enabled(c)
                         if TweakID.iPadOSCacheData in tweaks else None)
        self._add_switch("iPad Apps", TweakID.iPadApps)
        self._add_switch("Shutter Sound", TweakID.Shutter)
        self._add_switch("Apple Pencil", TweakID.Pencil)
        self._add_switch("Action Button", TweakID.ActionButton)
        self._add_switch("Always On Display", TweakID.AOD)
        self._add_switch("AOD Vibrancy", TweakID.AODVibrancy)
        self._add_switch("Enable Low Power Mode (LGLPM)", TweakID.EnableLGLPM)
        self._add_switch("Disable Low Power Mode (LGLPM)", TweakID.DisableLGLPM)
        self._add_switch("Enable Apple Intelligence (for Unsupported Devices)",
                         TweakID.AIGestalt)

        self._tweaks_layout.addWidget(IOSSectionHeader(tr("Internal")))
        self._add_switch("Internal Install", TweakID.InternalInstall)
        self._add_switch("Show Internal Storage", TweakID.InternalStorage)
        self._add_switch("SRD", TweakID.SRD)
        self._add_switch("Collision SOS", TweakID.CollisionSOS)

        # Custom gestalt keys
        self._tweaks_layout.addWidget(IOSSectionHeader(tr("Custom Gestalt Keys")))
        self._custom_keys_layout = QVBoxLayout()
        self._custom_keys_layout.setSpacing(8)
        self._tweaks_layout.addLayout(self._custom_keys_layout)
        add_btn = IOSPrimaryButton(tr("Add Custom Key"))
        add_btn.clicked.connect(self._on_add_custom_key)
        self._tweaks_layout.addWidget(add_btn)

    def _show_notice(self, text: str):
        self._notice_lbl.setText(text)
        self._notice_lbl.setStyleSheet("font-size: 14px; background-color: transparent;")
        self._notice_card.show()

    def _set_controls_enabled(self, enabled: bool):
        for w in (self._file_card, self._tweaks_section, self._apply_btn):
            w.setEnabled(enabled)

    # -- state sync ----------------------------------------------------------
    def _sync_switches(self):
        for tweak_id, sw in self._switches.items():
            if tweak_id in tweaks:
                try:
                    sw.setChecked(bool(tweaks[tweak_id].enabled))
                except Exception:
                    pass
        # Dynamic Island dropdown: index 0 = none, else selected option + 1
        if hasattr(self, "_di_combo") and TweakID.DynamicIsland in tweaks:
            di = tweaks[TweakID.DynamicIsland]
            if di.enabled:
                self._di_combo.setCurrentIndex(di.get_selected_option() + 1)
            else:
                self._di_combo.setCurrentIndex(0)
        if hasattr(self, "_model_name_edit") and TweakID.ModelName in tweaks:
            self._model_name_edit.setText(str(tweaks[TweakID.ModelName].value or ""))

    def _on_di_activated(self, index: int):
        # Nugget's on_dynamicIslandDrp_activated, without the RdarFix tweak
        # (desk does not port Nugget's resolution fix).
        if TweakID.DynamicIsland not in tweaks:
            return
        if index == 0:
            tweaks[TweakID.DynamicIsland].set_enabled(False)
        else:
            model = ""
            try:
                model = self.window.device_manager.get_current_device_model() or ""
            except Exception:
                pass
            # disable X gestures on devices other than iPhone SEs
            if index != 1 or (model == "iPhone12,8" or model == "iPhone14,6"):
                tweaks[TweakID.DynamicIsland].set_selected_option(index - 1)
            else:
                tweaks[TweakID.DynamicIsland].set_enabled(False)
        self._sync_switches()

    # -- MobileGestalt file --------------------------------------------------
    def _update_mga_label(self):
        dm = self.window.device_manager
        selected = dm.data_singleton.gestalt_path
        if selected is None:
            self._mga_status.setText(tr("No file selected."))
        elif selected == dm.data_singleton.SAVED_GESTALT_STRING:
            self._mga_status.setText(tr("Using the saved file for this device."))
        else:
            self._mga_status.setText(selected)

    def _update_support_banner(self, version: str, build: str = ""):
        """Persistent banner stating the supported iOS range."""
        ok = is_gestalt_supported_build(build) if build else False
        ver_txt = f"iOS {version}" if version else "no device"
        state = (tr("This device ({ver}) is supported.")
                 if ok else tr("This device ({ver}) is NOT supported — "
                              "MobileGestalt is open on iOS 16.0 through "
                              "iOS 26.2 beta 1 only."))
        self._support_lbl.setText(
            tr("Supported: iOS 16.0 \u2013 26.2 beta 1. ") + state.replace("{ver}", ver_txt))
        self._support_lbl.setStyleSheet(
            t("value_label") + " background-color: transparent;")

    def _on_choose_file(self):
        dm = self.window.device_manager
        if dm.data_singleton.current_device is None:
            return
        selected_file, _ = QFileDialog.getOpenFileName(
            self, tr("Select Mobile Gestalt File"), "",
            "Plist Files (*.plist)", options=QFileDialog.ReadOnly)
        if not selected_file:
            dm.data_singleton.gestalt_path = None
            self._update_mga_label()
            return
        try:
            with open(selected_file, 'rb') as in_fp:
                gestalt_plist = plistlib.load(in_fp)
        except Exception:
            QMessageBox.critical(self, tr("Error!"), tr("Could not read that plist file."))
            return
        if "CacheExtra" not in gestalt_plist:
            QMessageBox.critical(self, tr("Error!"), tr("The file is not a mobile gestalt file!"))
            return
        if not dm.pref_manager.is_valid_mga_plist(
                gestalt_plist, dm.get_current_device_build(),
                dm.get_current_device_model()):
            # Nugget's GestaltDialog: confirm before using a mismatched file.
            answer = QMessageBox.question(
                self, tr("MobileGestalt"),
                tr("The gestalt file looks like it was made for a different device.\n"
                   "Are you sure you want to use this one?"))
            if answer != QMessageBox.Yes:
                return
            dm.data_singleton.gestalt_path = selected_file
        else:
            dm.data_singleton.gestalt_path = dm.data_singleton.SAVED_GESTALT_STRING
            dm.pref_manager.save_mga_file(selected_file, dm.get_current_device_udid())
        self._update_mga_label()

    def _on_forget_file(self):
        dm = self.window.device_manager
        if dm.data_singleton.current_device is None:
            return
        dm.pref_manager.remove_mga_data(dm.get_current_device_udid())
        dm.data_singleton.gestalt_path = None
        self._update_mga_label()

    # -- custom gestalt keys ---------------------------------------------------
    def _on_add_custom_key(self):
        # Row layout ported from Nugget's on_addGestaltKeyBtn_clicked.
        key_id = CustomGestaltTweaks.create_tweak()

        widget = QWidget()
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        key_field = QLineEdit()
        key_field.setPlaceholderText(tr("Key"))
        key_field.setStyleSheet(self._lineedit_style())
        key_field.textEdited.connect(
            lambda txt, kid=key_id: CustomGestaltTweaks.set_tweak_key(kid, txt))
        lay.addWidget(key_field, 3)

        type_combo = QComboBox()
        type_combo.addItems(ValueTypeStrings)
        type_combo.setStyleSheet(t("combo_dropdown"))
        lay.addWidget(type_combo, 2)

        value_field = QLineEdit()
        value_field.setPlaceholderText(tr("Value"))
        value_field.setText("1")
        value_field.setStyleSheet(self._lineedit_style())
        value_field.textEdited.connect(
            lambda txt, kid=key_id: CustomGestaltTweaks.set_tweak_value(kid, txt))
        type_combo.activated.connect(
            lambda idx, kid=key_id, vf=value_field:
                vf.setText(CustomGestaltTweaks.set_tweak_value_type(kid, idx)))
        lay.addWidget(value_field, 2)

        del_btn = QToolButton()
        del_btn.setText("\u2715")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(
            lambda _, kid=key_id, w=widget: self._delete_custom_key(kid, w))
        lay.addWidget(del_btn)

        self._custom_keys_layout.addWidget(widget)

    def _delete_custom_key(self, key_id: int, widget: QWidget):
        CustomGestaltTweaks.deactivate_tweak(key_id)
        self._custom_keys_layout.removeWidget(widget)
        widget.setParent(None)

    # -- apply -----------------------------------------------------------------
    def _on_apply(self):
        self.window._start_gestalt_apply()
