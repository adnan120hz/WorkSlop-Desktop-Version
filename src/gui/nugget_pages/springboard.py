"""Springboard page, Full Nugget shell.

Port of leminlimez/Nugget v7.4.1 ``src/gui/pages/tools/springboard.py``:
same widgets of the vendored form, same handlers. Adaptations are
bindings only: upstream's ``load_springboard()`` becomes this app's
registry loader, and the lock-screen auto-lock slider row is hidden —
its tweak (``SBMinimumLockscreenIdleTime``) is a tombstoned Settings
duplicate in this app (REMOVED_TWEAK_IDS), so the row is removed
instead of being left wired to a payload that must never apply. The
floating tab bar row is hidden the same way: its tweak
(``UseFloatingTabBar``) is a ``disabled=True`` registry spec (dead key
on iPadOS 26.4+), so it is never registered in ``tweaks`` and a wired
radio would raise ``KeyError`` on click (Audit 99/56).
"""
from src.gui.pages.page import Page
from src.qt.nugget741_ui import Ui_Nugget741
from src.tweaks.tweak_loader import load_plist_tweaks
from src.tweaks.tweaks import tweaks, TweakID


class NuggetSpringboardPage(Page):
    def __init__(self, ui: Ui_Nugget741):
        super().__init__()
        self.ui = ui

    def load_page(self):
        self.ui.footnoteTxt.textEdited.connect(self.on_footnoteTxt_textEdited)
        self.ui.watchOSChk.toggled.connect(self.on_watchOSChk_toggled)

        # Rows whose tweaks this app tombstoned stay hidden, not dead.
        # floatingTabBarContent: UseFloatingTabBar is a disabled registry
        # spec (never registered, never applied) — hide its row instead
        # of wiring radios to a tweak that does not exist (Audit 99/56).
        for name in ("autoLockLbl", "lockScreenAutoLockSlider",
                     "lockScreenAutoLockSeparator",
                     "floatingTabBarContent"):
            widget = getattr(self.ui, name, None)
            if widget is not None:
                widget.hide()

        # create the radio buttons
        self.createRadioBtns(key=TweakID.AirDropDisableTimeLimit, container=self.ui.airdropTimeLimitBtns)
        self.createRadioBtns(key=TweakID.SBDontLockAfterCrash, container=self.ui.disableLockRespringBtns)
        self.createRadioBtns(key=TweakID.SBDontDimOrLockOnAC, container=self.ui.disableDimmingBtns)
        self.createRadioBtns(key=TweakID.SBHideLowPowerAlerts, container=self.ui.lowBatteryAlertsBtns)
        self.createRadioBtns(key=TweakID.SBHideACPower, container=self.ui.hideACPowerBtns)
        self.createRadioBtns(key=TweakID.SBNeverBreadcrumb, container=self.ui.disableCrumbBtns)
        self.createRadioBtns(key=TweakID.SBShowSupervisionTextOnLockScreen, container=self.ui.supervisionTextBtns)
        self.createRadioBtns(key=TweakID.AirplaySupport, container=self.ui.enableAirPlayBtns)
        self.createRadioBtns(key=TweakID.SBAlwaysShowSystemApertureInSnapshots, container=self.ui.showDIInScreenshotsBtns)
        self.createRadioBtns(key=TweakID.HideDICompletely, container=self.ui.hideDICompletelyBtns)

        self.createRadioBtns(key=TweakID.SBShowAuthenticationEngineeringUI, container=self.ui.authEngUIBtns)
        # No radios for UseFloatingTabBar: its spec is disabled=True, so
        # the tweak is never in ``tweaks`` and any wired radio would
        # KeyError on click. Its row (floatingTabBarContent) is hidden
        # above with the other tombstoned rows.

        load_plist_tweaks()

    ## ACTIONS
    def on_footnoteTxt_textEdited(self, text: str):
        tweaks[TweakID.LockScreenFootnote].set_value(text, toggle_enabled=True)

    def on_watchOSChk_toggled(self, checked: bool):
        tweaks[TweakID.WatchOSCompatibility].set_enabled(checked)
