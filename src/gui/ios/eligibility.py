"""Eligibility section (iOS style).

Tweak logic is ported verbatim from leminlimez/Nugget's eligibility page
(src/gui/pages/tools/eligibility.py); this file only renders it in the
WorkSlop iOS interface. All checkbox/dropdown/text handlers mirror Nugget's
``on_*`` handlers 1:1.

One deliberate deviation: Nugget maps the iPad-filtered spoof dropdown with
``index + 6``, which is off by one (filtered index 1 is the first iPad model
= tweak index 8, not 7). This port uses an explicit per-item mapping so the
model the user picks is the model that gets spoofed.
"""
from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QSizePolicy,
)

from src.gui.ios.components import (
    IOSSectionHeader, IOSCard, IOSSwitch,
)
from src.gui.theme import t
from src.tweaks.tweaks import tweaks, TweakID
from src.tweaks.tweak_loader import load_eligibility


def tr(s: str) -> str:
    return QCoreApplication.translate("Nugget", s)


# Display labels, identical to Nugget's spoof_drp_options
# (src/gui/pages/tools/gestalt.py::setup_spoofedModelDrp_models).
_SPOOF_IPHONE_LABELS = [
    "iPhone 15 Pro (iPhone16,1)",
    "iPhone 15 Pro Max (iPhone16,2)",
    "iPhone 16 (iPhone17,3)",
    "iPhone 16 Plus (iPhone17,4)",
    "iPhone 16 Pro (iPhone17,1)",
    "iPhone 16 Pro Max (iPhone17,2)",
    "iPhone 17 (iPhone18,3)",
]
_SPOOF_IPAD_LABELS = [
    "iPad Mini (A17 Pro) (W) (iPad16,1)",
    "iPad Mini (A17 Pro) (C) (iPad16,2)",
    "iPad Pro (13-inch) (M4) (W) (iPad16,5)",
    "iPad Pro (13-inch) (M4) (C) (iPad16,6)",
    "iPad Pro (11-inch) (M4) (W) (iPad16,3)",
    "iPad Pro (11-inch) (M4) (C) (iPad16,4)",
    "iPad Pro (12.9-inch) (M2) (W) (iPad14,5)",
    "iPad Pro (12.9-inch) (M2) (C) (iPad14,6)",
    "iPad Pro (11-inch) (M2) (W) (iPad14,3)",
    "iPad Pro (11-inch) (M2) (C) (iPad14,4)",
    "iPad Air (13-inch) (M2) (W) (iPad14,10)",
    "iPad Air (13-inch) (M2) (C) (iPad14,11)",
    "iPad Air (11-inch) (M2) (W) (iPad14,8)",
    "iPad Air (11-inch) (M2) (C) (iPad14,9)",
    "iPad Pro (11-inch) (M1) (W) (iPad13,4)",
    "iPad Pro (11-inch) (M1) (C) (iPad13,5)",
    "iPad Pro (12.9-inch) (M1) (W) (iPad13,8)",
    "iPad Pro (12.9-inch) (M1) (C) (iPad13,9)",
    "iPad Air (M1) (W) (iPad13,16)",
    "iPad Air (M1) (C) (iPad13,17)",
]


class EligibilitySection(QWidget):
    """Nugget's eligibility page as an embeddable section widget."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self._switches = {}
        self._built = False

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

    # -- lifecycle ---------------------------------------------------------
    def refresh(self):
        dm = self.window.device_manager
        device = dm.data_singleton.current_device
        load_eligibility(device)
        self._build_ui(device)
        self._sync_controls()

    # -- ui ----------------------------------------------------------------
    def _row_card(self):
        # Same row shell as the registry tweak rows in tweaks.py (lazy import:
        # tweaks.py imports this module at top level, so a top-level import
        # would be circular).
        from src.gui.ios.tweaks import (
            ROW_CARD_MIN_HEIGHT, ROW_CARD_HMARGIN, ROW_CARD_VMARGIN,
            make_switch_column,
        )
        self._make_switch_column = make_switch_column
        card = IOSCard()
        card.setMinimumHeight(ROW_CARD_MIN_HEIGHT)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(ROW_CARD_HMARGIN, ROW_CARD_VMARGIN,
                               ROW_CARD_HMARGIN, ROW_CARD_VMARGIN)
        lay.setSpacing(12)
        return card, lay

    def _add_switch(self, title: str, tweak_id):
        card, lay = self._row_card()
        lbl = QLabel(tr(title))
        lbl.setStyleSheet("font-size: 15px; background-color: transparent;")
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)
        sw = IOSSwitch()
        sw.toggled.connect(lambda checked, tid=tweak_id: self._on_switch(tid, checked))
        lay.addWidget(self._make_switch_column(card, sw))
        self._layout.addWidget(card)
        self._switches[tweak_id] = sw
        return sw

    def _lineedit_style(self):
        return (
            "QLineEdit { background-color: rgba(255,255,255,0.08);"
            " border: 1px solid rgba(255,255,255,0.15); border-radius: 12px;"
            " padding: 8px 12px; font-size: 14px; color: white; }"
        )

    def _build_ui(self, device):
        if self._built:
            return
        self._built = True

        # EU Enabler (Nugget: euEnablerEnabledChk / regionCodeTxt).
        # B17 honesty fix: Nugget's "Method 1 / Method 2" dropdown only chose
        # which /var/MobileAsset/... path the Config.plist was generated for,
        # but that file is never delivered by this fork (BookRestore does not
        # exist here — device_manager skips it with a warning). The dropdown
        # was a gimmick and is removed; the tweak writes eligibility.plist
        # with the region code swapped, nothing else.
        self._layout.addWidget(IOSSectionHeader(tr("EU Enabler")))
        self._add_switch("Enable EU Enabler", TweakID.EUEnabler)

        eu_note = QLabel(tr(
            "Writes eligibility.plist with your region code to "
            "/var/db/os_eligibility. The MobileAsset Config.plist step needs "
            "BookRestore and is not applied by this app."))
        eu_note.setWordWrap(True)
        eu_note.setStyleSheet(t("value_label"))
        self._layout.addWidget(eu_note)

        region_card, region_lay = self._row_card()
        region_lbl = QLabel(tr("Region Code"))
        region_lbl.setStyleSheet("font-size: 15px; background-color: transparent;")
        region_lay.addWidget(region_lbl, 1)
        self._region_edit = QLineEdit()
        self._region_edit.setPlaceholderText(tr("US"))
        self._region_edit.setMaxLength(2)
        self._region_edit.setStyleSheet(self._lineedit_style())
        self._region_edit.textEdited.connect(self._on_region_edited)
        region_lay.addWidget(self._region_edit, 2)
        self._layout.addWidget(region_card)

        # BookRestore folders (Nugget: createEligFolderChk / createFFFolderChk)
        self._layout.addWidget(IOSSectionHeader(tr("Eligibility Folders")))
        self._elig_folder_sw = self._add_switch("Create Eligibility Folder",
                                                TweakID.CreateBRFolders)
        # Nugget mirrors the FF checkbox off the eligibility one (no separate
        # tweak); both switches drive the same tweak and stay in sync.
        self._ff_folder_sw = self._add_switch("Create Feature Flags Folder",
                                              TweakID.CreateBRFolders)

        # Apple Intelligence (Nugget: enableAIChk / eligFileChk)
        self._layout.addWidget(IOSSectionHeader(tr("Apple Intelligence")))
        self._add_switch("Enable Apple Intelligence (for Unsupported Devices)",
                         TweakID.AIGestalt)
        self._add_switch("Enable Eligibility File", "elig_file_group")

        # Spoofing (Nugget: spoofedModelDrp / spoofHardwareChk / spoofCPUChk)
        self._layout.addWidget(IOSSectionHeader(tr("Spoofing")))
        spoof_card, spoof_lay = self._row_card()
        spoof_lbl = QLabel(tr("Spoofed Model"))
        spoof_lbl.setStyleSheet("font-size: 15px; background-color: transparent;")
        spoof_lay.addWidget(spoof_lbl, 1)
        self._spoof_combo = QComboBox()
        self._spoof_combo.setStyleSheet(t("combo_dropdown"))
        self._spoof_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._spoof_combo.activated.connect(self._on_spoof_activated)
        spoof_lay.addWidget(self._spoof_combo, 2)
        self._layout.addWidget(spoof_card)

        self._setup_spoof_models(device)

        self._add_switch("Spoof Hardware Model", TweakID.SpoofHardware)
        self._add_switch("Spoof CPU Model", TweakID.SpoofCPU)

    def _setup_spoof_models(self, device):
        """Fill the spoof dropdown like Nugget's setup_spoofedModelDrp_models.

        iPhones see iPhone models, iPads see iPad models, no device sees all.
        ``self._spoof_map`` maps each dropdown index to the tweak value index.
        """
        model = ""
        try:
            if device is not None:
                model = device.model or ""
        except Exception:
            pass
        self._spoof_combo.clear()
        self._spoof_map = [0]  # "Original" -> tweak index 0
        self._spoof_combo.addItem(tr("Original"))
        if model.startswith("iPhone") or not model:
            labels = _SPOOF_IPHONE_LABELS
            base = 1
        elif model.startswith("iPad"):
            labels = _SPOOF_IPAD_LABELS
            base = 8
        else:
            labels = _SPOOF_IPHONE_LABELS + _SPOOF_IPAD_LABELS
            base = 1
        for i, label in enumerate(labels):
            self._spoof_combo.addItem(tr(label))
            self._spoof_map.append(base + i)

    # -- handlers (mirror Nugget's EligibilityPage.on_* 1:1) -----------------
    def _on_switch(self, tweak_id, checked: bool):
        if tweak_id == "elig_file_group":
            self._on_elig_file_toggled(checked)
            return
        if tweak_id in tweaks:
            # Nugget: the hardware/CPU checkboxes only take effect when a
            # spoof model is actually selected (selected_option != 0).
            if tweak_id in (TweakID.SpoofHardware, TweakID.SpoofCPU):
                tweaks[tweak_id].set_enabled(
                    checked and tweaks[tweak_id].selected_option != 0)
            else:
                tweaks[tweak_id].set_enabled(checked)
        # Nugget: toggling Create Eligibility Folder mirrors the FF checkbox.
        # Both switches drive the same tweak, so keep them visually in sync.
        if tweak_id == TweakID.CreateBRFolders:
            for sw in (getattr(self, "_elig_folder_sw", None),
                       getattr(self, "_ff_folder_sw", None)):
                if sw is not None:
                    sw.blockSignals(True)
                    sw.setChecked(checked)
                    sw.blockSignals(False)
        self._sync_controls()

    def _on_region_edited(self, text: str):
        if TweakID.EUEnabler in tweaks:
            tweaks[TweakID.EUEnabler].set_region_code(text)

    def _on_elig_file_toggled(self, checked: bool):
        # Nugget: on_eligFileChk_toggled enables all three together.
        for tid in (TweakID.AIEligibility, TweakID.AIFeatureFlags, TweakID.AIFeatureFlagsUI):
            if tid in tweaks:
                tweaks[tid].set_enabled(checked)

    def _on_spoof_activated(self, index: int):
        # Nugget: on_spoofedModelDrp_activated. The hardware/CPU tweaks follow
        # the model selection, gated on their own checkboxes.
        if index < 0 or index >= len(self._spoof_map):
            return
        idx_to_apply = self._spoof_map[index]
        hw_checked = self._switches.get(TweakID.SpoofHardware)
        cpu_checked = self._switches.get(TweakID.SpoofCPU)
        hw_on = hw_checked.isChecked() if hw_checked is not None else False
        cpu_on = cpu_checked.isChecked() if cpu_checked is not None else False
        if TweakID.SpoofModel in tweaks:
            tweaks[TweakID.SpoofModel].set_selected_option(
                idx_to_apply, is_enabled=(index != 0))
        if TweakID.SpoofHardware in tweaks:
            tweaks[TweakID.SpoofHardware].set_selected_option(
                idx_to_apply, is_enabled=(index != 0 and hw_on))
        if TweakID.SpoofCPU in tweaks:
            tweaks[TweakID.SpoofCPU].set_selected_option(
                idx_to_apply, is_enabled=(index != 0 and cpu_on))
        self._sync_controls()

    # -- state sync ----------------------------------------------------------
    def _sync_controls(self):
        for tweak_id, sw in self._switches.items():
            if tweak_id == "elig_file_group":
                # on when any of the three eligibility-file tweaks is on
                on = any(tid in tweaks and tweaks[tid].enabled
                         for tid in (TweakID.AIEligibility, TweakID.AIFeatureFlags,
                                     TweakID.AIFeatureFlagsUI))
                sw.blockSignals(True)
                sw.setChecked(bool(on))
                sw.blockSignals(False)
            elif tweak_id in tweaks:
                sw.blockSignals(True)
                try:
                    sw.setChecked(bool(tweaks[tweak_id].enabled))
                except Exception:
                    pass
                sw.blockSignals(False)
        if hasattr(self, "_region_edit") and TweakID.EUEnabler in tweaks:
            code = tweaks[TweakID.EUEnabler].code
            if self._region_edit.text() != code:
                self._region_edit.setText(code)
        if hasattr(self, "_spoof_combo") and TweakID.SpoofModel in tweaks:
            sel = tweaks[TweakID.SpoofModel].get_selected_option()
            try:
                dropdown_index = self._spoof_map.index(sel)
            except ValueError:
                dropdown_index = 0
            self._spoof_combo.setCurrentIndex(dropdown_index)
