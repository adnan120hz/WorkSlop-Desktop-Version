"""Risky section (iOS style).

Tweak logic is ported verbatim from leminlimez/Nugget's risky page
(src/gui/pages/tools/risky.py); this file only renders it in the
WorkSlop iOS interface. All checkbox/text handlers mirror Nugget's
``on_*`` handlers 1:1.

One adaptation: Nugget marks these tweaks ``is_risky=True`` and gates them
behind a ``risky_allowed`` apply flag. This fork's tweak classes have no
risky gating (GoldenNugget removed it), so the tweaks apply like any other
enabled tweak. The section header carries Nugget's warning instead.
"""
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QSizePolicy,
)

from src.gui.ios.components import (
    IOSSectionHeader, IOSCard, IOSSwitch,
)
from src.gui.theme import ColorThemeManager
from src.tweaks.tweaks import tweaks, TweakID
from src.tweaks.tweak_loader import load_risky


def tr(s: str) -> str:
    return QCoreApplication.translate("Nugget", s)


class RiskySection(QWidget):
    """Nugget's risky page as an embeddable section widget."""

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
        load_risky()
        self._build_ui()
        self._apply_gating()
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

    def _add_switch(self, title: str, tweak_id, on_toggled=None):
        card, lay = self._row_card()
        lbl = QLabel(tr(title))
        lbl.setStyleSheet("font-size: 15px; background-color: transparent;")
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)
        sw = IOSSwitch()
        sw.toggled.connect(lambda checked: on_toggled(checked))
        lay.addWidget(self._make_switch_column(card, sw))
        self._layout.addWidget(card)
        self._switches[tweak_id] = sw
        return sw

    # Single-source gating (user audit 2026-10-03): Risky rows consult the
    # SAME deliverability decision as the Tweaks page and the backend, so
    # CustomResolution can no longer be toggled where the shared decision
    # forbids it (wrong device / locked capability), and the reason is
    # shown on the row instead of failing silently at apply.
    def _device_context(self):
        device = None
        try:
            device = self.window.device_manager.data_singleton.current_device
        except Exception:
            device = None
        if device is None:
            return "", "", True
        return (getattr(device, "version", "") or "",
                getattr(device, "build", "") or "",
                "iPad" not in str(getattr(device, "model", "") or ""))

    def _apply_gating(self):
        from src.tweaks.capabilities import tweak_deliverability
        version, build, is_iphone = self._device_context()
        for tweak_id, sw in list(self._switches.items()):
            deliverable, _code, message = tweak_deliverability(
                tweak_id, device_version=version, device_build=build,
                is_iphone=is_iphone)
            sw.setEnabled(bool(deliverable))
            tip = "" if deliverable else (
                tr("Locked: ") + str(message or "Not supported on this device."))
            sw.setToolTip(tip)
            if not deliverable and tweak_id in tweaks:
                # Defense in depth: a locked tweak must not stay enabled
                # from a preset / previous device.
                try:
                    tweaks[tweak_id].set_enabled(False)
                except Exception:
                    pass
                self._sync_switch(tweak_id)

    def _sync_switch(self, tweak_id):
        if tweak_id in tweaks and tweak_id in self._switches:
            try:
                self._switches[tweak_id].setChecked(bool(tweaks[tweak_id].enabled))
            except Exception:
                pass

    def _lineedit_style(self):
        return (
            "QLineEdit { background-color: rgba(255,255,255,0.08);"
            " border: 1px solid rgba(255,255,255,0.15); border-radius: 12px;"
            " padding: 8px 12px; font-size: 14px; color: white; }"
        )

    def _warning_label(self):
        # Nugget's resHeightWarningLbl/resWidthWarningLbl: a red-bordered
        # empty label shown when the input is not a valid integer.
        lbl = QLabel("")
        lbl.setFixedSize(22, 22)
        lbl.setStyleSheet(
            "QLabel { border: 2px solid red; border-radius: 11px; "
            "color: red; background-color: transparent; }")
        lbl.hide()
        return lbl

    def _build_ui(self):
        if self._built:
            return
        self._built = True

        self._layout.addWidget(IOSSectionHeader(tr("Risky")))
        warn = QLabel(tr(
            "WARNING: risky, use with caution. A bad value here can "
            "bootloop the device."))
        warn.setWordWrap(True)
        c = ColorThemeManager.instance().colors
        warn.setStyleSheet(
            f"font-size: 13px; color: {c.danger_text}; background-color: transparent;")
        self._layout.addWidget(warn)

        # Disable OTA Updates (file) (Nugget: disableOTAChk)
        self._add_switch("Disable OTA Updates (file)", TweakID.DisableOTAFile,
                         on_toggled=self.on_disableOTAChk_clicked)

        # Set a Custom Device Resolution (Nugget: enableResolutionChk)
        self._add_switch(
            "Set a Custom Device Resolution", TweakID.CustomResolution,
            on_toggled=self.on_enableResolutionChk_clicked)

        # Resolution height/width (Nugget: resChangerContent)
        self._res_card, res_lay = self._row_card()
        res_inner = QVBoxLayout()
        res_inner.setSpacing(8)
        res_lay.addLayout(res_inner)

        h_row = QHBoxLayout()
        h_lbl = QLabel(tr("Resolution Height"))
        h_lbl.setStyleSheet("font-size: 15px; background-color: transparent;")
        h_row.addWidget(h_lbl, 1)
        self._res_height_edit = QLineEdit()
        self._res_height_edit.setPlaceholderText(tr("e.g. 2556"))
        self._res_height_edit.setStyleSheet(self._lineedit_style())
        self._res_height_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._res_height_edit.textEdited.connect(self.on_resHeightTxt_textEdited)
        h_row.addWidget(self._res_height_edit, 2)
        self._res_height_warn = self._warning_label()
        h_row.addWidget(self._res_height_warn)
        res_inner.addLayout(h_row)

        w_row = QHBoxLayout()
        w_lbl = QLabel(tr("Resolution Width"))
        w_lbl.setStyleSheet("font-size: 15px; background-color: transparent;")
        w_row.addWidget(w_lbl, 1)
        self._res_width_edit = QLineEdit()
        self._res_width_edit.setPlaceholderText(tr("e.g. 1179"))
        self._res_width_edit.setStyleSheet(self._lineedit_style())
        self._res_width_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._res_width_edit.textEdited.connect(self.on_resWidthTxt_textEdited)
        w_row.addWidget(self._res_width_edit, 2)
        self._res_width_warn = self._warning_label()
        w_row.addWidget(self._res_width_warn)
        res_inner.addLayout(w_row)

        self._layout.addWidget(self._res_card)

    def _sync_controls(self):
        for tweak_id in self._switches:
            self._sync_switch(tweak_id)
        # Nugget: resChangerContent hidden unless the resolution tweak is on
        if hasattr(self, "_res_card") and TweakID.CustomResolution in tweaks:
            self._res_card.setVisible(bool(tweaks[TweakID.CustomResolution].enabled))

    # -- handlers (mirror Nugget's risky.py on_* 1:1) -----------------------
    def on_disableOTAChk_clicked(self, checked: bool):
        if TweakID.DisableOTAFile in tweaks:
            tweaks[TweakID.DisableOTAFile].set_enabled(checked)
        self._sync_switch(TweakID.DisableOTAFile)

    def on_enableResolutionChk_clicked(self, checked: bool):
        if TweakID.CustomResolution in tweaks:
            tweaks[TweakID.CustomResolution].set_enabled(checked)
        self._sync_switch(TweakID.CustomResolution)
        # toggle the ui content
        if hasattr(self, "_res_card"):
            if checked:
                self._res_card.show()
            else:
                self._res_card.hide()

    def on_resHeightTxt_textEdited(self, txt: str):
        if TweakID.CustomResolution not in tweaks:
            return
        if txt == "":
            # remove the canvas_height value
            tweaks[TweakID.CustomResolution].value.pop("canvas_height", None)
            self._res_height_warn.hide()
            return
        try:
            val = int(txt)
            tweaks[TweakID.CustomResolution].value["canvas_height"] = val
            self._res_height_warn.hide()
        except Exception:
            self._res_height_warn.show()

    def on_resWidthTxt_textEdited(self, txt: str):
        if TweakID.CustomResolution not in tweaks:
            return
        if txt == "":
            # remove the canvas_width value
            tweaks[TweakID.CustomResolution].value.pop("canvas_width", None)
            self._res_width_warn.hide()
            return
        try:
            val = int(txt)
            tweaks[TweakID.CustomResolution].value["canvas_width"] = val
            self._res_width_warn.hide()
        except Exception:
            self._res_width_warn.show()
