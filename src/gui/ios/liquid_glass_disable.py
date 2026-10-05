"""Liquid Glass Disable (Beta 1) — dedicated iOS-style page.

The two route switches are ordinary registry specs (Section
"Liquid Glass Disable (Beta 1)", TweakID.LGDisableG1/LGDisableG2) rendered
by the shared IOSSectionContent, so they enable, autosave, count in the
pre-apply summary and stage through the normal apply pipeline exactly like
every other tweak. This page adds what a generic switch row cannot: the
honest Beta 1 explanation, the per-device "original saved" status, and the
two rollback buttons (G2: empty managed overlay; G1: write back the device
original saved before the first apply).
"""

from PySide6.QtCore import Qt, QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMessageBox,
)

from src.devicemanagement.session import install_windows_selector_policy
from src.gui.ios.components import (
    IOSCard, IOSDangerButton, IOSPrimaryButton, IOSSectionHeader,
)
from src.gui.ios.tweaks import IOSSectionPage
from src.gui.theme import ColorThemeManager
from src.tweaks import lg_disable
from src.tweaks.registry import Section
from src.tweaks.tweak_names import TweakID

_NUGGET = "Nugget"


def _tr(text: str) -> str:
    return QCoreApplication.translate(_NUGGET, text)


class LGDRollbackThread(QThread):
    """Background runner for one Beta 1 rollback (device restore)."""

    progress = Signal(str)
    alert = Signal(object)
    finished_with_result = Signal(bool, str)

    def __init__(self, manager, which: str, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.which = which
        self._final_alert = None

    def _collect_alert(self, msg):
        self._final_alert = msg
        if msg is not None:
            self.alert.emit(msg)

    def run(self):
        install_windows_selector_policy()
        try:
            self.manager.lgd_rollback(
                self.which, self.progress.emit, self._collect_alert)
            msg = self._final_alert
            ok = (msg is not None
                  and getattr(msg, "icon", None) == QMessageBox.Information)
            err = "" if ok else (getattr(msg, "txt", "")
                                 or "Rollback did not complete.")
            self.finished_with_result.emit(ok, err)
        except Exception as e:  # defensive: never die silently on a thread
            self.finished_with_result.emit(False, f"{type(e).__name__}: {e}")


class IOSLiquidGlassDisablePage(IOSSectionPage):
    """Section page for Liquid Glass Disable (Beta 1) + rollback controls."""

    PAGE_INDEX = 16  # appended last in MainWindow.ios_pages; never renumber

    def __init__(self, window, parent=None):
        super().__init__(window, Section.LIQUID_GLASS_DISABLE, parent)
        self._rollback_thread = None
        self._focused_route = None

        layout = self.layout()

        # --- honest Beta 1 explanation (top, always visible) ---
        intro_card = IOSCard(self)
        intro_layout = QVBoxLayout(intro_card)
        intro_layout.setContentsMargins(16, 12, 16, 12)
        intro_layout.setSpacing(6)
        intro = QLabel(_tr(
            "BETA 1 — unproven. This page writes one research candidate "
            "key, SolariumForceFallback = true, through two delivery "
            "routes. The key string exists in the iOS 26.6.1 system "
            "binaries, but it is NOT proven that iOS 26.6.1 reads it from "
            "either file — enabling a route does not claim to disable "
            "Liquid Glass. Test one route at a time: full backup first, "
            "Low Power Mode off, reboot after applying, then judge the "
            "result. Every apply is checked by an automatic verification "
            "gate (payload parses, value is a real bool, G1 keeps 100% of "
            "your original keys) and is cancelled if the check fails. "
            "On iOS 26.6.1 (builds 23G82 and 23G83), Apply delivers "
            "these routes through a full device backup and restore "
            "instead of a partial restore, because the partial route "
            "showed no effect in beta testing; the same checks run "
            "first, an encrypted backup is refused, and any failure "
            "cancels the apply before your device is changed."))
        intro.setWordWrap(True)
        c = ColorThemeManager.instance().colors
        intro.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 13px;"
            " background-color: transparent;")
        intro_layout.addWidget(intro)
        self._intro_label = intro
        intro_wrap = QWidget(self)
        intro_wrap_layout = QVBoxLayout(intro_wrap)
        intro_wrap_layout.setContentsMargins(16, 16, 16, 0)
        intro_wrap_layout.setSpacing(0)
        intro_wrap_layout.addWidget(intro_card)
        layout.insertWidget(0, intro_wrap)

        # --- rollback + status (bottom, survives section rebuilds) ---
        footer = QWidget(self)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(16, 8, 16, 16)
        footer_layout.setSpacing(8)

        footer_layout.addWidget(IOSSectionHeader(_tr("Rollback")))

        self._status_label = QLabel("", footer)
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 13px;"
            " background-color: transparent;")
        footer_layout.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._g2_btn = IOSDangerButton(
            _tr("Roll Back G2 (Empty Overlay)"), footer)
        self._g2_btn.clicked.connect(lambda: self._confirm_rollback("g2"))
        btn_row.addWidget(self._g2_btn)
        self._g1_btn = IOSDangerButton(
            _tr("Roll Back G1 (Restore Saved Original)"), footer)
        self._g1_btn.clicked.connect(lambda: self._confirm_rollback("g1"))
        btn_row.addWidget(self._g1_btn)
        footer_layout.addLayout(btn_row)

        hint = QLabel(_tr(
            "Enable a route above, then press Apply Tweaks on the Apply "
            "page. The rollback buttons write to the device immediately "
            "(G2 restores an empty managed overlay; G1 writes back the "
            "original .GlobalPreferences.plist saved before your first "
            "G1 apply)."))
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 13px;"
            " background-color: transparent;")
        footer_layout.addWidget(hint)
        self._hint_label = hint

        self._apply_btn = IOSPrimaryButton(_tr("Open Apply Page"), footer)
        self._apply_btn.clicked.connect(lambda: self.window.show_ios_page(6))
        footer_layout.addWidget(self._apply_btn)

        layout.addWidget(footer)
        self.refresh()

    # -- status ----------------------------------------------------------
    def refresh(self):
        """Re-read device + saved-original state (called on navigation)."""
        dm = getattr(self.window, "device_manager", None)
        udid = ""
        name = ""
        try:
            udid = dm.get_current_device_udid() or ""
            name = dm.get_current_device_name() or ""
        except Exception:
            udid = ""
        if not udid:
            self._status_label.setText(_tr(
                "No device connected. Connect your iPhone to apply or "
                "roll back."))
            return
        meta = lg_disable.load_original_meta(udid)
        device_line = name or udid
        if meta:
            self._status_label.setText(_tr(
                "Device: %1. A pristine original .GlobalPreferences.plist "
                "is saved for rollback (captured %2, iOS %3, %4 keys).")
                .replace("%1", device_line)
                .replace("%2", str(meta.get("saved_at", "unknown")))
                .replace("%3", str(meta.get("ios_version", "unknown")))
                .replace("%4", str(meta.get("key_count", "?"))))
        else:
            self._status_label.setText(_tr(
                "Device: %1. No saved original yet — it is captured "
                "automatically before your first G1 apply.").replace(
                    "%1", device_line))

    # -- Home tile route focus -------------------------------------------
    def focus_route(self, route: str):
        """Mark which route the user came for, without enabling anything.

        Expands the route section, scrolls its card into view and gives
        the switch keyboard focus. This NEVER toggles a tweak: the user
        still makes the explicit switch decision on this page.
        """
        route = str(route or "").strip().lower()
        routes = {
            "g2": TweakID.LGDisableG2,
            "g1": TweakID.LGDisableG1,
        }
        tweak_id = routes.get(route)
        if tweak_id is None:
            self._focused_route = None
            return
        self._focused_route = route
        content = getattr(self, "content", None)
        if content is None:
            return
        collapsibles = getattr(content, "_section_collapsibles", {})
        collapsible = collapsibles.get(Section.LIQUID_GLASS_DISABLE)
        if collapsible is not None:
            try:
                collapsible.set_expanded(True)
            except Exception:
                pass
        cards = getattr(content, "_switch_cards", {})
        card = cards.get(tweak_id)
        if card is not None:
            try:
                self._scroll.ensureWidgetVisible(card)
            except Exception:
                pass
        switches = getattr(content, "_switches", {})
        switch = switches.get(tweak_id)
        if switch is not None:
            try:
                if switch.isEnabled():
                    switch.setFocus(Qt.FocusReason.OtherFocusReason)
            except Exception:
                pass

    # -- rollback ----------------------------------------------------------
    def _confirm_rollback(self, which: str):
        if getattr(self.window, "apply_in_progress", False):
            QMessageBox.information(
                self, _tr("Liquid Glass Disable (Beta 1)"),
                _tr("An apply or reset is already running. Wait for it "
                    "to finish first."))
            return
        if self._rollback_thread is not None and self._rollback_thread.isRunning():
            return
        udid = ""
        try:
            udid = self.window.device_manager.get_current_device_udid() or ""
        except Exception:
            udid = ""
        if not udid:
            QMessageBox.warning(
                self, _tr("Liquid Glass Disable (Beta 1)"),
                _tr("No device connected. Connect your iPhone first."))
            return
        if which == "g2":
            text = _tr(
                "Restore an empty managed .GlobalPreferences.plist "
                "overlay? This removes the SolariumForceFallback key "
                "(other WorkSlop GlobalPreferences tweaks re-apply on "
                "your next Apply). The device reboots if auto-reboot is "
                "on.")
        else:
            meta = lg_disable.load_original_meta(udid)
            if not meta:
                QMessageBox.warning(
                    self, _tr("Liquid Glass Disable (Beta 1)"),
                    _tr("No saved original .GlobalPreferences.plist for "
                        "this device yet, so there is nothing safe to "
                        "roll back to. The original is saved automatically "
                        "before your first G1 apply."))
                return
            text = _tr(
                "Write back the saved original .GlobalPreferences.plist "
                "(captured %1, iOS %2)? This replaces the device's "
                "current file with that exact copy. The device reboots "
                "if auto-reboot is on.").replace(
                    "%1", str(meta.get("saved_at", "unknown"))).replace(
                    "%2", str(meta.get("ios_version", "unknown")))
        reply = QMessageBox.question(
            self, _tr("Liquid Glass Disable (Beta 1)"), text,
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.StandardButton.Cancel)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._set_rollback_busy(True)
        thread = LGDRollbackThread(self.window.device_manager, which, self)
        self._rollback_thread = thread
        thread.progress.connect(self.window.update_label)
        thread.alert.connect(self.window.alert_message)
        thread.finished_with_result.connect(self._on_rollback_done)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_rollback_done(self, ok: bool, _err: str):
        self._set_rollback_busy(False)
        # The rollback turned the route's switch off in the model; rebuild
        # so the switch visuals match, and refresh the saved-original line.
        try:
            self.rebuild()
        except Exception:
            pass
        self.refresh()

    def _set_rollback_busy(self, busy: bool):
        self._g2_btn.setEnabled(not busy)
        self._g1_btn.setEnabled(not busy)
        self._apply_btn.setEnabled(not busy)

    def _retheme(self):
        super()._retheme()
        c = ColorThemeManager.instance().colors
        # During super().__init__ _retheme runs before these labels exist.
        for lbl in (getattr(self, "_intro_label", None),
                    getattr(self, "_status_label", None),
                    getattr(self, "_hint_label", None)):
            if lbl is not None:
                lbl.setStyleSheet(
                    f"color: {c.text_secondary}; font-size: 13px;"
                    " background-color: transparent;")
