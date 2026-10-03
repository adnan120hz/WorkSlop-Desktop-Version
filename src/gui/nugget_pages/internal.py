"""Internal page, Full Nugget shell.

Port of leminlimez/Nugget v7.4.1 ``src/gui/pages/tools/internal.py``:
same radio rows in the same order on the vendored form. Two upstream
rows are hidden instead of wired, because this app removed their
payloads: Metal HUD (``MetalForceHudEnabled``, removed by audit B28)
and Search Disabled Domains (``DisableSearchingWebsites``, tombstoned
in REMOVED_TWEAK_IDS). Everything else binds to the registry loader.
"""
from src.gui.pages.page import Page
from src.qt.nugget741_ui import Ui_Nugget741
from src.tweaks.tweak_loader import load_plist_tweaks
from src.tweaks.tweaks import TweakID


class NuggetInternalPage(Page):
    def __init__(self, ui: Ui_Nugget741):
        super().__init__()
        self.ui = ui

    def load_page(self):
        # Tombstoned payloads: their upstream rows are hidden, never dead.
        for name in ("metalHUDContent", "searchDisabledDomainsContent"):
            widget = getattr(self.ui, name, None)
            if widget is not None:
                widget.hide()

        # Create the radio buttons where needed
        self.createRadioBtns(key=TweakID.SBBuildNumber, container=self.ui.buildVersionBtns)
        self.createRadioBtns(key=TweakID.RTL, container=self.ui.RTLBtns)
        self.createRadioBtns(key=TweakID.LTR, container=self.ui.LTRBtns)
        self.createRadioBtns(key=TweakID.SBIconVisibility, container=self.ui.sbIconVisibilityBtns)
        self.createRadioBtns(key=TweakID.KeyFlick, container=self.ui.keyFlickBtns)

        self.createRadioBtns(key=TweakID.DisableSecondsHand, container=self.ui.disableSecondsHandBtns)
        self.createRadioBtns(key=TweakID.ShowButtonHints, container=self.ui.hintsVisibleBtns)

        self.createRadioBtns(key=TweakID.iMessageDiagnosticsEnabled, container=self.ui.iMessageBtns)
        self.createRadioBtns(key=TweakID.IDSDiagnosticsEnabled, container=self.ui.IDSBtns)
        self.createRadioBtns(key=TweakID.VCDiagnosticsEnabled, container=self.ui.VCBtns)
        self.createRadioBtns(key=TweakID.AccessoryDeveloperEnabled, container=self.ui.accessoryDevBtns)

        self.createRadioBtns(key=TweakID.AppStoreDebug, container=self.ui.appStoreBtns)
        self.createRadioBtns(key=TweakID.NotesDebugMode, container=self.ui.notesBtns)

        self.createRadioBtns(key=TweakID.BKDigitizerVisualizeTouches, container=self.ui.showTouchesBtns)
        self.createRadioBtns(key=TweakID.BKHideAppleLogoOnLaunch, container=self.ui.hideRespringBtns)
        self.createRadioBtns(key=TweakID.EnableWakeGestureHaptic, container=self.ui.wakeVibrateBtns)
        self.createRadioBtns(key=TweakID.PlaySoundOnPaste, container=self.ui.pasteSoundBtns)
        self.createRadioBtns(key=TweakID.AnnounceAllPastes, container=self.ui.notifyPastesBtns)

        load_plist_tweaks()
