"""Liquid Glass Disable — dedicated iOS-style page.

The switches are ordinary registry specs (Section
"Liquid Glass Disable (Beta 1)": the Squair Protocol test payload and
Liquid Glass (Latest)) rendered by the shared IOSSectionContent, so they
enable, autosave, count in the pre-apply summary and stage through the
normal apply pipeline exactly like every other tweak. This page adds
what a generic switch row cannot: the honest explanation, the device
status line, and the rollback buttons (each removes exactly its own
payload's keys from a fresh device capture). The Beta 1 G1/G2 routes
left the product in v14.0 (user order 2026-10-07).
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
            "UNPROVEN on screen. This page writes Apple's real firmware "
            "keys through the full-backup route: Liquid Glass (Latest) "
            "puts SolariumForceFallback = true into your device's "
            "com.apple.SwiftUI.plist (its reader is verified alive in "
            "the iOS 26.6.1 firmware), plus the two lock-screen keys "
            "into .GlobalPreferences.plist and the specular key into "
            "com.apple.springboard.plist; the Lock Screen Keys (Test) "
            "entry is a test-only experiment. Nothing on this page claims the "
            "glass look is disabled — judge it with an isolated device "
            "test: full backup first, Low Power Mode off, reboot after "
            "applying. Every apply is checked by an automatic "
            "verification gate (payload parses, value is a real bool, "
            "and 100% of your existing keys must survive) and is "
            "cancelled if the check fails. "
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
        self._squair_btn = IOSDangerButton(
            _tr("Roll Back Lock-Screen Keys (Remove Its 2 Keys)"), footer)
        self._squair_btn.clicked.connect(
            lambda: self._confirm_rollback("squair"))
        btn_row.addWidget(self._squair_btn)
        self._latest_btn = IOSDangerButton(
            _tr("Roll Back Latest (Remove Its 4 Keys)"), footer)
        self._latest_btn.clicked.connect(
            lambda: self._confirm_rollback("latest"))
        btn_row.addWidget(self._latest_btn)
        footer_layout.addLayout(btn_row)

        hint = QLabel(_tr(
            "Enable a payload above, then press Apply Tweaks on the "
            "Apply page. The rollback buttons write to the device "
            "immediately: each reads your device's current files and "
            "removes only that payload's own keys — your other settings "
            "stay."))
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
    def _device_gate_state(self):
        """(udid, name, version, build, applicable) for the S8 route.

        ``applicable`` is the backend's exact window (a connected device
        on iOS 26.6.1 build 23G82 or 23G83); the switch lock itself is
        applied where the switches are built (src.gui.ios.tweaks).
        """
        dm = getattr(self.window, "device_manager", None)
        udid = name = version = build = ""
        try:
            udid = dm.get_current_device_udid() or ""
            name = dm.get_current_device_name() or ""
            version = dm.get_current_device_version() or ""
            build = dm.get_current_device_build() or ""
        except Exception:
            udid = ""
        applicable = False
        if udid:
            try:
                from src.restore.lgd_full import lgd_full_route_applicable
                applicable = lgd_full_route_applicable(version, build)
            except Exception:
                applicable = False
        return udid, name, version, build, applicable

    def refresh(self):
        """Re-read device + saved-original state (called on navigation)."""
        udid, name, version, build, applicable = self._device_gate_state()
        if not udid:
            self._status_label.setText(_tr(
                "No device connected. Connect your iPhone to apply or "
                "roll back. The switches above stay locked: this S8 "
                "route is a full backup (all data) for iOS 26.6.1 "
                "builds 23G82 and 23G83 only — separate from Partial "
                "Restore (up to iOS 26) and the iOS 27 Full Backup "
                "route."))
            return
        if not applicable:
            self._status_label.setText(_tr(
                "Device: %1 (iOS %2, build %3). The switches above are "
                "locked: this S8 route is a full backup (all data) and "
                "runs only on iOS 26.6.1 builds 23G82 and 23G83 — "
                "separate from Partial Restore (up to iOS 26) and the "
                "iOS 27 Full Backup route. Rollback reads your device's "
                "current files and removes only each payload's own "
                "keys.").replace("%1", name or udid).replace(
                    "%2", version or "?").replace("%3", build or "?"))
            return
        self._status_label.setText(_tr(
            "Device: %1 (iOS %2, build %3). This build can run the "
            "S8 full backup (all data) route. Rollback reads your "
            "device's current files and removes only each payload's "
            "own keys.").replace("%1", name or udid).replace(
                "%2", version or "?").replace("%3", build or "?"))

    def rebuild(self):
        # Device changes rebuild the switches (the S8 gate is evaluated
        # at build time); refresh the status line to match the new gate.
        super().rebuild()
        if getattr(self, "_status_label", None) is not None:
            self.refresh()

    # -- Home tile route focus -------------------------------------------
    def focus_route(self, route: str):
        """Mark which route the user came for, without enabling anything.

        Expands the route section, scrolls its card into view and gives
        the switch keyboard focus. This NEVER toggles a tweak: the user
        still makes the explicit switch decision on this page.
        """
        route = str(route or "").strip().lower()
        routes = {
            "latest": TweakID.LGDisableLatest,
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
        if which == "latest":
            text = _tr(
                "Remove the four Liquid Glass (Latest) keys? Your "
                "device's three preference files are read fresh and only "
                "SolariumForceFallback (com.apple.SwiftUI.plist), "
                "SBDisallowGlassTime and SBDisallowGlassButtons "
                "(.GlobalPreferences.plist) and "
                "SBDisableSpecularEverywhereUsingLSSAssertion "
                "(com.apple.springboard.plist) are removed — your other "
                "settings stay. The device reboots if auto-reboot is "
                "on.")
        elif which == "squair":
            text = _tr(
                "Remove the two Lock Screen Keys (Test) keys? The "
                "device's .GlobalPreferences.plist is read fresh and "
                "only SBDisallowGlassTime and SBDisallowGlassButtons "
                "are removed — your other settings stay. The "
                "FeatureFlags/Domain/SpringBoard.plist file, if it "
                "landed on the device, cannot be removed by a restore "
                "and is left in place. The device reboots if "
                "auto-reboot is on.")
        else:
            return
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

    def _on_rollback_done(self, ok: bool, err: str):
        self._set_rollback_busy(False)
        if not ok:
            # A failed rollback must reach the user; swallowing the
            # error made a failed restore look like success (round 21).
            QMessageBox.warning(
                self, _tr("Liquid Glass Disable (Beta 1)"),
                _tr("The rollback did not complete: %1").replace(
                    "%1", err or _tr("unknown error")))
        # The rollback turned the route's switch off in the model; rebuild
        # so the switch visuals match, and refresh the saved-original line.
        try:
            self.rebuild()
        except Exception:
            pass
        self.refresh()

    def _set_rollback_busy(self, busy: bool):
        self._squair_btn.setEnabled(not busy)
        self._latest_btn.setEnabled(not busy)
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
