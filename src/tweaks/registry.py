"""Single source of truth for the plist-based tweaks.

Every tweak's definition (id, section, title, plist location, key, default
value, UI kind) lives here exactly once. ``tweak_loader`` builds the runtime
instances from these specs and the iOS tweaks page renders its rows from
them — adding a tweak means adding one entry here.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from PySide6.QtCore import QT_TRANSLATE_NOOP

from .basic_plist_locations import FileLocation
from .tweak_names import TweakID


class Section(Enum):
    LIQUID_GLASS = "Liquid Glass"
    SPRINGBOARD = "SpringBoard"
    FEATURE_FLAGS = "Feature Flags"
    INTERNAL = "Internal Options"


class Kind(Enum):
    SWITCH = "switch"   # boolean toggle
    TEXT = "text"       # free-form text value
    NUMBER = "number"   # numeric value


# Feature (page) key each registry Section belongs to. Feeds HotLoad's
# FEATURE_TWEAKS so every registry tweak automatically joins its feature;
# the Sidebar uses the same keys to know which page owns a section.
SECTION_FEATURES: dict[Section, str] = {
    Section.LIQUID_GLASS: "Liquid Glass",
    Section.SPRINGBOARD: "Springboard",
    Section.FEATURE_FLAGS: "Feature Flags",
    Section.INTERNAL: "Internal",
}


@dataclass(frozen=True)
class TweakSpec:
    id: TweakID
    section: Section
    title: str
    location: FileLocation
    key: str
    value: any = True          # value written when the tweak is enabled
    kind: Kind = Kind.SWITCH
    min_value: float = 0       # NUMBER kind only
    max_value: float = 999     # NUMBER kind only
    step: float = 1.0          # NUMBER kind only; not integral = decimal input
    min_version: Optional[str] = None
    max_version: Optional[str] = None
    iphone_only: bool = False
    ipad_only: bool = False
    factory: Optional[Callable[[], object]] = None  # overrides BasicPlistTweak
    description: Optional[str] = None  # detailed "what it does" tooltip
    disabled: bool = False  # True = tweak is cut off: never loaded, never applied, never rendered
    excludes: tuple = ()  # TweakIDs that must be turned off when this one is
                          # turned on (mutually-exclusive pairs, e.g. RTL/LTR).
                          # Enforced by set_tweak_enabled() in tweaks.py.


def _t(id_: TweakID, section: Section, title: str, location: FileLocation,
       key: str, description: str = "", **kwargs) -> TweakSpec:
    # QT_TRANSLATE_NOOP marks the title for pyside6-lupdate; the actual
    # translation happens at render time (translators are not installed yet
    # when this module is imported).
    return TweakSpec(id=id_, section=section,
                     title=QT_TRANSLATE_NOOP("Nugget", title),
                     description=QT_TRANSLATE_NOOP("Nugget", description) if description else None,
                     location=location, key=key, **kwargs)


def _watchos_compatibility():
    from .tweak_classes import AdvancedPlistTweak
    return AdvancedPlistTweak(
        FileLocation.nanoregistry,
        keyValues={
            "IOS_PAIRING_EOL_MIN_PAIRING_COMPATIBILITY_VERSION_CHIPIDS": "",
            "maxPairingCompatibilityVersion": 37,
            "lastRestoreIdentifier": "CD97EEB8-BCD2-486B-BC13-C384E6B916C4",  # not sure if this is needed
            "minPairingCompatibilityVersionWithChipID": 1,
            "lastRestoreIdentifier_state": 0,
            "AdvertisingIdentifierSeed": "85E70251-1960-4DA0-A321-B68AC118FAB5",  # this prolly isn't needed either
            "minPairingCompatibilityVersion": 1
        })


GP = FileLocation.globalPreferences


def _ff(id_: TweakID, title: str, flag_category: str, flag_names: list,
        description: str = "", **kwargs) -> TweakSpec:
    """Feature-flag tweak.

    GoldenNugget removed the whole feature-flags system; the definitions
    below (ClockAnim, Lockscreen, PhotoUI, AI, KioskMode) are ported verbatim
    from leminlimez/Nugget's ``load_featureflags()``.
    Round 5 (2026-10-01): the eight ``SolariumFF*`` Liquid Glass pairs that
    used to live here were deleted with the whole legacy Liquid Glass
    section — the feature-flags delivery channel is dead past iOS 26.1
    (specs are capped at ``max_version="26.1"``) and the entries were
    device-negative on iOS 26.6.1.
    The ``factory`` builds a ``FeatureFlagTweak`` which writes into
    ``/var/preferences/FeatureFlags/Global.plist`` during apply.
    That is the iOS 26-and-lower store. On iOS 27 Apple moved the
    feature-flag store to ``/var/preferences/FeatureFlags/Settings.plist``
    (sole path read by FeatureFlags.framework; no Global.plist fallback),
    and as of late Sep 2026 no working delivery channel for either path
    is publicly confirmed on iOS 27 — so these switches are experimental
    there and may silently do nothing. Community reports put the last
    writable iOS for the exploit-based Global.plist route at 26.1, so the
    specs are capped at ``max_version="26.1"``: fully supported on
    iOS 26.1 and lower, locked above.
    """
    from .tweak_classes import FeatureFlagTweak
    return TweakSpec(
        id=id_, section=Section.FEATURE_FLAGS,
        title=QT_TRANSLATE_NOOP("Nugget", title),
        description=QT_TRANSLATE_NOOP("Nugget", description) if description else None,
        location=FileLocation.featureflags, key="",
        factory=lambda: FeatureFlagTweak(
            flag_category=flag_category, flag_names=flag_names, **kwargs),
        # Exploit-based Global.plist route: last writable iOS is 26.1
        # (community reports). Above that the switches lock in the UI.
        max_version="26.1",
    )


_FF_SPECS: tuple[TweakSpec, ...] = (
    _ff(TweakID.ClockAnim, "Enable Lockscreen Clock Animation",
        'SpringBoard', ['SwiftUITimeAnimation'],
        description="Enables the SwiftUI time animation on the lockscreen clock."),
    _ff(TweakID.Lockscreen, "Enable Duplicate Lockscreen Button and Lockscreen Quickswitch",
        "SpringBoard", ['AutobahnQuickSwitchTransition', 'SlipSwitch', 'PosterEditorKashida'],
        description="Enables the duplicate lockscreen button and the lockscreen quick-switch transition."),
    _ff(TweakID.PhotoUI, "Enable Old Photo UI",
        'Photos', ['Lemonade'], is_list=False, inverted=True,
        description="Restores the old Photos app UI (disables the Lemonade redesign)."),
    _ff(TweakID.AI, "Enable Apple Intelligence",
        'SpringBoard', ['Domino', 'SuperDomino'],
        description="Enables the Apple Intelligence feature flags (Domino / SuperDomino)."),
    _ff(TweakID.KioskMode, "Enable Kiosk Mode",
        'PreferencesFramework', ['ForcedRetailKioskMode'],
        description="Forces retail kiosk mode."),
)

SPECS: tuple[TweakSpec, ...] = (
    # --- Liquid Glass ---
    # Round 5 (2026-10-01, revised per user order): section INTENTIONALLY
    # EMPTY. The user rejected the Tinted-only spec ("mendingan langsung
    # dari Settings saja") — the product must offer TRUE full-disable of
    # Liquid Glass or nothing at all. All 109 legacy specs were deleted as
    # fake/unproven/dead/misdirected. No spec may be added here until a
    # full-disable method is proven on-device on iOS 26.6.1 (stock,
    # non-jailbreak). Deep research for such a method is in progress.

    # --- SpringBoard ---
    _t(TweakID.LockScreenFootnote, Section.SPRINGBOARD, "Lock Screen Footnote Text",
       FileLocation.footnote, "LockScreenFootnote", value="", kind=Kind.TEXT,
       description=QT_TRANSLATE_NOOP("Nugget", "Sets custom text shown at the bottom of the Lock Screen below the time. Long text is cut off — keep it short. Leave empty to remove.")),
    _t(TweakID.WatchOSCompatibility, Section.SPRINGBOARD, "Allow pairing with any watchOS version",
       FileLocation.nanoregistry, "", factory=_watchos_compatibility,
       description=QT_TRANSLATE_NOOP("Nugget", "Removes the minimum watchOS pairing check in NanoRegistry so you can pair an Apple Watch running any watchOS version with your iPhone.")),
    _t(TweakID.AirDropDisableTimeLimit, Section.SPRINGBOARD, "Disable AirDrop Time Limit for Everyone Option",
       FileLocation.airdrop, "OverrideTimeLimitEveryoneMode",
       description=QT_TRANSLATE_NOOP("Nugget", "Unlocks the hidden 'Everyone' AirDrop receiving option that would normally be limited to a 10-minute time window.")),
    _t(TweakID.SBDontLockAfterCrash, Section.SPRINGBOARD, "Disable Lock After Respring",
       FileLocation.springboard, "SBDontLockAfterCrash",
       description=QT_TRANSLATE_NOOP("Nugget", "Prevents the screen from locking right after a respring — the phone won't ask for a passcode immediately after the UI reloads.")),
    _t(TweakID.SBDontDimOrLockOnAC, Section.SPRINGBOARD, "Disable Screen Dimming While Charging",
       FileLocation.springboard, "SBDontDimOrLockOnAC",
       description=QT_TRANSLATE_NOOP("Nugget", "Stops the display from auto-dimming while the device is connected to a charger.")),
    _t(TweakID.SBHideLowPowerAlerts, Section.SPRINGBOARD, "Disable Low Battery Alerts",
       FileLocation.springboard, "SBHideLowPowerAlerts",
       description=QT_TRANSLATE_NOOP("Nugget", "Suppresses the 'Low Battery — 20% / 10%' system alerts.")),
    _t(TweakID.SBHideACPower, Section.SPRINGBOARD, "Hide AC Power on Lock Screen",
       FileLocation.springboard, "SBHideACPower",
       description=QT_TRANSLATE_NOOP("Nugget", "Hides the charging status from the Lock Screen while the device is plugged into AC power.")),
    _t(TweakID.SBNeverBreadcrumb, Section.SPRINGBOARD, "Disable Breadcrumbs",
       FileLocation.springboard, "SBNeverBreadcrumb",
       description=QT_TRANSLATE_NOOP("Nugget", "Disables the 'Return to <App>' breadcrumb button that appears in the status bar after opening a link from another app.")),
    _t(TweakID.SBShowSupervisionTextOnLockScreen, Section.SPRINGBOARD, "Show Supervision Text on Lock Screen",
       FileLocation.springboard, "SBShowSupervisionTextOnLockScreen",
       description=QT_TRANSLATE_NOOP("Nugget", "Shows the device-supervision text on the Lock Screen, like the '<Device> is supervised by <org>' label seen on MDM-managed devices.")),
    _t(TweakID.AirplaySupport, Section.SPRINGBOARD, "Enable AirPlay support for Stage Manager",
       FileLocation.springboard, "SBExtendedDisplayOverrideSupportForAirPlayAndDontFileRadars",
       description=QT_TRANSLATE_NOOP("Nugget", "Adds extended-display AirPlay support for Stage Manager so apps and external displays can use the feature more broadly.")),
    _t(TweakID.SBMinimumLockscreenIdleTime, Section.SPRINGBOARD, "Auto‑Lock (Lock Screen)",
       FileLocation.springboard, "SBMinimumLockscreenIdleTime", value=5, kind=Kind.NUMBER,
       min_value=0, max_value=600,
       description=QT_TRANSLATE_NOOP("Nugget", "Sets how many minutes of inactivity before the Lock Screen turns the display off. 0 = never auto-lock.")),
    _t(TweakID.SBAlwaysShowSystemApertureInSnapshots, Section.SPRINGBOARD, "Show Dynamic Island in Screenshots",
       FileLocation.springboard, "SBAlwaysShowSystemApertureInSnapshots", min_version="17.4", iphone_only=True,
       description=QT_TRANSLATE_NOOP("Nugget", "Forces the Dynamic Island to appear in screenshots instead of being hidden or shrunk while the screenshot is taken.")),
    _t(TweakID.HideDICompletely, Section.SPRINGBOARD, "Hide Dynamic Island Completely",
       FileLocation.springboard, "SBSuppressDynamicIslandCompletely", min_version="17.4", iphone_only=True,
       description=QT_TRANSLATE_NOOP("Nugget", "Suppresses the Dynamic Island cutout completely so it is never drawn. Can make the screen look odd on devices with a pill cutout.")),
    _t(TweakID.SBShowAuthenticationEngineeringUI, Section.SPRINGBOARD, "Show Red/Green Authentication Line on Lock Screen",
       FileLocation.springboard, "SBShowAuthenticationEngineeringUI",
       description=QT_TRANSLATE_NOOP("Nugget", "Shows a red/green authentication progress indicator on the Lock Screen while Face ID or passcode checks are running (engineering debug UI).")),
    # DEAD 2026-10-01 (binary research): Apple removed the floating tab bar
    # (and this preference) in iPadOS 26.4 — the key is a stale no-op on
    # 26.6.1. Kept in the enum for history; never loaded, never applied,
    # never rendered.
    _t(TweakID.UseFloatingTabBar, Section.SPRINGBOARD, "Disable Floating Tab Bar",
       FileLocation.uikit, "UseFloatingTabBar", value=False, ipad_only=True, disabled=True,
       description=QT_TRANSLATE_NOOP("Nugget", "Uses the old fixed tab bar style instead of the floating tab bar on iPad. Enabled when the switch is OFF.")),
    _t(TweakID.SBDisableIconParallax, Section.SPRINGBOARD, "Disable Icon Parallax",
       FileLocation.springboard, "SBDisableParallax",
       description=QT_TRANSLATE_NOOP("Nugget", "Stops Home Screen icons from shifting with the device tilt (the parallax effect). Pair with Disable Icon Page-Control Parallax for a fully static Home Screen.")),
    _t(TweakID.SBHideSearchAffordance, Section.SPRINGBOARD, "Hide Search Button on Home Screen",
       FileLocation.springboard, "SBHomeScreenShowsSearchAffordance", value=False,
       description=QT_TRANSLATE_NOOP("Nugget", "Removes the search button below the icons on the Home Screen (the faint search bar/icon above the Dock). Enabled when the switch is ON.")),

    # --- Internal Options ---
    _t(TweakID.SBBuildNumber, Section.INTERNAL, "Show Build Version in Status Bar", GP, "UIStatusBarShowBuildVersion",
       description=QT_TRANSLATE_NOOP("Nugget", "Displays the iOS build number (e.g. 21A5284a) in the status bar next to the iOS version.")),
    _t(TweakID.RTL, Section.INTERNAL, "Force Right-to-Left Layout", GP, "NSForceRightToLeftWritingDirection",
       description=QT_TRANSLATE_NOOP("Nugget", "Forces a right-to-left layout for the entire system, mirroring the UI as if your primary language were RTL."),
       excludes=(TweakID.LTR,)),
    _t(TweakID.LTR, Section.INTERNAL, "Force Left-to-Right Layout", GP, "NSForceLeftToRightWritingDirection",
       description=QT_TRANSLATE_NOOP("Nugget", "Forces a left-to-right layout across the whole system regardless of the RTL language setting."),
       excludes=(TweakID.RTL,)),
    _t(TweakID.SBIconVisibility, Section.INTERNAL, "Show Hidden Icons on Home Screen", GP, "SBIconVisibility",
       description=QT_TRANSLATE_NOOP("Nugget", "Reveals hidden or disabled Home Screen icons, including internal placeholder icons that are normally not drawn.")),
    _t(TweakID.iMessageDiagnosticsEnabled, Section.INTERNAL, "iMessage Debugging", GP, "iMessageDiagnosticsEnabled",
       description=QT_TRANSLATE_NOOP("Nugget", "Enables the iMessage engineering debug menu / diagnostics inside the Messages app.")),
    _t(TweakID.IDSDiagnosticsEnabled, Section.INTERNAL, "Continuity Debugging", GP, "IDSDiagnosticsEnabled",
       description=QT_TRANSLATE_NOOP("Nugget", "Enables the Continuity engineering debug diagnostics in Settings (Apple ID and related sections).")),
    _t(TweakID.VCDiagnosticsEnabled, Section.INTERNAL, "FaceTime Debugging", GP, "VCDiagnosticsEnabled",
       description=QT_TRANSLATE_NOOP("Nugget", "Enables FaceTime / VoIP engineering debug diagnostics.")),
    _t(TweakID.AccessoryDeveloperEnabled, Section.INTERNAL, "Show Accessory Developer Settings", GP, "AccessoryDeveloperEnabled",
       description=QT_TRANSLATE_NOOP("Nugget", "Adds a hidden Accessory Developer settings page to the Settings app for testing accessories.")),
    # (ported from leminlimez/Nugget's load_internal(): BasicPlistTweak(FileLocation.globalPreferences, "GesturesEnabled"))
    _t(TweakID.KeyFlick, Section.INTERNAL, "Keyboard Key Flicks", GP, "GesturesEnabled",
       description=QT_TRANSLATE_NOOP("Nugget", "Enables the iPad-style keyboard keyflicks on iPhones.")),
    _t(TweakID.DisableSecondsHand, Section.INTERNAL, "Disable Clock Icon Seconds Hand", GP, "SBDisableClockIconSecondsHand",
       description=QT_TRANSLATE_NOOP("Nugget", "Stops the animated second hand on the Clock app's Home Screen icon.")),
    _t(TweakID.DisableSearchingWebsites, Section.INTERNAL, "Disable Spotlight Searching in Websites", GP, "SBSearchDisabledDomains",
       description=QT_TRANSLATE_NOOP("Nugget", "Removes website / web search results from Spotlight search suggestions.")),
    _t(TweakID.ShowButtonHints, Section.INTERNAL, "Show Hardware Button Hints in Screenshots", GP, "SBHardwareButtonHintDropletsAlwaysVisibleInSnapshots",
       description=QT_TRANSLATE_NOOP("Nugget", "Shows the side button / action button hint labels in screenshots (engineering debug UI).")),
    _t(TweakID.AppStoreDebug, Section.INTERNAL, "App Store Debug Gesture", FileLocation.appStore, "debugGestureEnabled",
       description=QT_TRANSLATE_NOOP("Nugget", "Enables the hidden debug gesture in the App Store app, used to dump store data and inspect the store backend.")),
    _t(TweakID.NotesDebugMode, Section.INTERNAL, "Notes Debug Mode", FileLocation.notes, "DebugModeEnabled",
       description=QT_TRANSLATE_NOOP("Nugget", "Turns on the Notes app debug menu for engineering debugging.")),
    _t(TweakID.BKDigitizerVisualizeTouches, Section.INTERNAL, "Show Touches With Debug Info", FileLocation.backboardd, "BKDigitizerVisualizeTouches",
       description=QT_TRANSLATE_NOOP("Nugget", "Visually marks every touch point on the screen with debugging information as you touch. Great for diagnosing touch issues.")),
    _t(TweakID.BKHideAppleLogoOnLaunch, Section.INTERNAL, "Hide Respring Icon", FileLocation.backboardd, "BKHideAppleLogoOnLaunch",
       description=QT_TRANSLATE_NOOP("Nugget", "Hides the Apple logo animation during respring, showing a black screen instead until the UI comes back.")),
    _t(TweakID.EnableWakeGestureHaptic, Section.INTERNAL, "Vibrate on Raise-to-Wake", FileLocation.coreMotion, "EnableWakeGestureHaptic",
       description=QT_TRANSLATE_NOOP("Nugget", "Plays a Taptic Engine vibration when the device wakes via the raise-to-wake gesture.")),
    _t(TweakID.PlaySoundOnPaste, Section.INTERNAL, "Play Sound on Paste", FileLocation.pasteboard, "PlaySoundOnPaste",
       description=QT_TRANSLATE_NOOP("Nugget", "Plays a sound every time content is pasted anywhere on the device.")),
    _t(TweakID.AnnounceAllPastes, Section.INTERNAL, "Show Notifications for System Pastes", FileLocation.pasteboard, "AnnounceAllPastes",
       description=QT_TRANSLATE_NOOP("Nugget", "Shows a system notification whenever an app reads the pasteboard, acting as a privacy indicator for system-level pastes.")),
    # === Round 6 (2026-10-02): 71 audited candidates, pre-beta developer release ===
    # WARNING: All unverified on device. See AUDIT-KANDIDAT-BARU.md.
    _t(TweakID.SolariumForceFallback, Section.LIQUID_GLASS, "Force Solarium Fallback", GP, "SolariumForceFallback",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Force iOS to use Liquid Glass fallback mode. Unverified — needs device test.")),
    _t(TweakID.DisableSolariumSwiftUI, Section.LIQUID_GLASS, "Disable Solarium (SwiftUI)", GP, "com.apple.SwiftUI.DisableSolarium",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disable Solarium for SwiftUI. Reader removed in 26.1 — likely non-functional.")),
    _t(TweakID.GlassLegibility2, Section.LIQUID_GLASS, "Glass Legibility Value 2", FileLocation.uikit, "UIViewGlassLegibilitySetting", value=2,
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Glass legibility value 2 = unobserved branch. 0=Clear, 1=Tinted (proven).")),
    _t(TweakID.SolariumFeatureFlags, Section.FEATURE_FLAGS, "Solarium Feature Flags", FileLocation.featureflags, "SolariumFlags",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "WARNING: Can break Control Center (full white). Developer only.")),
    _t(TweakID.DisallowGlassTime, Section.LIQUID_GLASS, "Disallow Glass on LS Clock", GP, "SBDisallowGlassTime",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disallow glass effect on Lock Screen clock.")),
    _t(TweakID.DisableGlassDock, Section.LIQUID_GLASS, "Disable Glass on Dock", GP, "SBDisableGlassDock",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disable Liquid Glass on Dock — solid style.")),
    _t(TweakID.FlatIconsEverywhere, Section.LIQUID_GLASS, "Flat Icons Everywhere", GP, "SBUseFlatIconsEverywhere",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Force all icons flat, no 3D/glass effect.")),
    _t(TweakID.DisableWidgetSpecular, Section.LIQUID_GLASS, "Disable Widget Specular", GP, "SBDisableWidgetSpecular",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Remove specular highlight from widgets.")),
    _t(TweakID.DisableDockSpecular, Section.LIQUID_GLASS, "Disable Dock Specular", GP, "SBDisableDockSpecular",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Remove specular highlight from dock.")),
    _t(TweakID.DisableFolderSpecular, Section.LIQUID_GLASS, "Disable Folder Specular", GP, "SBDisableFolderSpecular",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Remove specular highlight from folders.")),
    _t(TweakID.ExcludeClearGlassShadows, Section.LIQUID_GLASS, "Exclude Clear Glass Shadows", GP, "SBExcludeAllClearGlassShadows",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Remove all Clear Glass shadows.")),
    _t(TweakID.ExcludeDockShadow, Section.LIQUID_GLASS, "Exclude Dock Shadow", GP, "SBExcludeDockShadow",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Remove dock drop shadow.")),
    _t(TweakID.ExcludeSearchShadow, Section.LIQUID_GLASS, "Exclude Search Shadow", GP, "SBExcludeSearchShadow",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Remove search field shadow.")),
    _t(TweakID.DisableOuterRefraction, Section.LIQUID_GLASS, "Disable Outer Refraction", GP, "SolariumDisableOuterRefraction",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disable liquid bending at glass edges.")),
    _t(TweakID.DisableSolariumHDR, Section.LIQUID_GLASS, "Disable Solarium HDR", GP, "SolariumAllowHDR", value=False,
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disable HDR tone-mapping. Value=False.")),
    _t(TweakID.DisableSpecularMotion, Section.LIQUID_GLASS, "Disable Specular Motion", GP, "SBDisableSpecularEverywhereUsingLSSAssertion",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disable motion-based specular.")),
    _t(TweakID.DisableSpecularEverywhere, Section.LIQUID_GLASS, "Disable Specular Everywhere", GP, "SBDisableSpecularEverywhere",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Remove specular from all CC tiles.")),
    _t(TweakID.SuppressDICompletely, Section.SPRINGBOARD, "Suppress Dynamic Island", FileLocation.springboard, "SBSuppressDynamicIslandCompletely",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Hide Dynamic Island completely. Tool-proven.")),
    _t(TweakID.DisableGlassEverywhere, Section.LIQUID_GLASS, "Disable Glass Everywhere (Predicted)", GP, "SBDisableGlassEverywhere",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Predicted key — pattern hypothesis.")),
    _t(TweakID.DisallowGlassEverywhere, Section.LIQUID_GLASS, "Disallow Glass Everywhere (Predicted)", GP, "SBDisallowGlassEverywhere",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Predicted key — pattern hypothesis.")),
    # === Non-glass candidates (audited) ===
    _t(TweakID.CustomLockDate, Section.SPRINGBOARD, "Custom Lock Screen Date", FileLocation.globalPreferencesHomeDomain, "AppleICUDateTimeSymbols",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Custom Lock Screen date format. Device-proven (iOS 26.0-26.7).")),
    _t(TweakID.NotifDisplayStyle, Section.SPRINGBOARD, "Notification Display Style", GP, "globalNotificationListDisplayStyleSetting",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Display As: Count/Stack/List. Apple key from iOS 26 headers.")),
    _t(TweakID.NotifPreview, Section.SPRINGBOARD, "Notification Previews", GP, "globalContentPreviewSetting",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Show Previews: Always/When Unlocked/Never.")),
    _t(TweakID.DisableParallax, Section.SPRINGBOARD, "Disable Icon Parallax", FileLocation.springboard, "SBDisableParallax",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Stop icons shifting with device tilt.")),
    _t(TweakID.HideSearchAffordance, Section.SPRINGBOARD, "Hide Search Button", FileLocation.springboard, "SBHomeScreenShowsSearchAffordance", value=False,
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Hide search button above Dock. Value=False.")),
    _t(TweakID.AnimDragCoeff, Section.SPRINGBOARD, "Animation Speed Coefficient", GP, "UIAnimationDragCoefficient", value=0.5,
       min_version="26.0", kind=Kind.NUMBER, min_value=0, max_value=5, step=0.1,
       description=QT_TRANSLATE_NOOP("Nugget", "Animation speed: <1 faster, >1 slower, 0 disables.")),
    # === Remaining audited candidates ===
    _t(TweakID.DisableLockScreenSpecular, Section.LIQUID_GLASS, "Disable LS Specular (Predicted)", GP, "SBDisableLockScreenSpecular",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Remove specular from Lock Screen. Predicted.")),
    _t(TweakID.DisableClockSpecular, Section.LIQUID_GLASS, "Disable Clock Specular (Predicted)", GP, "SBDisableClockSpecular",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Remove specular from LS clock. Predicted.")),
    _t(TweakID.DisableGlassLockScreen, Section.LIQUID_GLASS, "Disable Glass on LS (Predicted)", GP, "SBDisableGlassLockScreen",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disable glass on Lock Screen. Predicted.")),
    _t(TweakID.DisableCompactChrome, Section.LIQUID_GLASS, "Disable Compact Chrome", GP, "DisableSolariumCompactChrome",
       min_version="27.0", description=QT_TRANSLATE_NOOP("Nugget", "Disable Solarium compact chrome. Gate 27.0.")),
    _t(TweakID.DisableGlassDI, Section.LIQUID_GLASS, "Disable Glass on DI (Predicted)", GP, "SBDisableGlassDynamicIsland",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disable glass on Dynamic Island. Predicted.")),
    _t(TweakID.DisallowGlassDI, Section.LIQUID_GLASS, "Disallow Glass on DI (Predicted)", GP, "SBDisallowGlassDynamicIsland",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disallow glass on DI. Predicted.")),
    _t(TweakID.DisableIslandSpecular, Section.LIQUID_GLASS, "Disable Island Specular (Predicted)", GP, "SBDisableIslandSpecular",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Remove DI specular. Predicted.")),
    _t(TweakID.ExcludeAllGlassShadows, Section.LIQUID_GLASS, "Exclude All Glass Shadows (Predicted)", GP, "SBExcludeAllGlassShadows",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Remove all glass shadows. Predicted.")),
    _t(TweakID.FlatDockEverywhere, Section.LIQUID_GLASS, "Flat Dock Everywhere (Predicted)", GP, "SBUseFlatDockEverywhere",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Flat dock everywhere. Predicted.")),
    _t(TweakID.DisableGlassBlur, Section.LIQUID_GLASS, "Disable Glass Blur (Predicted)", GP, "SBDisableGlassBlur",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disable glass blur. Predicted.")),
    _t(TweakID.DisallowGlassKeyboard, Section.LIQUID_GLASS, "Disallow Glass Keyboard (Predicted)", GP, "SBDisallowGlassKeyboard",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disallow keyboard glass. Predicted.")),
    _t(TweakID.DisableRefractionEverywhere, Section.LIQUID_GLASS, "Disable Refraction Everywhere (Predicted)", GP, "SBDisableRefractionEverywhere",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disable refraction everywhere. Predicted.")),
    # === Remaining: status bar, notifications, keyboard, siri ===
    _t(TweakID.StatusBarOverrides, Section.SPRINGBOARD, "Status Bar Overrides (Developer)", FileLocation.globalPreferencesHomeDomain, "StatusBarOverrides",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "DEVELOPER ONLY: Binary status bar overrides. Requires manual file creation.")),
    _t(TweakID.ShowSystemServices, Section.SPRINGBOARD, "Show System Services Icons", GP, "ShowSystemServices",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Show/hide VPN/Location/Alarm icons.")),
    _t(TweakID.NotifDisplayStyle, Section.SPRINGBOARD, "Notification Display Style", GP, "globalNotificationListDisplayStyleSetting",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Already added above — duplicate guard.")),
    _t(TweakID.KbAutocorrect, Section.INTERNAL, "Keyboard Autocorrect", GP, "KeyboardAutocorrection",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Toggle autocorrect. Device-proven channel.")),
    _t(TweakID.KbPrediction, Section.INTERNAL, "Keyboard Prediction", GP, "KeyboardPrediction",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Toggle predictive text.")),
    _t(TweakID.SiriEnabled, Section.INTERNAL, "Siri Master Switch", GP, "Assistant Enabled",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Master on/off for Siri.")),
    # === WorkSlop own system — remaining audited candidates (not GoldenNugget copy) ===
    _t(TweakID.GranularSpringBoard, Section.LIQUID_GLASS, "Granular SpringBoard Glass", GP, "SBGranularGlass",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Granular glass control per SpringBoard surface.")),
    _t(TweakID.LGLPMGestalt, Section.LIQUID_GLASS, "LG Low Power Mode Signal", GP, "SAGvsp6O6kAQ4fEfDJpC4Q",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "LGLPM signal. Unverified on 26.6.1.")),
    _t(TweakID.ShowSystemServices, Section.SPRINGBOARD, "System Services Icons", GP, "ShowSystemServices",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Toggle VPN/Location/Alarm status bar icons.")),
    _t(TweakID.ShowBatteryPercentage, Section.SPRINGBOARD, "Battery Percentage", FileLocation.springboard, "SBShowBatteryPercentage",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Show battery percentage.")),
    _t(TweakID.NotifScheduled, Section.SPRINGBOARD, "Scheduled Delivery", GP, "globalScheduledDeliverySetting",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Scheduled notification delivery.")),
    _t(TweakID.NotifSummarize, Section.SPRINGBOARD, "Notification Summarization", GP, "globalSummarizationSetting",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "AI notification summarization.")),
    _t(TweakID.NotifAnnounce, Section.SPRINGBOARD, "Announce Notifications", GP, "globalAnnounceSetting",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Spoken notification announcements.")),
    _t(TweakID.NotifHighlights, Section.SPRINGBOARD, "Notification Highlights", GP, "globalHighlightsSetting",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Highlight important notifications.")),
    _t(TweakID.NotifAlertType, Section.SPRINGBOARD, "Banner Style", GP, "alertType",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Banner style per-app: Temporary/Persistent.")),
    _t(TweakID.NotifGrouping, Section.SPRINGBOARD, "Notification Grouping", GP, "bulletinGroupingSetting",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Grouping: Automatic/By App/Off.")),
    _t(TweakID.NotifVisibility, Section.SPRINGBOARD, "Notification Visibility", GP, "lockScreenSetting",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Per-app visibility control.")),
    _t(TweakID.NotifPriority, Section.SPRINGBOARD, "Prioritize Notifications", GP, "prioritizationSetting",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "AI-powered prioritization.")),
    _t(TweakID.IconVisibility, Section.SPRINGBOARD, "Reveal Hidden Icons", GP, "SBIconVisibility",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Reveal hidden/disabled Home Screen icons.")),
    _t(TweakID.DisableClockSeconds, Section.SPRINGBOARD, "Disable Clock Seconds Hand", GP, "SBDisableClockIconSecondsHand",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Stop animated second hand on Clock icon.")),
    _t(TweakID.KbGestureIntro, Section.INTERNAL, "Keyboard Gesture Intro", GP, "DidShowGestureKeyboardIntroduction",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Re-show gesture keyboard introduction.")),
    _t(TweakID.KbAutoLists, Section.INTERNAL, "Keyboard Autocorrect Lists", GP, "KeyboardAutocorrectionLists",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Android-style autocorrect bar.")),
    _t(TweakID.KbPredBar, Section.INTERNAL, "Prediction Bar Toggle", GP, "KeyboardShowPredictionBar",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Show/hide prediction bar.")),
    _t(TweakID.SiriDataSharing, Section.INTERNAL, "Siri Data Sharing Opt-Out", GP, "Siri Data Sharing Opt-In Status", value=2,
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Opt-out of Siri telemetry. Value=2.")),
    _t(TweakID.SiriAutoPunct, Section.INTERNAL, "Dictation Auto Punctuation", GP, "Dictation Auto Punctuation Enabled",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Auto punctuation during dictation.")),
    _t(TweakID.SiriVoiceTrigger, Section.INTERNAL, "Hey Siri Toggle", GP, "VoiceTrigger Enabled",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Toggle Hey Siri voice trigger.")),
    _t(TweakID.SiriTriggerPhrase, Section.INTERNAL, "Trigger Phrase Type", GP, "UserPreferredVoiceTriggerPhraseType",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Choose trigger phrase: Hey Siri vs Siri.")),
    _t(TweakID.SiriSpeakerTTS, Section.INTERNAL, "Speaker for TTS", GP, "Use device speaker for TTS",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Route Siri voice through device speaker.")),
    _t(TweakID.SiriDeclined, Section.INTERNAL, "Siri Declined Flag", GP, "UserHasDeclinedEnable",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Flag for declined Siri setup.")),
    _t(TweakID.SiriVocab, Section.INTERNAL, "Custom Vocabulary", GP, "CustomVocabulary",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Custom vocabulary for Siri.")),
) + _FF_SPECS

SPECS_BY_SECTION = {section: [s for s in SPECS if s.section == section and not s.disabled] for section in Section}
SPECS_BY_ID = {spec.id: spec for spec in SPECS if not spec.disabled}