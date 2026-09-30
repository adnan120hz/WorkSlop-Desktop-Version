from .tweak_names import TweakID
from .tweak_classes import (
    BasicPlistTweak, AdvancedPlistTweak, NullifyFileTweak,
    MobileGestaltTweak, MobileGestaltPickerTweak,
    MobileGestaltMultiTweak, MobileGestaltCacheDataTweak,
    FeatureFlagTweak,
)
from .posterboard.posterboard_tweak import PosterboardTweak
from .posterboard.template_options.templates_tweak import TemplatesTweak
from .status_bar.status_bar_tweak import StatusBarTweak
from .icon_themes.icon_themes_tweak import IconThemesTweak
from .eligibility_tweak import EligibilityTweak, AITweak, BookRestoreFileTweak
from .registry import SPECS_BY_ID
    
tweaks = {
    ## PosterBoard
    TweakID.PosterBoard: PosterboardTweak(),

    ## Templates
    TweakID.Templates: TemplatesTweak(),

    ## Status Bar
    TweakID.StatusBar: StatusBarTweak(),

    ## Icon Themes
    TweakID.IconThemes: IconThemesTweak(),

    ## Creating the folders for BookRestore
    # (ported from leminlimez/Nugget's tweaks.py; in Nugget this entry lives
    # in the main tweaks dict, not in load_eligibility())
    TweakID.CreateBRFolders: BookRestoreFileTweak(),
}


# Mutually-exclusive pairs whose tweaks are NOT registry specs, so they cannot
# carry ``excludes`` on a TweakSpec. Declared here next to the enforcement
# helper instead. Both directions are listed explicitly.
_EXTRA_EXCLUSIONS = {
    TweakID.EnableLGLPM: (TweakID.DisableLGLPM,),
    TweakID.DisableLGLPM: (TweakID.EnableLGLPM,),
}


def set_tweak_enabled(tweak_id: TweakID, enabled: bool) -> None:
    """Set a tweak's enabled state, enforcing mutual exclusion.

    Enabling one side of an Enable/Disable (or RTL/LTR) pair automatically
    disables the other side, so the apply payload can never contain both
    contradictory values. Registry pairs declare their partners via
    ``TweakSpec.excludes``; non-registry pairs (e.g. the MobileGestalt LGLPM
    switches) are covered by ``_EXTRA_EXCLUSIONS`` above.
    """
    tw = tweaks.get(tweak_id)
    if tw is None:
        return
    tw.set_enabled(enabled)
    if not enabled:
        return
    excluded = list(_EXTRA_EXCLUSIONS.get(tweak_id, ()))
    spec = SPECS_BY_ID.get(tweak_id)
    if spec is not None:
        excluded.extend(spec.excludes)
    for other_id in excluded:
        other = tweaks.get(other_id)
        if other is not None and getattr(other, "enabled", False):
            other.set_enabled(False)