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