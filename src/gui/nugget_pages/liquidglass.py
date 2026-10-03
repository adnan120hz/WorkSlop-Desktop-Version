"""Liquid Glass page, Full Nugget shell.

Port of leminlimez/Nugget v7.4.1 ``src/gui/pages/tools/liquidglass.py``
(24 lines there; same eight radio rows, same order, same containers of
the vendored form). The one adaptation is the binding: upstream's rows
drive upstream ``TweakID.*`` entries, here they drive this app's
verbatim Nugget set (``Nugget*`` IDs, ``src/tweaks/nugget_lg.py``) with
the identical ``set_value``/``set_enabled`` operations upstream's
``createRadioBtns`` performs — payloads are untouched.

Upstream parks its Solarium FeatureFlag switches on a separate
FeatureFlags page the classic sidebar has no entry for, so — exactly
like the second interface's subsection — the three group switches ride
at the bottom of this page, wired with upstream's own groupings and
labels (``NUGGET_LG_FF_GROUPS``).
"""
from PySide6.QtWidgets import QCheckBox, QLabel

from src.gui.pages.page import Page
from src.qt.nugget741_ui import Ui_Nugget741
from src.tweaks.nugget_lg import (
    NUGGET_LG_FF_GROUPS, NUGGET_LG_PLIST_ROWS, load_nugget_lg_tweaks,
)
from src.tweaks.tweaks import tweaks

# Upstream row order (liquidglass.py) mapped onto the vendored form's
# per-row radio containers; identical to NUGGET_LG_PLIST_ROWS order.
_CONTAINERS = (
    "forceSolariumFallbackBtns",
    "disableSolariumBtns",
    "ignoreSolariumAppBuildBtns",
    "noLiquidClockBtns",
    "noLiquidDockBtns",
    "disableSpecularBtns",
    "disableOuterRefractionBtns",
    "disableSolariumHDRBtns",
)


class NuggetLiquidGlassPage(Page):
    def __init__(self, ui: Ui_Nugget741):
        super().__init__()
        self.ui = ui

    def load_page(self):
        load_nugget_lg_tweaks()
        # Create the radio buttons where needed (upstream wiring, same
        # order; only DisableSolariumHDR passes invert_values=True).
        for (tweak_id, _title, invert), container_name in zip(
                NUGGET_LG_PLIST_ROWS, _CONTAINERS):
            self.createRadioBtns(key=tweak_id,
                                 container=getattr(self.ui, container_name),
                                 invert_values=invert)
        self._build_feature_flag_switches()

    def _build_feature_flag_switches(self):
        layout = self.ui.liquidGlassPageContent.layout()
        if layout is None:
            return
        header = QLabel("Feature Flags", self.ui.liquidGlassPageContent)
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)
        for title, tweak_ids in NUGGET_LG_FF_GROUPS:
            chk = QCheckBox(title, self.ui.liquidGlassPageContent)
            chk.setChecked(all(tweaks[t].enabled for t in tweak_ids))
            chk.toggled.connect(
                lambda checked, ids=tweak_ids:
                    self._set_ff_group(ids, checked))
            layout.addWidget(chk)

    @staticmethod
    def _set_ff_group(tweak_ids, checked: bool):
        # Upstream featureflags.py handlers call set_enabled on each
        # member of the group; mirror that here.
        for tweak_id in tweak_ids:
            tweaks[tweak_id].set_enabled(checked)
