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
    requires_gestalt: bool = False  # True = MobileGestalt capability decision is mandatory
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


# Wave 10 Package 1: the five registry Feature Flags specs (ClockAnim,
# Lockscreen, PhotoUI, AI, KioskMode) are removed from the active product
# registry. Their delivery channel is dead for iOS 26.6.1 and the audit
# kill list names them explicitly. The TweakID members remain only as
# tombstones in src/tweaks/capabilities.py::REMOVED_TWEAK_IDS; old presets
# naming them resolve to removed/skipped, never to a FeatureFlags payload.
_FF_SPECS: tuple[TweakSpec, ...] = ()

SPECS: tuple[TweakSpec, ...] = (
    # --- Liquid Glass ---
    # Wave 10 audit containment: apart from the user-ordered Hide Search
    # presentation row, the active rows here are the three research-only
    # forensic/binary-gated specs and the one user-retained icon exception
    # below. They are not a full-disable claim and are not presented as
    # supported on iOS 26.6.1; the central audit gate in
    # src/tweaks/capabilities.py blocks research-only delivery on 23G83.

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
    # Wave 10 Home/Hide Search package: the canonical Hide Search Button is
    # presented in the Liquid Glass menu by explicit user order. This is a
    # presentation move only — the single writer keeps the managed
    # SpringBoard location, key SBHomeScreenShowsSearchAffordance, and
    # value=False. The retired HideSearchAffordance name aliases here.
    _t(TweakID.SBHideSearchAffordance, Section.LIQUID_GLASS, "Hide Search Button on Home Screen",
       FileLocation.springboard, "SBHomeScreenShowsSearchAffordance", value=False,
       description=QT_TRANSLATE_NOOP("Nugget", "Removes the search button below the icons on the Home Screen (the faint search bar/icon above the Dock). Enabled when the switch is ON.")),
    _t(TweakID.SolariumForceFallback, Section.LIQUID_GLASS, "Force Solarium Fallback", GP, "SolariumForceFallback",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Force iOS to use Liquid Glass fallback mode. Unverified — needs device test.")),
    # REMOVED (Wave 10, user order 2026-10-02): GlassLegibility2 (K1),
    # DisableSolariumSwiftUI (dead reader on iOS 26.6.1), and
    # SolariumFeatureFlags (placeholder with no real flag set) are deleted
    # from the v10 product registry. Their TweakID members remain only as
    # tombstones in src/tweaks/capabilities.py::REMOVED_TWEAK_IDS; old
    # presets naming them resolve to removed/skipped, never applied.
    _t(TweakID.DisallowGlassTime, Section.LIQUID_GLASS, "Disallow Glass on LS Clock", GP, "SBDisallowGlassTime",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disallow glass effect on Lock Screen clock.")),
    _t(TweakID.DisableGlassDock, Section.LIQUID_GLASS, "Disable Glass on Dock", GP, "SBDisableGlassDock",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Disable Liquid Glass on Dock — solid style.")),
    _t(TweakID.FlatIconsEverywhere, Section.LIQUID_GLASS, "Flat Icons Everywhere", GP, "SBUseFlatIconsEverywhere",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "User-retained Wave 10 exception: force all icons flat, no 3D/glass effect. Pattern-grade; iOS 26.6.1 reader unproven.")),
    # REMOVED (Wave 10, user order 2026-10-02): DisableGlassEverywhere and
    # DisallowGlassEverywhere were predicted pattern-hypothesis keys
    # presented as normal product toggles. Deleted from the v10 product
    # registry; TweakID tombstones remain in REMOVED_TWEAK_IDS only.
    # === Non-glass candidates (audited) ===
    _t(TweakID.CustomLockDate, Section.SPRINGBOARD, "Custom Lock Screen Date", FileLocation.globalPreferencesHomeDomain, "AppleICUDateTimeSymbols",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Custom Lock Screen date format. Device-proven (iOS 26.0-26.7).")),
    _t(TweakID.AnimDragCoeff, Section.SPRINGBOARD, "Animation Speed Coefficient", GP, "UIAnimationDragCoefficient", value=0.5,
       min_version="26.0", kind=Kind.NUMBER, min_value=0, max_value=5, step=0.1,
       description=QT_TRANSLATE_NOOP("Nugget", "Animation speed: <1 faster, >1 slower, 0 disables.")),
    # === Remaining audited candidates ===
    # REMOVED (Wave 10, user order 2026-10-02): the predicted Liquid Glass
    # entries that used to sit around DisableCompactChrome —
    # DisableLockScreenSpecular, DisableClockSpecular,
    # DisableGlassLockScreen, DisableGlassDI, DisallowGlassDI,
    # DisableIslandSpecular, ExcludeAllGlassShadows, FlatDockEverywhere,
    # DisableGlassBlur, DisallowGlassKeyboard, and
    # DisableRefractionEverywhere — are deleted from the v10 product
    # registry. TweakID tombstones remain in REMOVED_TWEAK_IDS only.
    # === Remaining: status bar, notifications, keyboard, siri ===
    # REMOVED: StatusBarOverrides was incorrectly registered as a plist key.
    # The actual statusBarOverrides is a BINARY STRUCT file at
    # /var/mobile/Library/SpringBoard/statusBarOverrides (iOS 26), not a plist.
    # It requires manual binary file creation, not BasicPlistTweak.
    # See ~/workspace/riset/ for the visual signal research.
    _t(TweakID.ShowSystemServices, Section.SPRINGBOARD, "Show System Services Icons", GP, "ShowSystemServices",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Show/hide VPN/Location/Alarm icons.")),
    # === WorkSlop own system — remaining audited candidates (not GoldenNugget copy) ===
    # REMOVED: GranularSpringBoard used invented key SBGranularGlass (not a real
    # Apple key). The granular controls are N1-N7 (SBUseFlatIconsEverywhere, etc.)
    # which are implemented as separate entries below.
    # REMOVED (Wave 10): LGLPMGestalt was registered here as a BasicPlistTweak
    # writing the MobileGestalt key SAGvsp6O6kAQ4fEfDJpC4Q as a top-level key
    # into FileLocation.mga. That delivery model is wrong — MobileGestalt
    # tweaks patch CacheExtra in the device's own plist. The registry model
    # is deleted; old presets naming LGLPMGestalt resolve to removed/skipped
    # via src/tweaks/capabilities.py::REMOVED_TWEAK_IDS, never applied. No
    # registry spec may target FileLocation.mga without a MobileGestalt
    # factory.
    # REMOVED (Wave 10 Package 1, audit kill list): the Settings-duplicate
    # SpringBoard/Keyboard/Siri rows, the ten wrong-domain Notification
    # rows, the wrong value/type rows (DisableSearchingWebsites,
    # SiriTriggerPhrase, SiriVocab), the dead-reader Liquid Glass
    # specular/shadow/refraction/HDR rows plus DisableCompactChrome, and
    # the five redundant duplicate rows (SuppressDICompletely,
    # DisableParallax, HideSearchAffordance, IconVisibility,
    # DisableClockSeconds) are deleted from the active v10 registry.
    # Non-duplicate kills stay tombstoned in REMOVED_TWEAK_IDS; the five
    # duplicate names alias to their canonical IDs there.
    _t(TweakID.KbGestureIntro, Section.INTERNAL, "Keyboard Gesture Intro", GP, "DidShowGestureKeyboardIntroduction",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Re-show gesture keyboard introduction.")),
    _t(TweakID.KbAutoLists, Section.INTERNAL, "Keyboard Autocorrect Lists", GP, "KeyboardAutocorrectionLists",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Android-style autocorrect bar.")),
    _t(TweakID.SiriSpeakerTTS, Section.INTERNAL, "Speaker for TTS", GP, "Use device speaker for TTS",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Route Siri voice through device speaker.")),
    _t(TweakID.SiriDeclined, Section.INTERNAL, "Siri Declined Flag", GP, "UserHasDeclinedEnable",
       min_version="26.0", description=QT_TRANSLATE_NOOP("Nugget", "Flag for declined Siri setup.")),
) + _FF_SPECS

SPECS_BY_SECTION = {section: [s for s in SPECS if s.section == section and not s.disabled] for section in Section}
SPECS_BY_ID = {spec.id: spec for spec in SPECS if not spec.disabled}


def home_tweak_catalogue(specs_by_section=None) -> tuple:
    """Registry-derived Home catalogue entries for every active spec.

    Home consumes this instead of a hand-maintained tweak list, so adding
    one registry spec surfaces it on Home automatically. ``specs_by_section``
    is injectable for tests; by default the live ``SPECS_BY_SECTION``
    mapping is read at call time so a registry rebuild is reflected without
    editing Home. Removed tombstones and retired duplicate aliases are not
    specs and therefore never appear as separate Home entries.
    """
    source = SPECS_BY_SECTION if specs_by_section is None else specs_by_section
    entries = []
    for section in Section:
        feature = SECTION_FEATURES.get(section, section.value)
        for spec in source.get(section, []):
            if getattr(spec, "disabled", False):
                continue
            entries.append({
                "id": spec.id,
                "id_name": spec.id.name,
                "title": spec.title,
                "section": section,
                "section_name": section.value,
                "feature": feature,
                "location": spec.location,
                "location_path": spec.location.value,
                "key": spec.key,
            })
    return tuple(entries)