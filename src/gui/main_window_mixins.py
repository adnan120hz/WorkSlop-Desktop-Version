"""Mixins for :class:`MainWindow`, breaking the monolithic GUI shell into
focused pieces: device-bar handling, settings/presets/theme, navigation and
the apply/reset flow. Each mixin only reaches ``self`` attributes that
``MainWindow.__init__`` installs, so they stay plain objects mixed into
``class MainWindow(QtWidgets.QMainWindow, DeviceBarMixin, SettingsMixin,
NavigationMixin, ApplyMixin)``.
"""

from typing import Optional
import os

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QCoreApplication

from src.controllers.video_handler import set_ignore_frame_limit
from src.devicemanagement.constants import (
    Version, is_ios27_build, mobilegestalt_decision,
)
from src.tweaks.capabilities import clear_unsupported_mobilegestalt_state
from src.gui.dialogs import AboutProgramDialog
from src.gui.dialogs.reset_dialog import ResetDialog
from src.gui.logger import get_logger
from src.gui.theme import ColorThemeManager
from src.gui.thread_workers.apply_worker import (
    ApplyAlertMessage,
    ApplyThread,
    RefreshDevicesThread,
    get_sudo_pwd,
    set_sudo_pwd,
)
from src.gui.version import App_Build, App_Version
from src.gui.ios.theme_manager import ThemeManager
from src.gui.ios.tweaks import _hidden_feature_names
from src.gui.pages.pages_list import Page
from src.tweaks.tweak_classes import set_tweak_change_callback
from src.tweaks.tweaks import tweaks, TweakID


class DeviceBarMixin:
    """Device refresh, selection and per-device interface updates."""

    def updateInterfaceForNewDevice(self):
        # update the home page
        self.pages[Page.Home].updatePhoneInfo()

        # Rebuild the tweak sections for the newly selected device: the pages
        # are constructed at startup before any device is known, so per-device
        # compatibility filtering (min_version / iphone_only / ipad_only) is
        # only correct when re-evaluated against the real connected device.
        for page in ("ios_tweaks", "ios_springboard", "ios_internal", "ios_liquidglass", "ios_lgd"):
            section_page = getattr(self, page, None)
            if section_page is not None:
                try:
                    section_page.rebuild()
                except Exception:
                    pass


    def _apply_hidden_feature_gating(self):
        """Hide the Sidebar buttons and iOS home cards for HotLoad-hidden
        features on this device. Kept central so the gating survives every
        re-apply point (device refresh / selection).

        Only ever HIDES — it never re-shows a button that HotLoad hid. The
        Status Bar page used to be force-hidden on iOS 27 because the Speakeasy
        feature flag could not be written; it now delivers the carrier name
        through StatusBarOverrides.archive, so the page stays reachable there
        (trimmed down to the carrier rows by the page itself).
        """
        hidden = _hidden_feature_names()
        if hidden:
            print(f"[HotLoad] Hiding feature pages: {', '.join(sorted(hidden))}")
        statusbar_hidden = "Status Bar" in hidden
        # Sidebar (classic shell) buttons
        btn_map = {
            "Liquid Glass": self.ui.liquidGlassPageBtn,
            "Springboard": self.ui.springboardOptionsPageBtn,
            "Internal": self.ui.internalOptionsPageBtn,
            "PosterBoard": self.ui.posterboardPageBtn,
            "Daemons": self.ui.daemonsPageBtn,
        }
        for feat, btn in btn_map.items():
            btn.setVisible(feat not in hidden)
        self.ui.statusBarPageBtn.setVisible(not statusbar_hidden)
        # iOS home cards
        card_map = {
            "PosterBoard": self.ios_home.posterboard_card,
            "Daemons": self.ios_home.daemons_card,
        }
        for feat, card in card_map.items():
            card.setVisible(feat not in hidden)
        self.ios_home.set_statusbar_visible(not statusbar_hidden)


    @QtCore.Slot()
    def refresh_devices(self):
        # Refresh must ALWAYS re-run enumeration (user report 2026-10-03:
        # "Refresh doesn't work"). The old guard silently swallowed clicks
        # forever when a previous thread died without emitting finished
        # (flag stuck True). Self-heal: a dead/not-running thread no longer
        # counts as "in progress".
        existing = getattr(self, "refresh_worker_thread", None)
        if getattr(self, "refresh_in_progress", False):
            alive = False
            try:
                alive = existing is not None and existing.isRunning()
            except Exception:
                alive = False
            if alive:
                return  # a scan is genuinely running; ignore the click
            self.refresh_in_progress = False  # stale flag from a dead thread
            self.refresh_worker_thread = None
        self.refresh_in_progress = True
        try:
            self.ui.refreshBtn.setDisabled(True)
        except Exception:
            pass
        # Visual feedback: searching state on the footer + device panel.
        if hasattr(self, "footer_status_lbl"):
            try:
                self.footer_status_lbl.setText(
                    self.tr("Searching for devices…"))
            except Exception:
                pass
        if hasattr(self, "device_panel"):
            try:
                self.device_panel.set_searching(True)
            except Exception:
                pass
        self.refresh_worker_thread = RefreshDevicesThread(manager=self.device_manager, settings=self.settings)
        self.refresh_worker_thread.alert.connect(self.alert_message)
        self.refresh_worker_thread.device_found.connect(self._on_device_found_partial)
        self.refresh_worker_thread.finished.connect(self.refresh_devices_finished)
        self.refresh_worker_thread.finished.connect(self.refresh_worker_thread.deleteLater)
        self.refresh_worker_thread.start()
        # Safety net: if the worker ever hangs past the manager's own 60s
        # enumeration ceiling, release the UI instead of wedging Refresh.
        QtCore.QTimer.singleShot(75_000, self._refresh_watchdog)

    def _refresh_watchdog(self):
        """Release a wedged refresh (thread alive past every timeout)."""
        thread = getattr(self, "refresh_worker_thread", None)
        if not getattr(self, "refresh_in_progress", False):
            return
        try:
            alive = thread is not None and thread.isRunning()
        except Exception:
            alive = False
        if alive:
            import logging
            logging.getLogger("WorkSlop.refresh").error(
                "refresh watchdog: worker still running after 75s; "
                "releasing the refresh lock (thread left to finish)")
            # Do not kill the thread (unsafe); just unlock the UI. Its
            # finished signal will still refresh the UI when it lands.
            self.refresh_in_progress = False
            if hasattr(self, "device_panel"):
                try:
                    self.device_panel.set_searching(False)
                except Exception:
                    pass

    @QtCore.Slot()
    def _on_device_found_partial(self):
        """A device was appended mid-scan: show it right away (the full
        finished handler still runs at the end for the final state)."""
        try:
            self.ios_home.refresh_device_combo()
            self.ios_home.update_device_info()
            self.ios_home.update_status()
        except Exception:
            pass
        if hasattr(self, "device_panel"):
            try:
                self.device_panel.refresh_devices()
            except Exception:
                pass
        if hasattr(self, "footer_status_lbl"):
            try:
                self.footer_status_lbl.setText(self.tr("Device found…"))
            except Exception:
                pass


    def warn_for_dev_beta(self):
        """Warn once per app session per device on developer-beta iOS.

        Trigger set is unchanged: iOS > 26.0 whose build string ends in a
        letter (a beta build). Two fixes vs the inherited version:

        * The text names the detected major version (an iOS 27 device no
          longer reads "iOS 26 beta" -- the old string was inherited
          verbatim and never updated).
        * The box is deferred until the device-switch flow has finished
          and is shown NON-modally, at most once per session per device.
          The old modal ``QMessageBox.exec()`` inside
          ``change_selected_device`` could kill the app outright on
          Linux/Wayland compositors (v11.0.1 user report, 2026-10-03:
          "The Wayland connection broke") and it re-appeared on every
          device switch.
        """
        ver = self.device_manager.get_current_device_version()
        if ver == "":
            return
        try:
            parsed = Version(ver)
        except Exception:
            return
        build = self.device_manager.get_current_device_build() or ""
        if not (parsed > Version("26.0") and build
                and not build[-1].isdigit()):
            return
        warned = getattr(self, "_beta_warned_devices", None)
        if warned is None:
            warned = self._beta_warned_devices = set()
        device_key = self.device_manager.get_current_device_udid() or build
        if device_key in warned:
            return
        warned.add(device_key)
        txt = self.tr(
            "Warning: You are on iOS %1 beta.\n\n"
            "This has been known to cause problems and potentially lead "
            "to bootloops.\n\nUse at your own risk!").replace(
                "%1", str(parsed.major))
        # Defer until the device-switch flow has fully finished; never
        # run a modal loop from inside it.
        QtCore.QTimer.singleShot(0, lambda: self._show_dev_beta_warning(txt))

    def _show_dev_beta_warning(self, txt):
        """Show the developer-beta warning non-modally (see above)."""
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle(self.tr("Warning"))
        box.setText(txt)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.setModal(False)
        box.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        # Keep a reference: the box is modeless, so it must not be
        # garbage-collected while it is on screen.
        self._dev_beta_warning_box = box
        box.show()


    def refresh_devices_finished(self):
        self.refresh_in_progress = False
        # The thread's own ``finished -> deleteLater`` already freed the C++
        # object; drop our reference so closeEvent never probes a dead wrapper.
        try:
            self.refresh_worker_thread = None
        except Exception:
            pass
        self.toggle_thread_btns(disabled=False)
        # clear the picker
        self.ui.devicePicker.clear()

        if len(self.device_manager.devices) == 0:
            self.ui.devicePicker.setEnabled(False)
            self.ui.devicePicker.addItem(self.noneText)
            self.show_home()

            # hide all pages
            self.ui.sidebarDiv1.hide()

            self.ui.gestaltPageBtn.hide()
            self.ui.statusBarPageBtn.hide()
            self.ui.springboardOptionsPageBtn.hide()
            self.ui.internalOptionsPageBtn.hide()
            self.ui.liquidGlassPageBtn.hide()
            self.ui.daemonsPageBtn.hide()
            self.ui.iconThemesPageBtn.hide()
            self.ui.passcodePageBtn.hide()
            self.ui.posterboardPageBtn.hide()

            self.ui.sidebarDiv2.hide()
            self.ui.applyPageBtn.hide()
            _backup_btn = getattr(self.ui, "backupPageBtn", None)
            if _backup_btn is not None:
                _backup_btn.hide()
            self.ui.jjtechBtn.hide()
            self.ui.duyBtn.show()

            # mirror in the iOS UI: no device → no status bar card
            if hasattr(self, "ios_home"):
                self.ios_home.set_statusbar_visible(False)
                self.ios_home.set_mobilegestalt_visible(False)
        else:
            self.ui.devicePicker.setEnabled(True)
            # populate the ComboBox with device names
            for device in self.device_manager.devices:
                tag = " (@ USB)" if device.connected_via_usb else " (@ WiFi)"
                self.ui.devicePicker.addItem(f"{device.name}{tag}")

            # show all pages
            self.ui.sidebarDiv1.show()
            self.ui.statusBarPageBtn.show()
            self.ui.springboardOptionsPageBtn.show()
            self.ui.internalOptionsPageBtn.show()
            self.ui.liquidGlassPageBtn.show()
            self.ui.daemonsPageBtn.show()
            self.ui.iconThemesPageBtn.show()
            self.ui.gestaltPageBtn.show()
            self.ui.passcodePageBtn.hide()
            self.ui.posterboardPageBtn.show()

            self.ui.sidebarDiv2.show()
            self.ui.applyPageBtn.show()
            _backup_btn = getattr(self.ui, "backupPageBtn", None)
            if _backup_btn is not None:
                _backup_btn.show()

            # HotLoad-hidden features are carved out of the Sidebar and iOS home
            self._apply_hidden_feature_gating()
        
        # update the selected device
        self.ui.devicePicker.setCurrentIndex(0)
        # HotLoad-hidden features are carved out of the Sidebar and iOS home
        self._apply_hidden_feature_gating()
        # keep the iOS home in sync
        self.ios_home.refresh_device_combo()
        self.ios_home.update_device_info()
        self.ios_home.update_status()
        # keep the left device panel tree in sync too
        if hasattr(self, "device_panel"):
            try:
                self.device_panel.set_searching(False)
                self.device_panel.refresh_devices()
            except Exception:
                pass
        if hasattr(self, "footer_status_lbl"):
            try:
                count = len(self.device_manager.devices or [])
                self.footer_status_lbl.setText(
                    f"{count} device(s) connected" if count
                    else "No device connected")
            except Exception:
                pass
        # Honest no-device state: surface the detection diagnostic (cable /
        # Trust / driver) on Home instead of a bare "No Device".
        if not (self.device_manager.devices or []):
            notes = getattr(self.device_manager, "detection_notes", None) or []
            if notes and hasattr(self, "ios_home"):
                try:
                    self.ios_home.show_detection_guidance(notes[0])
                except Exception:
                    pass


    def change_selected_device(self, index):
        if len(self.device_manager.devices) > 0:
            self.device_manager.set_current_device(index=index)
            # hide sidebar buttons that are for newer versions
            MinTweakVersions = {
                "26.0": [self.ui.liquidGlassPageBtn],
            }

            device_ver = Version(self.device_manager.data_singleton.current_device.version)
            device_build = self.device_manager.data_singleton.current_device.build or ""
            # MobileGestalt menu stays visible but auto-locks on unsupported
            # builds: open on iOS 16.0 -> iOS 26.2 beta 1, locked after that.
            # One shared decision (exact build authoritative) drives Home, the
            # sidebar, Tweaks, Eligibility, presets, and the backend.
            gestalt_decision = mobilegestalt_decision(
                device_build, str(device_ver))
            gestalt_ok = gestalt_decision.supported
            if not gestalt_ok:
                cleared = clear_unsupported_mobilegestalt_state(gestalt_decision)
                if cleared:
                    get_logger("gui").info(
                        "MobileGestalt tweaks forced off for this device "
                        f"({gestalt_decision.reason_code}): {', '.join(cleared)}")
                    # Rewrite AutoSave so the cleared state is what a later
                    # restart restores, not the stale ON state.
                    try:
                        if self.autosave_enabled():
                            self._save_autosave_preset()
                    except Exception:
                        pass
            gestalt_tip_ok = "MobileGestalt (supports iOS 16.0 - 26.2 beta 1)"
            gestalt_tip_locked = (
                gestalt_decision.user_message +
                f" (this device build: {device_build or 'unknown'})")
            self.ui.gestaltPageBtn.setVisible(True)
            self.ui.gestaltPageBtn.setEnabled(gestalt_ok)
            self.ui.gestaltPageBtn.setToolTip(
                gestalt_tip_ok if gestalt_ok else gestalt_tip_locked)
            if hasattr(self, "ios_home"):
                self.ios_home.set_mobilegestalt_visible(True)
                self.ios_home.set_mobilegestalt_locked(
                    not gestalt_ok,
                    self.device_manager.data_singleton.current_device.version)
            if hasattr(self, "workslop_sidebar"):
                self.workslop_sidebar.set_gestalt_locked(
                    not gestalt_ok,
                    gestalt_tip_ok if gestalt_ok else gestalt_tip_locked)
            # Status Bar menu: locked on any iOS 27 build, open on iOS 26
            # and below. It stays visible (like MobileGestalt) so the user
            # sees why it is unavailable.
            statusbar_locked = is_ios27_build(device_build)
            statusbar_tip = (
                "Status Bar"
                if not statusbar_locked else
                "Status Bar is locked on iOS 27 "
                f"(this device: {device_build}). It is open on iOS 26 and below."
            )
            self.ui.statusBarPageBtn.setEnabled(not statusbar_locked)
            self.ui.statusBarPageBtn.setToolTip(statusbar_tip)
            if hasattr(self, "ios_home"):
                self.ios_home.set_statusbar_locked(statusbar_locked)
            # toggle option visibility for the minimum versions
            for version, views in MinTweakVersions.items():
                # show views if the version is higher
                parsed_ver = Version(version)
                for view in views:
                    view.setVisible(device_ver >= parsed_ver)
            # The Status Bar page is no longer force-hidden on iOS 27 -- the
            # carrier name is delivered through StatusBarOverrides.archive.
            # Visibility is owned by _apply_hidden_feature_gating() (HotLoad
            # aware), so just re-apply it here. The Solarium fallback tweak is
            # a different, iOS 26-only tweak and keeps its own gating.
            if device_ver >= Version("27.0"):
                if hasattr(self, "ios_tweaks"):
                    self.ios_tweaks.set_force_solarium_fallback_visible(False)
            else:
                if hasattr(self, "ios_tweaks"):
                    self.ios_tweaks.set_force_solarium_fallback_visible(True)
            self._apply_hidden_feature_gating()

            # force video looping on iPads (loop gated off the classic widgets)
            is_iphone = self.device_manager.get_current_device_model().startswith("iPhone")
            if not is_iphone:
                # force looping
                tweaks[TweakID.PosterBoard].loop_video = True

            # sparse-restore book credits do not apply to this fork
            self.ui.jjtechBtn.hide()
            # swap out the current posterboard file
            tweaks[TweakID.PosterBoard].config_manager.update_for_saved_database(self.device_manager.get_current_device_udid())

            # show the PB if initial load is true
            if self.initial_load:
                self.initial_load = False
                if len(tweaks[TweakID.PosterBoard].tendies) > 0:
                    self.show_ios_page(2)
                elif len(tweaks[TweakID.Templates].templates) > 0:
                    # templates have no dedicated page in the unified shell
                    self.show_ios_page(2)
                self._sync_sidebar_selection()
        else:
            self.device_manager.set_current_device(index=None)
            # No device = unknown, and unknown is fail-closed for
            # MobileGestalt: stale ON state must not survive into a summary
            # or AutoSave.
            clear_unsupported_mobilegestalt_state(mobilegestalt_decision("", ""))

        # update the interface
        self.updateInterfaceForNewDevice()
        self.ios_home.update_device_info()
        self.ios_home.update_status()
        if index > -1:
            self.warn_for_dev_beta()



class SettingsMixin:
    """Settings/preset loading, theme switching and app-version label."""

    def loadSettings(self):
        try:
            # load the settings
            auto_reboot = self.settings.value("auto_reboot", True, type=bool)
            ignore_frame_limit = self.settings.value("ignore_pb_frame_limit", False, type=bool)
            disable_tendies_limit = self.settings.value("disable_tendies_limit", False, type=bool)
            auto_refresh_posterboard = self.settings.value("auto_refresh_posterboard", True, type=bool)
            use_backup_cache = self.settings.value("use_backup_cache", True, type=bool)

            skip_setup = self.settings.value("skip_setup", True, type=bool)
            supervised = self.settings.value("supervised", False, type=bool)
            organization_name = self.settings.value("organization_name", "", type=str)
            use_encrypted_backup = self.settings.value("use_encrypted_backup", False, type=bool)
            use_afc_media = self.settings.value("use_afc_media", True, type=bool)
            tweak_autosave = self.settings.value("tweak_autosave", True, type=bool)

            self.device_manager.pref_manager.auto_reboot = auto_reboot
            set_ignore_frame_limit(ignore_frame_limit)
            self.device_manager.pref_manager.disable_tendies_limit = disable_tendies_limit
            self.device_manager.pref_manager.auto_refresh_posterboard = auto_refresh_posterboard
            self.device_manager.pref_manager.use_backup_cache = use_backup_cache
            self.device_manager.pref_manager.use_encrypted_backup = use_encrypted_backup
            self.device_manager.pref_manager.use_afc_media = use_afc_media
            self.device_manager.pref_manager.skip_setup = skip_setup
            self.device_manager.pref_manager.supervised = supervised
            self.device_manager.pref_manager.organization_name = organization_name
            self.device_manager.pref_manager.tweak_autosave = tweak_autosave
        except Exception as e:
            # Never silent: a NameError here used to abort every assignment
            # below it, so the app quietly booted with default preferences
            # (and the Settings switches read back OFF after a restart).
            get_logger("gui").warning("loadSettings failed: %s", e, exc_info=True)


    def autosave_enabled(self) -> bool:
        """Whether the AutoSave preset is written/loaded at all.

        Read through instead of cached on the window so flipping the Settings
        switch takes effect immediately, with no restart.
        """
        try:
            return bool(self.device_manager.pref_manager.tweak_autosave)
        except Exception:
            # never let a missing pref break tweak handling: autosave is the
            # historical default, so fall back to it
            return True


    def _load_last_preset(self):
        """Load the latest autosaved preset on startup.

        Prefers the AutoSave preset (written on every tweak change) so the UI
        restores the most recent configuration. Falls back to the last
        manually-loaded preset when no autosave exists.

        With autosave turned off the AutoSave preset is NOT loaded: the file is
        deliberately left on disk (it can still be loaded by hand), but
        restoring a frozen snapshot on every launch would be misleading when
        the app no longer keeps it up to date.
        """
        if self.autosave_enabled() and "AutoSave" in self.preset_manager.list_presets():
            self.preset_manager.load_preset("AutoSave")
            # Rewrite AutoSave right away so stale entries (e.g. daemons that
            # are no longer exposed in the UI) are purged from disk on the
            # next launch instead of lingering in the file forever.
            self._save_autosave_preset()
            return
        last_preset = self.settings.value("last_loaded_preset", "", type=str)
        if last_preset:
            self.preset_manager.load_preset(last_preset)


    def _register_tweak_autosave(self):
        """Register callback to auto-save preset when tweaks change."""
        set_tweak_change_callback(self._on_tweak_changed)


    def _on_tweak_changed(self):
        """Called when any tweak value changes - schedule autosave."""
        if not self.autosave_enabled():
            # Still registered (so the callback is never dangling) but inert:
            # no debounce timer is even scheduled while the option is off.
            return
        if self._preset_autosave_pending:
            return
        self._preset_autosave_pending = True
        # Debounce: save after 500ms of no changes
        QtCore.QTimer.singleShot(500, self._save_autosave_preset)


    def _save_autosave_preset(self):
        """Save current tweak state to AutoSave preset."""
        self._preset_autosave_pending = False
        if not self.autosave_enabled():
            # Second guard: a debounce timer scheduled before the switch was
            # flipped off still fires, and must not resurrect the file.
            return
        try:
            self.preset_manager.save_preset(
                "AutoSave", "Automatic save of last tweak configuration", tags=["auto"],
                device_model=self.device_manager.get_current_device_model() or "",
                ios_version=self.device_manager.get_current_device_version() or "")
        except Exception:
            pass  # Silent fail - autosave is best-effort


    def apply_theme(self, theme: int):
        """Apply the active UI mode WITHOUT navigating away (Wave 11).

        Restores the v4-era dual interface (user order 2026-10-03):

        * IOS (WorkSlop, the main UI): the generated Nugget sidebar is
          hidden, the WorkSlop v4 sidebar rail shows, the shell is
          full-screen with no padding, and the content stack shows the
          iOS-style pages.
        * CLASSIC (Nugget, the second UI): the generated sidebar and the
          padded desktop shell show, the WorkSlop rail hides, and the
          classic Home/Daemons pages live in the same content stack; the
          iOS-style pages open inside this chrome as actions.

        Only the chrome changes — the current page stays put.
        """
        self.theme_manager.save_theme(theme)
        # The OS window title bar follows the active interface: dark in
        # Full Nugget (Windows immersive dark title bar via DWM), light
        # in the other two. Best-effort off Windows — see
        # src/gui/titlebar.py. The requested state is kept on
        # self._titlebar_dark so tests can verify it without native
        # chrome (offscreen renders have no OS title bar to capture).
        try:
            from src.gui.titlebar import (
                apply_os_titlebar_dark, titlebar_dark_for_theme,
            )
            self._titlebar_dark = titlebar_dark_for_theme(theme)
            apply_os_titlebar_dark(self, self._titlebar_dark)
        except Exception:
            pass
        is_ios = theme == ThemeManager.IOS
        self.ui.sidebar.setVisible(not is_ios)
        if hasattr(self, "workslop_sidebar"):
            self.workslop_sidebar.setVisible(is_ios)
        # The device bar serves both shells (device picker + refresh).
        self.ui.deviceBar.setVisible(True)
        if is_ios:
            # WorkSlop mode: full-screen, no padding
            self.shell_layout.setContentsMargins(0, 0, 0, 0)
            self.shell_layout.setSpacing(0)
            self.body_row.setSpacing(0)
            # entering the main UI: land on its pages unless already inside
            if self.content_stack.currentIndex() != 1:
                self.content_stack.setCurrentIndex(1)
                self.ios_pages.setCurrentIndex(0)
            self._update_shared_nav(self.ios_pages.currentIndex())
        else:
            # Nugget mode: padding around the desktop shell. Full Nugget
            # sits flush like upstream (dark window edge to edge).
            if theme == ThemeManager.FULL_NUGGET:
                self.shell_layout.setContentsMargins(0, 0, 0, 0)
                self.shell_layout.setSpacing(0)
            else:
                self.shell_layout.setContentsMargins(16, 16, 16, 16)
                self.shell_layout.setSpacing(12)
            self.body_row.setSpacing(16)
            # the classic shell hides the shared header except on pages
            # that need it (Icon Themes keeps "+ Add Icon")
            self._update_shared_nav(self.ios_pages.currentIndex())
            if theme == ThemeManager.FULL_NUGGET:
                self._land_full_nugget_view()
            elif self.content_stack.currentIndex() == 3:
                # Left Full Nugget with its page stack on screen.
                self.show_home()
            if self.content_stack.currentIndex() == 1 \
                    and self.ios_pages.currentIndex() == 0:
                # the iOS home has no meaning inside the classic shell
                self.show_home()
        # Classic-shell flavor (WorkSlop icons vs Full Nugget originals)
        # and the Nugget-only Liquid Glass subsection follow the mode.
        self._retheme_classic()
        # The shared device bar repaints with its shell (dark in Full
        # Nugget, the themed light pill otherwise).
        try:
            self._style_device_pill()
        except Exception:
            pass
        # Full Nugget also restyles the classic Home's preset block
        # (dark Nugget colors + the UI credit over the banner).
        try:
            self.pages[Page.Home].set_full_nugget(
                theme == ThemeManager.FULL_NUGGET)
        except Exception:
            pass
        # The classic shell hosts Daemons / Posterboard / Settings /
        # Themes / Apply from the page stacks; in Full Nugget they take the
        # Nugget-original dark palette like the vendored Nugget pages
        # (user report 2026-10-03: they were still WorkSlop-light). The
        # classic Daemons page (stack 2) and the iOS-stack Daemons page
        # both follow; UI-1 and UI-2 keep their themed look untouched.
        for _page in (getattr(self, "ios_daemons", None),
                      getattr(self, "ios_posterboard", None),
                      getattr(self, "ios_settings", None),
                      getattr(self, "ios_themes_hub", None),
                      getattr(self, "ios_apply", None)):
            try:
                if _page is not None:
                    _page.set_full_nugget(
                        theme == ThemeManager.FULL_NUGGET)
            except Exception:
                pass
        try:
            self.pages[Page.Daemons].set_full_nugget(
                theme == ThemeManager.FULL_NUGGET)
        except Exception:
            pass
        for _page in (getattr(self, "ios_liquidglass", None),
                      getattr(self, "ios_tweaks", None)):
            try:
                if _page is not None:
                    _page.refresh_nugget_lg_visibility()
            except Exception:
                pass
        self._sync_sidebar_selection()
    def updateAppVersionLabel(self):
        new_text: str = self.ui.appVersionLbl.text()
        new_text = new_text.replace("%VERSION", App_Version)
        # The generated UI still ships the upstream caption; the classic
        # (Nugget-mode) sidebar shows it again since Wave 11, so brand it
        # WorkSlop Desktop here instead of editing the generated file.
        new_text = new_text.replace("GoldenNugget", "WorkSlop")
        if App_Build > 0:
            new_text = new_text.replace("%BETATAG", f"(beta {App_Build})")
        else:
            new_text = new_text.replace("%BETATAG", "")
        self.ui.appVersionLbl.setText(new_text)


    def _sync_settings(self):
        """Sync settings to disk immediately after critical changes."""
        try:
            self.settings.sync()
        except Exception:
            pass  # Best effort



class NavigationMixin:
    """Page structure, shared IOS nav bar and sidebar selection."""

    # Pages allowed to keep the iOS-style header.
    # Each one has a right action that is otherwise unreachable on the page
    # itself (Icon Themes "+ Add Icon"). The PosterBoard page keeps its header
    # in iOS mode only: it already has its own in-page "Import Files" card,
    # so the header's "+ Add Tendies" would be redundant chrome in classic.
    _classic_nav_pages = (10,)

    def _update_shared_nav(self, index: int):
        classic = ThemeManager.is_classic(getattr(self.theme_manager,
                          "current_theme", ThemeManager.IOS))
        if classic and index not in self._classic_nav_pages:
            # The classic (Nugget) shell hides the shared iOS header except
            # on pages that need it (Icon Themes keeps "+ Add Icon"); the
            # page refresh + selection sync below still run so hosted
            # iOS-style pages never show stale device state.
            self.ios_nav.setVisible(False)
            self.ios_nav.clear_right_action()
        else:
            # the iOS home page is full-screen — no header at all. The
            # refresh + sidebar sync below must still run for page 0:
            # returning early here left the rail highlighting the previous
            # page (e.g. Settings) after a programmatic jump home.
            self.ios_nav.setVisible(index != 0)
            if index == 0:
                self.ios_nav.clear_right_action()
            else:
                title = self._ios_page_titles.get(index, "")
                self.ios_nav.set_title(title)
                self.ios_nav.set_back_visible(True)
                right = self._nav_right_actions.get(index)
                if right:
                    self.ios_nav.set_right_action(right[0], right[1])
                else:
                    self.ios_nav.clear_right_action()
        # REAUDIT FIX: device-dependent pages (Settings "This device" rows,
        # Passcode device line, Backup apply state...) build their UI once at
        # construction, so they showed stale "No device" after the iPhone was
        # connected. Refresh on every navigation so they read live state.
        # currentChanged fires synchronously from setCurrentIndex, which
        # covers all navigation paths (sidebar, home tiles, direct calls).
        try:
            page = self.ios_pages.widget(index)
            refresh = getattr(page, "refresh", None)
            if callable(refresh):
                refresh()
        except Exception:
            pass
        # Keep the blue top tabs highlighted with whatever page is showing,
        # no matter which path navigated here (tabs, Home tiles, dialogs).
        try:
            self._sync_sidebar_selection()
        except Exception:
            pass


    def _on_workslop_menu(self, menu_id: str):
        """Navigate from the WorkSlop v4 sidebar rail."""
        if menu_id == "home":
            self.show_home()
        elif menu_id == "tweaks":
            self.show_ios_page(1)
        elif menu_id == "gestalt":
            self.on_mobileGestaltPageBtn_clicked()
            return  # already syncs the sidebar
        elif menu_id == "wallpaper":
            self.on_posterboardPageBtn_clicked()
            return
        elif menu_id == "backup":
            self.ios_backup.refresh()
            self.show_ios_page(13)
        elif menu_id == "appdata":
            self.show_ios_page(15)
        elif menu_id == "themes":
            self.show_ios_page(14)
        elif menu_id == "liquidglassdisable":
            self.show_ios_page(16)
        elif menu_id == "settings":
            self.on_settingsPageBtn_clicked()
            return
        self._sync_sidebar_selection()

    def _sync_sidebar_selection(self):
        """Move the checked highlight of the ACTIVE shell's rail to the
        active view: the WorkSlop v4 sidebar in IOS mode, the generated
        Nugget sidebar buttons in CLASSIC mode."""
        classic = ThemeManager.is_classic(getattr(self.theme_manager,
                          "current_theme", ThemeManager.IOS))
        if classic:
            btns = (self.ui.homePageBtn, self.ui.posterboardPageBtn,
                    self.ui.springboardOptionsPageBtn,
                    self.ui.internalOptionsPageBtn,
                    self.ui.liquidGlassPageBtn, self.ui.daemonsPageBtn,
                    self.ui.backupPageBtn, self.ui.applyPageBtn,
                    self.ui.settingsPageBtn,
                    self.ui.statusBarPageBtn, self.ui.iconThemesPageBtn,
                    self.ui.gestaltPageBtn)
            page_to_btn = {
                0: 0,   # home
                2: 1,   # posterboard
                7: 2,   # springboard
                8: 3,   # internal
                9: 4,   # liquid glass
                3: 5,   # daemons (iOS page hosted in classic)
                13: 6,  # backup
                6: 7,   # apply
                4: 8,   # settings
                5: 9,   # status bar
                10: 10,  # icon themes
                12: 11,  # mobilegestalt
            }
            idx = None
            if self.content_stack.currentIndex() == 0:
                idx = 0
            elif self.content_stack.currentIndex() == 2:
                idx = 5  # classic daemons page
            elif self.content_stack.currentIndex() == 3:
                # Full Nugget stack: highlight by its section key.
                keys = getattr(self, "_nugget_page_keys", [])
                if keys:
                    idx = {"statusbar": 9, "springboard": 2,
                           "internal": 3, "liquidglass": 4}.get(
                               keys[self.nugget_stack.currentIndex()])
            elif self.content_stack.currentIndex() == 1:
                idx = page_to_btn.get(self.ios_pages.currentIndex())
            target = btns[idx] if idx is not None else None
            for b in btns:
                b.setChecked(b is target)
            return
        page_to_menu = {
            0: "home",
            1: "tweaks", 3: "tweaks", 5: "tweaks", 6: "tweaks",
            7: "tweaks", 8: "tweaks", 9: "tweaks",
            12: "gestalt",
            2: "wallpaper",
            13: "backup",
            15: "appdata",
            10: "themes", 11: "themes", 14: "themes",
            4: "settings",
            16: "liquidglassdisable",
        }
        menu = page_to_menu.get(self.ios_pages.currentIndex())
        if menu is not None and hasattr(self, "workslop_sidebar"):
            self.workslop_sidebar.select(menu)


    def show_home(self):
        """Open the home page of the ACTIVE UI mode."""
        if getattr(self.theme_manager, "current_theme", ThemeManager.IOS) \
                == ThemeManager.IOS:
            self.content_stack.setCurrentIndex(1)
            self.ios_pages.setCurrentIndex(0)
            self._update_shared_nav(0)
        else:
            self.content_stack.setCurrentIndex(0)
        self._refresh_preset_widgets()
        self._sync_sidebar_selection()


    def _refresh_preset_widgets(self):
        """Keep the active-preset banners on both home pages in sync."""
        try:
            self.pages[Page.Home].refresh_preset_widget()
        except Exception:
            pass
        try:
            self.ios_home.refresh_preset_widget()
        except Exception:
            pass


    def show_ios_page(self, index: int):
        self.content_stack.setCurrentIndex(1)
        self.ios_pages.setCurrentIndex(index)

    # -- Full Nugget pages (third interface) -------------------------------

    def _full_nugget_active(self) -> bool:
        return getattr(self.theme_manager, "current_theme", None) \
            == ThemeManager.FULL_NUGGET

    def _ensure_nugget_pages(self):
        """Build the vendored Nugget v7.4.1 pages on first use.

        The upstream form is set up on a throwaway window (kept alive
        on self) because setupUi() paints the window stylesheet and
        builds the whole widget tree; the tweak-section pages are then
        reparented into this window's Nugget stack and wired by the
        ported page builders in src/gui/nugget_pages/.
        """
        if self._nugget_ui is not None:
            return
        from src.qt.nugget741_ui import Ui_Nugget741
        from src.gui.nugget_pages import (
            NuggetInternalPage, NuggetLiquidGlassPage,
            NuggetSpringboardPage, NuggetStatusBarPage,
        )
        host = QtWidgets.QMainWindow()
        ui = Ui_Nugget741()
        ui.setupUi(host)
        self._nugget_ui_host = host
        self._nugget_ui = ui
        pages = (
            ("statusbar", ui.statusBarPage, NuggetStatusBarPage(ui)),
            ("springboard", ui.springboardOptionsPage,
             NuggetSpringboardPage(ui)),
            ("internal", ui.internalOptionsPage, NuggetInternalPage(ui)),
            ("liquidglass", ui.liquidGlassPage, NuggetLiquidGlassPage(ui)),
        )
        for key, widget, page in pages:
            widget.setParent(None)
            self.nugget_stack.addWidget(widget)
            self._nugget_pages[key] = page
            self._nugget_page_keys.append(key)
        # Upstream's window stylesheet is the dark chrome of the form;
        # scoping it to the stack themes the stolen pages exactly as
        # upstream's window does, without touching the other shells.
        sheet = host.styleSheet()
        if sheet:
            self.nugget_stack.setStyleSheet(sheet)

    #: iOS-page index -> Nugget stack key, for theme-switch landing.
    _IOS_TO_NUGGET_PAGE = {5: "statusbar", 7: "springboard",
                           8: "internal", 9: "liquidglass"}

    def _land_full_nugget_view(self):
        """Pick the Full Nugget view matching what is on screen."""
        if self.content_stack.currentIndex() == 1:
            key = self._IOS_TO_NUGGET_PAGE.get(self.ios_pages.currentIndex())
            if key is not None:
                self.show_nugget_page(key)
                return
            self.show_home()
        # Classic Home / classic Daemons / the Nugget stack stay as-is.

    def show_nugget_page(self, key: str):
        """Open one original-Nugget tweak page (Full Nugget mode)."""
        self._ensure_nugget_pages()
        page = self._nugget_pages[key]
        was_loaded = page.loaded
        page.load()
        if was_loaded and key == "statusbar":
            # Reflect overrides changed in another shell.
            try:
                page.load_status_bar()
            except Exception:
                pass
        self.content_stack.setCurrentWidget(self.nugget_stack)
        self.nugget_stack.setCurrentIndex(self._nugget_page_keys.index(key))
        self._sync_sidebar_selection()


    def open_presets_section(self):
        """Open the settings page and scroll straight to the presets section."""
        self.content_stack.setCurrentIndex(1)
        self.ios_pages.setCurrentIndex(4)
        self._update_shared_nav(4)
        self._sync_sidebar_selection()
        self.ios_settings.scroll_to_presets()


    # -- fullscreen -------------------------------------------------------
    def set_fullscreen(self, enabled: bool) -> bool:
        """Enter or leave true window fullscreen.

        Returns True when the requested state is active. Leaving fullscreen
        restores the maximized state the window had before it was entered;
        the shell layout is size-policy driven (fixed rail + expanding page
        stack), so maximized and fullscreen states reuse the same layout.
        """
        enabled = bool(enabled)
        if enabled == self.isFullScreen():
            return enabled
        if enabled:
            self._fullscreen_restore_maximized = self.isMaximized()
            self.showFullScreen()
        else:
            if getattr(self, "_fullscreen_restore_maximized", False):
                self.showMaximized()
            else:
                self.showNormal()
        return self.isFullScreen()

    def toggle_fullscreen(self) -> bool:
        """Toggle fullscreen (F11). Returns the new fullscreen state."""
        return self.set_fullscreen(not self.isFullScreen())

    def _install_fullscreen_shortcuts(self):
        """Register F11 / ESC as window shortcuts for fullscreen.

        The application-wide event filter alone proved unreliable on real
        Windows (a focused child can consume or re-route the raw key
        event before the filter sees it, and it never fires at all for a
        hidden/modal-blocked window), so fullscreen is driven by proper
        QShortcuts with WindowShortcut context: they fire whenever this
        window is the active window, whatever child widget has focus,
        and stay inactive while a modal dialog owns its own window.
        ESC only leaves fullscreen; in a normal window it does nothing
        here (navigation-back stays with the event filter below).
        """
        from PySide6.QtGui import QKeySequence, QShortcut
        f11 = QShortcut(QKeySequence("F11"), self)
        f11.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        f11.activated.connect(self.toggle_fullscreen)
        esc = QShortcut(QKeySequence("Escape"), self)
        esc.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        esc.activated.connect(self._esc_shortcut)
        self._fullscreen_shortcuts = (f11, esc)

    def _esc_shortcut(self):
        if self.isFullScreen():
            self.set_fullscreen(False)

    def eventFilter(self, obj, event):
        """Handle F11 fullscreen, ESC, and the mouse back button."""
        if QtWidgets.QApplication.activeModalWidget() is not None:
            return False
        try:
            etype = event.type()
        except (AttributeError, TypeError):
            return False
        if etype == QtCore.QEvent.Type.KeyPress:
            if event.key() == QtCore.Qt.Key.Key_F11:
                self.toggle_fullscreen()
                return True
            if event.key() == QtCore.Qt.Key.Key_Escape:
                # In fullscreen, ESC first leaves fullscreen; only a normal
                # window treats ESC as navigation-back.
                if self.isFullScreen():
                    self.set_fullscreen(False)
                    return True
                return self._go_back()
        if etype == QtCore.QEvent.Type.MouseButtonPress and event.button() in (
                QtCore.Qt.MouseButton.BackButton, QtCore.Qt.MouseButton.ExtraButton1):
            return self._go_back()
        return False


    def _go_back(self) -> bool:
        """Navigate back: subpage -> home (stay in the UI)."""
        classic = ThemeManager.is_classic(getattr(self.theme_manager,
                          "current_theme", ThemeManager.IOS))
        if classic and self.content_stack.currentIndex() != 0:
            self.show_home()
            return True
        if self.ios_pages.currentIndex() != 0:
            self.ios_pages.setCurrentIndex(0)
            self._update_shared_nav(0)
            self._sync_sidebar_selection()
            return True
        return False


    def on_homePageBtn_clicked(self):
        self.show_home()


    def on_statusBarPageBtn_clicked(self):
        if self._full_nugget_active():
            self.show_nugget_page("statusbar")
            return
        self.show_ios_page(5)
        self._sync_sidebar_selection()


    def on_springboardOptionsPageBtn_clicked(self):
        if self._full_nugget_active():
            self.show_nugget_page("springboard")
            return
        self.show_ios_page(7)
        self._sync_sidebar_selection()


    def on_internalOptionsPageBtn_clicked(self):
        if self._full_nugget_active():
            self.show_nugget_page("internal")
            return
        self.show_ios_page(8)
        self._sync_sidebar_selection()


    def on_liquidGlassPageBtn_clicked(self):
        if self._full_nugget_active():
            self.show_nugget_page("liquidglass")
            return
        self.show_ios_page(9)
        self._sync_sidebar_selection()


    def on_mobileGestaltPageBtn_clicked(self):
        self.ios_gestalt.refresh()
        self.show_ios_page(12)
        self._sync_sidebar_selection()


    def on_daemonsPageBtn_clicked(self):
        if ThemeManager.is_classic(getattr(
                self.theme_manager, "current_theme", ThemeManager.IOS)):
            # The Nugget shell has its own classic Daemons page.
            self.pages[Page.Daemons].load()
            self.pages[Page.Daemons].refresh()
            self.content_stack.setCurrentIndex(2)
        else:
            self.ios_daemons.refresh_from_tweaks()
            self.show_ios_page(3)
        self._sync_sidebar_selection()


    def on_iconThemesPageBtn_clicked(self):
        self.show_ios_page(10)
        self._sync_sidebar_selection()


    def on_posterboardPageBtn_clicked(self):
        self.show_ios_page(2)
        self._sync_sidebar_selection()


    def on_applyPageBtn_clicked(self):
        self.show_ios_page(6)
        self._sync_sidebar_selection()


    def on_backupPageBtn_clicked(self):
        # Classic-sidebar Backup entry (UI-2 & UI-3): opens the same
        # Backup & Apply page as the main UI's Backup menu (iOS page
        # 13 — Start Protective Backup + Apply Tweaks).
        self.ios_backup.refresh()
        self.show_ios_page(13)
        self._sync_sidebar_selection()


    def on_settingsPageBtn_clicked(self):
        self.ios_settings.refresh()
        self.show_ios_page(4)
        self._sync_sidebar_selection()


    def show_about_dialog(self):
        dialog = AboutProgramDialog(self)
        dialog.exec()



class ApplyMixin:
    """Apply/reset orchestration, alerts and dialog prompts."""

    # IOSSummaryDialog extra-button result when the user asks to update the
    # backup cache from the pre-apply summary (QDialog.Accepted=1/Rejected=0).
    _SUMMARY_UPDATE_CACHE = 2

    def update_label(self, txt: str):
        # Mirror progress into the iOS surfaces (home indicator + Apply page)
        try:
            if txt:
                self.ios_home.show_process_status(txt)
                self.ios_apply.set_status(txt)
                self.ios_backup.set_process_status(txt)
        except Exception:
            pass


    def remove_tweaks_clicked(self):
        dialog = ResetDialog(device_manager=self.device_manager, apply_reset=self.apply_changes)
        dialog.exec()


    @QtCore.Slot()
    def apply_tweaks_clicked(self):
        self.apply_changes()


    def _build_apply_summary(self) -> tuple:
        """Human-readable breakdown of what an apply would change.

        Returns ``(lines, total)`` — ``lines`` feed the pre-apply summary
        dialog, ``total`` is the summed change count (0 = nothing to do).
        """
        from src.tweaks.registry import SPECS_BY_SECTION, SPECS_BY_ID, Section
        from src.tweaks.tweak_loader import (
            load_plist_tweaks, load_daemons, load_mobilegestalt,
            load_rdar_fix, load_eligibility, load_risky)
        from src.devicemanagement.constants import mobilegestalt_decision
        from src.tweaks.capabilities import (
            clear_unsupported_mobilegestalt_state, tweak_deliverability,
            validate_custom_resolution,
        )
        load_plist_tweaks()
        load_daemons()
        # B7: the loaders below register every tweak family the registry
        # section loop above cannot see (all are idempotent, so calling them
        # here is safe even if a page already ran them). Wave 10: they take
        # the current shared MobileGestalt decision — never a no-argument
        # load that would register deliverable gestalt tweaks blind.
        try:
            _dm = self.device_manager
            _build = _dm.get_current_device_build() or ""
            _version = _dm.get_current_device_version() or ""
            _model = _dm.get_current_device_model() or ""
            _device = _dm.data_singleton.current_device
        except Exception:
            _build = _version = _model = ""
            _device = None
        _decision = mobilegestalt_decision(_build, _version)
        if not _decision.supported:
            clear_unsupported_mobilegestalt_state(_decision)
        load_mobilegestalt(_build, _version, _decision)
        load_rdar_fix(_device, _decision)
        load_eligibility(_device, _decision)
        load_risky()

        def _deliverable(tid, tw=None):
            ok, _code, _msg = tweak_deliverability(
                tid, device_version=_version, device_build=_build,
                is_iphone=_model.startswith("iPhone"), tweak=tw)
            return ok

        lines = []
        total = 0

        def add(label, count):
            nonlocal total
            if count > 0:
                total += count
                lines.append(f"• {label}: {count}")

        for section in Section:
            enabled = sum(
                1 for spec in SPECS_BY_SECTION[section]
                if getattr(tweaks.get(spec.id), "enabled", False)
                and _deliverable(spec.id, tweaks.get(spec.id)))
            if enabled:
                add(QCoreApplication.translate("Nugget", section.value), enabled)

        pb = tweaks.get(TweakID.PosterBoard)
        if pb is not None and _deliverable(TweakID.PosterBoard, pb):
            add(QCoreApplication.translate("Nugget", "PosterBoard"), len(pb.tendies))

        tmpl = tweaks.get(TweakID.Templates)
        if tmpl is not None and _deliverable(TweakID.Templates, tmpl):
            add(QCoreApplication.translate("Nugget", "Templates"), len(tmpl.templates))

        st = tweaks.get(TweakID.StatusBar)
        if st is not None and _deliverable(TweakID.StatusBar, st):
            try:
                # The named no-SIM feature gets its own summary line; the
                # generic count excludes its owned flags (no double count).
                for op in st.describe_active_operations():
                    if op.get("id") == "statusbar.full_signal_bars_no_sim":
                        lines.append("• " + QCoreApplication.translate(
                            "Nugget", "Full Signal Bars (No SIM Visual)"))
                        total += 1
                    else:
                        add(QCoreApplication.translate("Nugget", "Status Bar"),
                            int(op.get("count", 0)))
            except Exception:
                pass

        dm = tweaks.get(TweakID.Daemons)
        if dm is not None and _deliverable(TweakID.Daemons, dm):
            add(QCoreApplication.translate("Nugget", "Daemons"),
                sum(1 for v in getattr(dm, "value", {}).values() if v))

        it = tweaks.get(TweakID.IconThemes)
        if it is not None:
            add(QCoreApplication.translate("Nugget", "Icon Themes"), len(it.themes))

        # B7: tweak families the registry section loop misses. Registry SPECS
        # only cover LIQUID_GLASS/SPRINGBOARD/FEATURE_FLAGS/INTERNAL; these
        # are registered by the other loaders above.
        from src.tweaks.tweak_classes import (
            MobileGestaltTweak, MobileGestaltPickerTweak,
            MobileGestaltMultiTweak, MobileGestaltCacheDataTweak,
            RdarFixTweak, FeatureFlagTweak)
        from src.tweaks.eligibility_tweak import (
            EligibilityTweak, AITweak, BookRestoreFileTweak)

        _gestalt_types = (MobileGestaltTweak, MobileGestaltPickerTweak,
                          MobileGestaltMultiTweak, MobileGestaltCacheDataTweak,
                          RdarFixTweak)
        # Spoof model/hardware/CPU are MobileGestalt picker tweaks but live
        # in the Eligibility UI section — count them there, not here.
        _spoof_ids = {TweakID.SpoofModel, TweakID.SpoofHardware,
                      TweakID.SpoofCPU}
        gestalt_on = sum(
            1 for tid, tw in tweaks.items()
            if tid not in _spoof_ids
            and isinstance(tw, _gestalt_types)
            and getattr(tw, "enabled", False)
            and _deliverable(tid, tw))
        add(QCoreApplication.translate("Nugget", "MobileGestalt"), gestalt_on)

        _elig_types = (EligibilityTweak, AITweak, BookRestoreFileTweak)
        elig_on = sum(
            1 for tid, tw in tweaks.items()
            if isinstance(tw, _elig_types)
            and getattr(tw, "enabled", False)
            and _deliverable(tid, tw))
        elig_on += sum(
            1 for tid in _spoof_ids
            if getattr(tweaks.get(tid), "enabled", False)
            and _deliverable(tid, tweaks.get(tid)))
        # Non-registry FeatureFlag tweaks are counted only when the central
        # deliverability decision would actually let them generate a payload
        # (removed tombstones such as AIFeatureFlags never count).
        ff_on = sum(
            1 for tid, tw in tweaks.items()
            if isinstance(tw, FeatureFlagTweak)
            and tid not in SPECS_BY_ID
            and getattr(tw, "enabled", False)
            and _deliverable(tid, tw))
        add(QCoreApplication.translate("Nugget", "Eligibility"),
            elig_on + ff_on)

        # Risky page tweaks (DisableOTAFile, CustomResolution) and the
        # ScreenTime agent plist nullifier (loaded by load_daemons()).
        # CustomResolution only counts when it would pass the backend gate.
        def _risky_count(tid):
            tw = tweaks.get(tid)
            if not getattr(tw, "enabled", False):
                return 0
            if not _deliverable(tid, tw):
                return 0
            if tid == TweakID.CustomResolution:
                ok, _code, _msg = validate_custom_resolution(
                    getattr(tw, "value", None))
                return 1 if ok else 0
            return 1

        risky_on = sum(
            _risky_count(tid)
            for tid in (TweakID.DisableOTAFile, TweakID.CustomResolution,
                        TweakID.ClearScreenTimeAgentPlist))
        add(QCoreApplication.translate("Nugget", "Risky"), risky_on)

        return lines, total


    def _confirm_apply_summary(self) -> bool:
        """Show the pre-apply summary; True only if the user confirms.

        When the backup cache is enabled, an extra "Update Cache" button lets
        the user force a cache refresh right here — the running summary shows
        the cache's creation date, the refresh runs in a background thread,
        and the dialog re-opens with the fresh date.
        """
        cache_enabled = self._backup_cache_enabled()
        while True:
            lines, total = self._build_apply_summary()
            if not lines:
                QtWidgets.QMessageBox.information(
                    self,
                    QCoreApplication.translate("Nugget", "Nothing to apply"),
                    QCoreApplication.translate(
                        "Nugget",
                        "No tweaks, daemons, wallpapers or templates are enabled. "
                        "Enable something first."))
                return False
            if cache_enabled:
                cache_line = self._backup_cache_summary_line()
                if cache_line:
                    lines.append(cache_line)
            from src.gui.ios.components import IOSSummaryDialog
            dlg = IOSSummaryDialog(
                title=QCoreApplication.translate("Nugget", "Apply Tweaks"),
                lines=lines,
                muted=QCoreApplication.translate(
                    "Nugget",
                    "Your device reboots when it's done — remember to turn Find My "
                    "back on afterwards. A protective backup runs first."),
                confirm_text=QCoreApplication.translate("Nugget", "Apply"),
                extra_button=(QCoreApplication.translate("Nugget", "Update Cache")
                              if cache_enabled else ""),
                parent=self)
            res = dlg.exec()
            if res == self._SUMMARY_UPDATE_CACHE:
                self._run_cache_update()
                # Re-open the summary (with the refreshed cache date) so the
                # user can review and then confirm or cancel.
                continue
            return res == QtWidgets.QDialog.Accepted

    def _backup_cache_enabled(self) -> bool:
        return (self.device_manager.pref_manager.use_backup_cache
                and not os.environ.get("GOLDENNUGGET_NO_BACKUP_CACHE"))

    def _backup_cache_summary_line(self) -> str:
        udid = self.device_manager.get_current_device_udid()
        if not udid:
            return ""
        from src.restore.protective_cache import peek_cache_info
        info = peek_cache_info(udid)
        q = QCoreApplication.translate
        if info is None:
            return q(
                "Nugget",
                "• Backup cache: none yet (will be created on this apply)")
        return q(
            "Nugget",
            "• Backup cache from: {0} (reused if fresh)").format(
                info.get("created") or "unknown")

    def _run_cache_update(self) -> bool:
        """Force a backup-cache refresh in a background thread, modally.

        Returns True only when the refresh ran to completion. The progress
        dialog stays open until ``finished_with_result`` fires; a failure
        already surfaced through the alert pipeline.
        """
        from src.gui.thread_workers.apply_worker import CacheUpdateThread
        udid = self.device_manager.get_current_device_udid()
        if not udid:
            QtWidgets.QMessageBox.information(
                self,
                QCoreApplication.translate("Nugget", "Update Cache"),
                QCoreApplication.translate(
                    "Nugget", "No device is selected. Connect your device first."))
            return False
        worker = CacheUpdateThread(manager=self.device_manager)
        self._cache_update_thread = worker  # keep a strong ref while running
        prog = QtWidgets.QProgressDialog(
            QCoreApplication.translate(
                "Nugget", "Updating backup cache..."),
            "", 0, 0, self)
        prog.setWindowTitle(QCoreApplication.translate("Nugget", "Update Cache"))
        prog.setWindowModality(QtCore.Qt.WindowModal)
        prog.setCancelButton(None)
        prog.setMinimumDuration(0)
        result = [False]

        def _on_progress(txt):
            prog.setLabelText(txt)

        def _on_finish(ok: bool, _err: str):
            result[0] = ok
            prog.close()

        worker.progress.connect(_on_progress)
        worker.finished_with_result.connect(_on_finish)
        worker.alert.connect(self.alert_message)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        # Modal event loop — worker signals keep flowing until _on_finish closes it.
        prog.exec()
        return result[0]


    def apply_changes(self, reset_pages: list=None):
        if not self.apply_in_progress:
            # Applies (not resets) get a what-will-change summary first.
            if reset_pages is None and not self._confirm_apply_summary():
                return
            self.apply_in_progress = True
            self.toggle_thread_btns(disabled=True)
            self.worker_thread = ApplyThread(manager=self.device_manager, settings=self.settings, reset_pages=reset_pages)
            self.worker_thread.progress.connect(self.update_label)
            self.worker_thread.alert.connect(self.alert_message)
            self.worker_thread.request_text.connect(self.on_password_request)
            self.worker_thread.choice_prompt.connect(self.on_choice_prompt)
            self.worker_thread.backup_finished.connect(self._on_backup_finished)
            self.worker_thread.finished_with_result.connect(self.finish_apply_thread)
            self.worker_thread.finished.connect(self.worker_thread.deleteLater)
            self.worker_thread.start()

    def _on_backup_finished(self, backup_root: str):
        """WorkSlop: the protective device backup just hit 100%.

        Opens the OS file manager with the finished backup selected so the
        user can copy it somewhere safe before the apply continues. Runs on
        the GUI thread (queued from ApplyThread.backup_finished).
        """
        from src.utils.file_manager import reveal_in_file_manager
        revealed = reveal_in_file_manager(backup_root)
        if revealed:
            self.update_label(QCoreApplication.translate(
                "Nugget",
                "Backup complete — file manager opened. Copy the backup "
                "somewhere safe, then the apply continues."))
        else:
            self.update_label(QCoreApplication.translate(
                "Nugget",
                "Backup complete (saved at {0}).").format(backup_root))


    def alert_message(self, alert: Optional[ApplyAlertMessage], log_to_console: bool = True):
        if alert is None:
            # do sudo dialog input
            get_sudo_pwd() # clear if it is already there
            pwd, ok = QtWidgets.QInputDialog.getText(None, "Enter Sudo Password", "Enter Your Computer's Password:", QtWidgets.QLineEdit.Password, "")
            if ok and pwd:
                set_sudo_pwd(pwd)
            return
        if log_to_console:
            print(alert.txt)
        # Backend messages that did not pick an explicit icon default to
        # the error renderer (QMessageBox.Critical).
        icon = alert.icon if alert.icon is not None else QtWidgets.QMessageBox.Critical
        # Apply/reset failures carry a traceback: route them through the same
        # parsed crash dialog (severity/likely cause + Copy Error + Report on
        # GitHub + Open Log), instead of a raw QMessageBox.
        if (icon == QtWidgets.QMessageBox.Critical
                and alert.exc_type is not None and alert.detailed_txt):
            from src.exceptions.crash_handler import show_error_dialog, _classify
            info = _classify(alert.exc_type, alert.exc_value)
            self._embedded_alert_error(alert, info)
            return
        detailsBox = QtWidgets.QMessageBox()
        detailsBox.setIcon(icon)
        detailsBox.setWindowTitle(alert.title)
        detailsBox.setText(alert.txt)
        if alert.detailed_txt != None:
            detailsBox.setDetailedText(alert.detailed_txt)
        restore_btn = None
        if alert.backup_path:
            restore_btn = detailsBox.addButton(
                self.tr("Restore data from backup"), QtWidgets.QMessageBox.AcceptRole)
        detailsBox.exec()
        if restore_btn is not None and detailsBox.clickedButton() is restore_btn:
            self._start_cache_restore()


    def _embedded_alert_error(self, alert: ApplyAlertMessage, info: dict):
        """Show an apply failure through the crash/error dialog."""
        # Need the restore callback to survive the dialog's exec() lifetime.
        def _restore():
            self._start_cache_restore()
        from src.exceptions.crash_handler import show_error_dialog
        show_error_dialog(
            summary=alert.txt,
            traceback_text=alert.detailed_txt,
            info=info,
            backup_path=alert.backup_path,
            on_restore=_restore if alert.backup_path else None,
        )


    def _start_cache_restore(self):
        from src.gui.thread_workers.apply_worker import RestoreCacheThread
        if getattr(self, '_cache_restore_in_progress', False):
            return
        if self.apply_in_progress:
            # A restore and an apply/reset must never drive the device at the
            # same time — both open their own lockdown sessions.
            self.alert_message(ApplyAlertMessage(
                txt="Cannot restore data while an apply/reset is in progress.",
                title="Restore data",
                icon=QtWidgets.QMessageBox.Warning,
            ), log_to_console=False)
            return
        self._cache_restore_in_progress = True
        # Hold the thread on the window like ApplyThread/RefreshDevicesThread
        # do. A bare local reference lets the Python wrapper be garbage-
        # collected while the native thread is still running, which Qt reports
        # as the "QThread: Destroyed while thread '' is still running" crash
        # in the middle of a device restore.
        worker = RestoreCacheThread(manager=self.device_manager)
        self._cache_restore_thread = worker
        worker.progress.connect(self._update_restore_label)
        worker.alert.connect(self.alert_message)
        # The media push can hit a device that is paired but still locked after
        # the reboot, so the recovery needs the same Abort/Resume dialog the
        # apply gets.
        worker.choice_prompt.connect(self.on_choice_prompt)
        worker.finished_with_result.connect(self._finish_cache_restore)
        worker.finished.connect(self._cache_restore_thread_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()


    def _start_full_backup_restore(self, backup_dir: str):
        """WorkSlop: restore a standard full backup folder (format 1).

        Mirrors ``_start_cache_restore`` (format 2 = GoldenNugget protective
        backup) with the same threading/guarding discipline.
        """
        from src.gui.thread_workers.apply_worker import RestoreFullBackupThread
        if getattr(self, '_full_restore_in_progress', False):
            return
        if self.apply_in_progress or getattr(self, '_cache_restore_in_progress', False):
            # A restore and an apply/reset must never drive the device at the
            # same time — both open their own lockdown sessions.
            self.alert_message(ApplyAlertMessage(
                txt="Cannot restore a backup while another operation is in progress.",
                title="Restore full backup",
                icon=QtWidgets.QMessageBox.Warning,
            ), log_to_console=False)
            return
        self._full_restore_in_progress = True
        # Hold the thread on the window like ApplyThread/RefreshDevicesThread
        # do — a bare local reference lets the Python wrapper be garbage-
        # collected while the native thread is still running.
        worker = RestoreFullBackupThread(manager=self.device_manager,
                                         backup_dir=backup_dir)
        self._full_restore_thread = worker
        worker.progress.connect(self._update_restore_label)
        worker.alert.connect(self.alert_message)
        worker.request_text.connect(self.on_password_request)
        worker.choice_prompt.connect(self.on_choice_prompt)
        worker.finished_with_result.connect(self._finish_full_restore)
        worker.finished.connect(self._full_restore_thread_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _finish_full_restore(self, success: bool, error_msg: str = ""):
        self._full_restore_in_progress = False
        self._mirror_backup_finish(success)
        if not success or error_msg:
            try:
                self.alert_message(ApplyAlertMessage(
                    txt=f"Restore full backup: {error_msg or 'failed'}",
                    title="Restore full backup",
                    icon=QtWidgets.QMessageBox.Critical,
                ), log_to_console=False)
            except Exception:
                pass

    def _full_restore_thread_finished(self):
        # run() returned, so the native thread is done; drop the window's
        # reference (deleteLater is already queued via the other connection).
        try:
            self._full_restore_thread = None
        except Exception:
            pass


    def _start_full_backup(self, save_dir: str):
        """WorkSlop: create a real full iPhone backup (the iTunes way)."""
        from src.gui.thread_workers.apply_worker import FullBackupThread
        if getattr(self, '_full_backup_in_progress', False):
            return
        if (self.apply_in_progress
                or getattr(self, '_cache_restore_in_progress', False)
                or getattr(self, '_full_restore_in_progress', False)):
            self.alert_message(ApplyAlertMessage(
                txt="Cannot start a full backup while another operation is in progress.",
                title="Full backup",
                icon=QtWidgets.QMessageBox.Warning,
            ), log_to_console=False)
            return
        self._full_backup_in_progress = True
        worker = FullBackupThread(manager=self.device_manager, save_dir=save_dir)
        self._full_backup_thread = worker
        worker.progress.connect(self._update_restore_label)
        worker.alert.connect(self.alert_message)
        worker.choice_prompt.connect(self.on_choice_prompt)
        worker.backup_finished.connect(self._on_full_backup_saved)
        worker.finished_with_result.connect(self._finish_full_backup)
        worker.finished.connect(self._full_backup_thread_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_full_backup_saved(self, backup_path: str):
        """Full backup hit 100%: reveal it so the user sees where it is."""
        from src.utils.file_manager import reveal_in_file_manager
        revealed = reveal_in_file_manager(backup_path)
        try:
            mbox = QtWidgets.QMessageBox(self)
            mbox.setWindowTitle(QCoreApplication.translate("Nugget", "Full Backup Complete"))
            mbox.setIcon(QtWidgets.QMessageBox.Information)
            mbox.setText(QCoreApplication.translate(
                "Nugget", "Full backup complete."))
            mbox.setInformativeText(
                QCoreApplication.translate(
                    "Nugget", "Saved at: {0}").format(backup_path)
                + ("\n" + QCoreApplication.translate(
                    "Nugget",
                    "The file manager was opened with the backup selected.")
                   if revealed else ""))
            mbox.exec()
        except Exception:
            pass

    def _finish_full_backup(self, success: bool, error_msg: str = ""):
        self._full_backup_in_progress = False
        self._mirror_backup_finish(success)
        if not success or error_msg:
            try:
                self.alert_message(ApplyAlertMessage(
                    txt=f"Full backup: {error_msg or 'failed'}",
                    title="Full backup",
                    icon=QtWidgets.QMessageBox.Critical,
                ), log_to_console=False)
            except Exception:
                pass

    def _full_backup_thread_finished(self):
        try:
            self._full_backup_thread = None
        except Exception:
            pass

    def _start_protective_backup(self):
        """WorkSlop: run the selective protective backup on demand.

        Same backup the iOS 27 apply flow runs automatically — photos,
        messages, contacts, Apple ID/settings data, keychain when encrypted.
        NOT a full backup.
        """
        from src.gui.thread_workers.apply_worker import ProtectiveBackupThread
        if getattr(self, '_protective_backup_in_progress', False):
            return
        if (self.apply_in_progress
                or getattr(self, '_cache_restore_in_progress', False)
                or getattr(self, '_full_restore_in_progress', False)
                or getattr(self, '_full_backup_in_progress', False)):
            self.alert_message(ApplyAlertMessage(
                txt="Cannot start a protective backup while another operation is in progress.",
                title="Protective backup",
                icon=QtWidgets.QMessageBox.Warning,
            ), log_to_console=False)
            return
        self._protective_backup_in_progress = True
        worker = ProtectiveBackupThread(manager=self.device_manager)
        self._protective_backup_thread = worker
        worker.progress.connect(self._update_restore_label)
        worker.alert.connect(self.alert_message)
        worker.backup_finished.connect(self._on_protective_backup_saved)
        worker.finished_with_result.connect(self._finish_protective_backup)
        worker.finished.connect(self._protective_backup_thread_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_protective_backup_saved(self, backup_path: str):
        try:
            mbox = QtWidgets.QMessageBox(self)
            mbox.setWindowTitle(QCoreApplication.translate("Nugget", "Protective Backup Complete"))
            mbox.setIcon(QtWidgets.QMessageBox.Information)
            mbox.setText(QCoreApplication.translate(
                "Nugget", "Protective backup complete."))
            mbox.setInformativeText(
                QCoreApplication.translate(
                    "Nugget", "Saved at: {0}").format(backup_path)
                + "\n" + QCoreApplication.translate(
                    "Nugget",
                    "This is a selective backup (photos, messages, contacts, "
                    "settings, keychain) — not a full backup. For maximum "
                    "safety, also run a Full Backup."))
            mbox.exec()
        except Exception:
            pass

    def _finish_protective_backup(self, success: bool, error_msg: str = ""):
        self._protective_backup_in_progress = False
        self._mirror_backup_finish(success)
        if not success or error_msg:
            try:
                self.alert_message(ApplyAlertMessage(
                    txt=f"Protective backup: {error_msg or 'failed'}",
                    title="Protective backup",
                    icon=QtWidgets.QMessageBox.Critical,
                ), log_to_console=False)
            except Exception:
                pass

    def _protective_backup_thread_finished(self):
        try:
            self._protective_backup_thread = None
        except Exception:
            pass


    def _start_gestalt_apply(self):
        """WorkSlop: apply only the MobileGestalt tweaks (Nugget's gestalt flow)."""
        from src.gui.thread_workers.apply_worker import GestaltApplyThread
        if getattr(self, '_gestalt_apply_in_progress', False):
            return
        if (self.apply_in_progress
                or getattr(self, '_cache_restore_in_progress', False)
                or getattr(self, '_full_restore_in_progress', False)
                or getattr(self, '_full_backup_in_progress', False)):
            self.alert_message(ApplyAlertMessage(
                txt="Cannot apply MobileGestalt tweaks while another operation is in progress.",
                title="MobileGestalt",
                icon=QtWidgets.QMessageBox.Warning,
            ), log_to_console=False)
            return
        if not self.device_manager.get_current_device_is_gestalt_supported():
            self.alert_message(ApplyAlertMessage(
                txt="MobileGestalt tweaks are not supported on this iOS build.\n\n"
                    "MobileGestalt is open on iOS 16.0 through iOS 26.2 beta 1 only.",
                title="MobileGestalt",
                icon=QtWidgets.QMessageBox.Warning,
            ), log_to_console=False)
            return
        self._gestalt_apply_in_progress = True
        worker = GestaltApplyThread(manager=self.device_manager)
        self._gestalt_apply_thread = worker
        worker.progress.connect(self._update_restore_label)
        worker.alert.connect(self.alert_message)
        worker.finished_with_result.connect(self._finish_gestalt_apply)
        worker.finished.connect(self._gestalt_apply_thread_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _finish_gestalt_apply(self, success: bool, error_msg: str = ""):
        self._gestalt_apply_in_progress = False
        try:
            self._update_restore_label(
                QCoreApplication.translate("Nugget", "MobileGestalt applied.")
                if success else
                QCoreApplication.translate("Nugget", "MobileGestalt failed."))
        except Exception:
            pass

    def _gestalt_apply_thread_finished(self):
        try:
            self._gestalt_apply_thread = None
        except Exception:
            pass


    def _update_restore_label(self, txt: str):
        try:
            self.ios_home.show_process_status(txt)
            self.ios_backup.set_process_status(txt)
        except Exception:
            pass

    def _mirror_backup_finish(self, success: bool):
        """Settle the Backup page's bottom progress strip when a
        backup/restore run ends (same runs that report above)."""
        try:
            self.ios_backup.finish_process_status(success)
        except Exception:
            pass


    def _finish_cache_restore(self, success: bool, error_msg: str = ""):
        self._cache_restore_in_progress = False
        self._mirror_backup_finish(success)
        if not success or error_msg:
            try:
                self.alert_message(ApplyAlertMessage(
                    txt=f"Restore data: {error_msg or 'failed'}",
                    title="Restore data",
                    icon=QtWidgets.QMessageBox.Critical,
                ), log_to_console=False)
            except Exception:
                pass


    def _cache_restore_thread_finished(self):
        # run() returned, so the native thread is done; drop the window's
        # reference (deleteLater is already queued via the other connection).
        try:
            self._cache_restore_thread = None
        except Exception:
            pass


    def on_password_request(self, title: str, label: str, box):
        try:
            password, ok = QtWidgets.QInputDialog.getText(
                self, title, label, QtWidgets.QLineEdit.Password)
            box.put(password if (ok and password) else None)
        except Exception:
            try:
                box.put(None)
            except Exception:
                pass


    def on_choice_prompt(self, title: str, text: str, box):
        """Main-thread Abort/Resume dialog (e.g. device locked too long after
        the security recovery). Built here — never on the worker thread — and
        the decision is boxed back to the waiting worker."""
        try:
            mbox = QtWidgets.QMessageBox(self)
            mbox.setWindowTitle(title)
            mbox.setIcon(QtWidgets.QMessageBox.Warning)
            mbox.setText(text)
            abort_btn = mbox.addButton(
                QCoreApplication.tr("Abort"), QtWidgets.QMessageBox.RejectRole)
            resume_btn = mbox.addButton(
                QCoreApplication.tr("Resume"), QtWidgets.QMessageBox.AcceptRole)
            mbox.setDefaultButton(resume_btn)
            mbox.exec()
            result = "abort" if mbox.clickedButton() is abort_btn else "resume"
        except Exception:
            result = "abort"
        try:
            box.put(result)
        except Exception:
            pass


    def finish_apply_thread(self, success: bool = False, error_msg: str = ""):
        self.apply_in_progress = False
        self.toggle_thread_btns(disabled=False)
        worker = getattr(self, 'worker_thread', None)
        is_reset = worker is not None and worker.reset_pages is not None
        # Show completion indicator on the iOS home page
        try:
            if success:
                self.ios_home.show_process_status(
                    QCoreApplication.tr("Reset complete!") if is_reset else QCoreApplication.tr("Apply complete!"),
                    success=True)
            else:
                self.ios_home.show_process_status(
                    QCoreApplication.tr("Operation failed"), success=False)
        except Exception:
            pass
        if success:
            if worker is not None and not is_reset:
                self.prompt_star_on_github()
        else:
            # Show error notification if not already shown via alert
            if error_msg and "timed out" not in error_msg.lower():
                self.alert_message(ApplyAlertMessage(
                    txt=f"Operation failed: {error_msg}",
                    title="Error",
                    icon=QtWidgets.QMessageBox.Critical
                ), log_to_console=False)


    def prompt_star_on_github(self):
        if self.settings.value("star_prompt_done", False, type=bool):
            return
        self.settings.setValue("star_prompt_done", True)
        self._sync_settings()
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle(self.tr("Enjoying WorkSlop Desktop?"))
        box.setText(self.tr("If you like WorkSlop Desktop, please consider giving it a star on GitHub!"))
        star_btn = box.addButton(self.tr("Star on GitHub"), QtWidgets.QMessageBox.AcceptRole)
        box.addButton(self.tr("Not now"), QtWidgets.QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == star_btn:
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QtCore.QUrl("https://github.com/adnan120hz/desk"))


    def prompt_first_launch_backup(self) -> bool:
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle(QCoreApplication.translate("Nugget", "Back up your device"))
        box.setText(QCoreApplication.translate(
            "Nugget",
            "Have you made a backup of your iPhone? Tweaks and daemon changes "
            "are risky — a bad tweak can bootloop the device or force a full "
            "restore, which erases everything. Create a backup in iTunes or "
            # REAUDIT FIX: dialog text said "GoldenNugget" — user-visible.
            "Finder before using WorkSlop Desktop."))
        box.setDetailedText(QCoreApplication.translate(
            "Nugget",
            "Back up your iPhone before tweaking:\n"
            "• Windows: iTunes → your device → Back Up Now\n"
            "• Mac: Finder → your device → Back Up Now\n\n"
            # REAUDIT FIX: dialog text said "GoldenNugget" — user-visible.
            "WorkSlop Desktop's own protected backup also runs automatically when "
            "you apply tweaks, but a full iTunes/Finder backup is the only "
            "complete safety net."))
        # Explicit opaque background: the dialog inherits the app's global
        # ``QWidget { background-color: transparent }`` rule otherwise and
        # would render see-through.
        c = ColorThemeManager.instance().colors
        box.setStyleSheet(f"""
            QMessageBox {{ background-color: {c.bg_elevated}; }}
            QLabel {{ color: {c.text_primary}; background: transparent; }}
            QPushButton {{
                background-color: {c.bg_secondary};
                color: {c.text_primary};
                border: 1px solid {c.border};
                border-radius: 6px;
                padding: 6px 16px;
                min-width: 80px;
            }}
            QPushButton:hover {{ background-color: {c.surface_hover}; }}
            QPushButton:pressed {{ background-color: {c.border}; }}
        """)
        got_it = box.addButton(
            QCoreApplication.translate("Nugget", "Got it, I'm backed up"),
            QtWidgets.QMessageBox.AcceptRole)
        box.addButton(
            QCoreApplication.translate("Nugget", "I'll do it later"),
            QtWidgets.QMessageBox.RejectRole)
        # Make sure the dialog comes to the front and grabs input focus
        # (otherwise clicks can be swallowed by the window around it).
        box.raise_()
        box.activateWindow()
        box.exec()
        return box.clickedButton() is got_it


    def toggle_thread_btns(self, disabled: bool):
        if disabled or not self.apply_in_progress:
            self.ios_apply.set_busy(disabled)
        if disabled or not self.refresh_in_progress:
            self.ui.refreshBtn.setDisabled(disabled)

