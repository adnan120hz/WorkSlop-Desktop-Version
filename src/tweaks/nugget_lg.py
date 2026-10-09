"""Liquid Glass Tweaks (Nugget) — the original Nugget set, verbatim.

User order 2026-10-03: next to the WorkSlop v4 Liquid Glass set (which
stays byte-identical and is NOT touched by this module), the app carries
Nugget's own Liquid Glass tweaks exactly as shipped in leminlimez/Nugget
v7.4.1 (tag v7.4.1, commit 26e0c50ec114ca3a4ff6ab2fb4ae309abfd39fa1):

* the eight plist tweaks from ``load_liquidglass()``
  (upstream ``src/tweaks/tweak_loader.py`` lines 381-419), and
* the eight Solarium FeatureFlag tweaks from ``load_featureflags()``
  (same file, lines 203-213) — eight tweak objects writing nine
  flags into FeatureFlags/Global.plist (IconServices carries two:
  EnhancedGlass + SolariumCornerRadius), each ``{'Enabled': False}``,

shown only in the Nugget interfaces (second and third UI), at the
bottom of the Liquid Glass section, under "Liquid Glass Tweaks
(Nugget)". Keys, file locations, values, types, delivery and reset
semantics are Nugget's own — nothing is adapted to WorkSlop
conventions; the only WorkSlop code here is the registry of the tweak
objects and the row metadata the UI glue renders.

Audit 16 (2026-10-09): the three Feature-Flag GROUP labels and the
per-tweak titles in ``NUGGET_LG_TITLES`` are WorkSlop's honest
rewording, NOT upstream's text. Upstream labels these switches
"Disable …", promising an on-device effect; all this app proves is
that it writes ``{'Enabled': False}`` records into
FeatureFlags/Global.plist, so the labels now say exactly that
("Write FeatureFlags: … — file write only, no device effect
promised"). Group membership, categories, flag names, inverted
semantics and every staged byte are unchanged (proven by
tools/test_audit16_ff_honest_labels.py).

Upstream class note: the constructors below call this repo's
``BasicPlistTweak`` / ``FeatureFlagTweak`` (src/tweaks/tweak_classes.py)
whose payload logic is identical to upstream's (verified line-for-line
against v7.4.1: same staging into the global-preferences plist dict and
the same ``{'Enabled': ...}`` feature-flag records). Constructor
arguments are copied verbatim from the upstream loader.

Reset semantics follow upstream exactly: a tweak set to "Default"
(``set_enabled(False)``) stages nothing; "Enabled"/"Disabled" stage the
key with the value upstream's radio buttons write
(``tweak.set_value(not invert_values)`` / ``tweak.set_value(invert_values)``,
upstream ``src/gui/pages/page.py`` createRadioBtns). The three
Feature-Flag group switches mirror upstream's feature-flags page
handlers (``src/gui/pages/tools/featureflags.py``): each switch calls
``set_enabled`` on the same 3/3/2 tweaks upstream groups together.
"""
from .basic_plist_locations import FileLocation
from .tweak_classes import BasicPlistTweak, FeatureFlagTweak
from .tweaks import tweaks
from .tweak_names import TweakID


def _nugget_lg_definitions() -> dict:
    """The 16 tweak definitions, upstream arguments verbatim."""
    return {
        # --- load_liquidglass() (upstream tweak_loader.py:385-417) ---
        TweakID.NuggetForceSolariumFallback: BasicPlistTweak(
            FileLocation.globalPreferences,
            "SolariumForceFallback"
        ),
        TweakID.NuggetDisableSolarium: BasicPlistTweak(
            FileLocation.globalPreferences,
            "com.apple.SwiftUI.DisableSolarium"
        ),
        TweakID.NuggetIgnoreSolariumLinkedOnCheck: BasicPlistTweak(
            FileLocation.globalPreferences,
            "com.apple.SwiftUI.IgnoreSolariumLinkedOnCheck"
        ),
        TweakID.NuggetNoLiquidClock: BasicPlistTweak(
            FileLocation.globalPreferences,
            "SBDisallowGlassTime"
        ),
        TweakID.NuggetNoLiquidDock: BasicPlistTweak(
            FileLocation.globalPreferences,
            "SBDisableGlassDock"
        ),
        TweakID.NuggetDisableSpecularMotion: BasicPlistTweak(
            FileLocation.globalPreferences,
            "SBDisableSpecularEverywhereUsingLSSAssertion"
        ),
        TweakID.NuggetDisableOuterRefraction: BasicPlistTweak(
            FileLocation.globalPreferences,
            "SolariumDisableOuterRefraction"
        ),
        TweakID.NuggetDisableSolariumHDR: BasicPlistTweak(
            FileLocation.globalPreferences,
            "SolariumAllowHDR",
            value=False
        ),
        # --- Solarium feature flags (upstream tweak_loader.py:203-213) ---
        TweakID.NuggetSolariumFFSwiftUI: FeatureFlagTweak(flag_category='SwiftUI', flag_names=['Solarium'], inverted=True),
        TweakID.NuggetSolariumFFSpringBoard: FeatureFlagTweak(flag_category='SpringBoard', flag_names=['SolariumElasticHUD'], inverted=True),

        TweakID.NuggetSolariumFFIconServices: FeatureFlagTweak(flag_category='IconServices', flag_names=['EnhancedGlass', 'SolariumCornerRadius'], inverted=True),

        TweakID.NuggetSolariumFFDocumentCamera: FeatureFlagTweak(flag_category='DocumentCamera', flag_names=['CaptureLiquidGlass'], inverted=True),
        TweakID.NuggetSolariumFFPhotos: FeatureFlagTweak(flag_category='Photos', flag_names=['SolariumGridMagicPocket'], inverted=True),
        TweakID.NuggetSolariumFFAppleMediaServices: FeatureFlagTweak(flag_category='AppleMediaServices', flag_names=['Solarium'], inverted=True),

        TweakID.NuggetSolariumFFSharing: FeatureFlagTweak(flag_category='Sharing', flag_names=['ShareSheetSolarium'], inverted=True),
        TweakID.NuggetSolariumFFMail: FeatureFlagTweak(flag_category='Mail', flag_names=['SolariumSearch'], inverted=True),
    }


def load_nugget_lg_tweaks():
    """Register the Nugget Liquid Glass tweaks (idempotent).

    Mirrors upstream's ``if TweakID.DisableSolarium in tweaks: return``
    guard on the set's own first ID, so repeated calls never replace
    live tweak objects (and their enabled state).
    """
    if TweakID.NuggetDisableSolarium in tweaks:
        return
    tweaks.update(_nugget_lg_definitions())


# Row metadata for the "Liquid Glass Tweaks (Nugget)" subsection.
# Titles are upstream's own UI labels (src/qt/mainwindow.ui of Nugget
# v7.4.1); ``invert`` matches upstream's createRadioBtns wiring
# (only DisableSolariumHDR is created with invert_values=True,
# upstream src/gui/pages/tools/liquidglass.py).
NUGGET_LG_PLIST_ROWS = [
    (TweakID.NuggetForceSolariumFallback, "Force Solarium Fallback", False),
    (TweakID.NuggetDisableSolarium, "Disable Liquid Glass", False),
    (TweakID.NuggetIgnoreSolariumLinkedOnCheck, "Ignore Liquid Glass App Build Check", False),
    (TweakID.NuggetNoLiquidClock, "Disable Liquid Glass on LS Clock", False),
    (TweakID.NuggetNoLiquidDock, "Disable Liquid Glass on Dock", False),
    (TweakID.NuggetDisableSpecularMotion, "Disable Specular Motion", False),
    (TweakID.NuggetDisableOuterRefraction, "Disable Outer Refraction", False),
    (TweakID.NuggetDisableSolariumHDR, "Disable Solarium HDR", True),
]

# Feature-Flag group switches: upstream's three groupings and the
# exact tweak groups their handlers toggle (featureflags.py) — but
# Audit 16: the labels are WorkSlop's honest rewording (see module
# docstring). Each switch only writes {'Enabled': False} records for
# its flags into FeatureFlags/Global.plist; no on-device effect is
# promised, so no label may start with "Disable".
NUGGET_LG_FF_GROUPS = [
    ("Write FeatureFlags: Solarium off (SwiftUI, SpringBoard, IconServices)"
     " — file write only, no device effect promised",
     [TweakID.NuggetSolariumFFSwiftUI,
      TweakID.NuggetSolariumFFSpringBoard,
      TweakID.NuggetSolariumFFIconServices]),
    ("Write FeatureFlags: glass flags off (DocumentCamera, Photos,"
     " AppleMediaServices) — file write only, no device effect promised",
     [TweakID.NuggetSolariumFFDocumentCamera,
      TweakID.NuggetSolariumFFPhotos,
      TweakID.NuggetSolariumFFAppleMediaServices]),
    ("Write FeatureFlags: glass flags off (Sharing, Mail)"
     " — file write only, no device effect promised",
     [TweakID.NuggetSolariumFFSharing,
      TweakID.NuggetSolariumFFMail]),
]

# Per-tweak display titles (Audit 16 honest wording): each names the
# exact FeatureFlags record the tweak writes when enabled.
NUGGET_LG_TITLES = {
    TweakID.NuggetSolariumFFSwiftUI: "Write FeatureFlags: SwiftUI/Solarium = off",
    TweakID.NuggetSolariumFFSpringBoard: "Write FeatureFlags: SpringBoard/SolariumElasticHUD = off",
    TweakID.NuggetSolariumFFIconServices: "Write FeatureFlags: IconServices/EnhancedGlass + SolariumCornerRadius = off",
    TweakID.NuggetSolariumFFDocumentCamera: "Write FeatureFlags: DocumentCamera/CaptureLiquidGlass = off",
    TweakID.NuggetSolariumFFPhotos: "Write FeatureFlags: Photos/SolariumGridMagicPocket = off",
    TweakID.NuggetSolariumFFAppleMediaServices: "Write FeatureFlags: AppleMediaServices/Solarium = off",
    TweakID.NuggetSolariumFFSharing: "Write FeatureFlags: Sharing/ShareSheetSolarium = off",
    TweakID.NuggetSolariumFFMail: "Write FeatureFlags: Mail/SolariumSearch = off",
}
