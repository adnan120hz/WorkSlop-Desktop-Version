"""Shared tweak capability classification and deliverability checks.

This module is the non-GUI home for the question "may this tweak be enabled
or delivered on the current device?" The GUI compatibility helper and the
backend apply pass both use it, so a tweak cannot look supported in the UI
while the backend treats it differently (or vice versa).

MobileGestalt is the first capability modelled here. The decision itself
lives in :mod:`src.devicemanagement.constants` (``mobilegestalt_decision``);
this module classifies which tweaks require that decision and combines it
with the registry's per-spec version/device-class constraints.

Wave 10 Package 1 adds the audit evidence gate from
``AUDIT-FINAL-WAVE10.md`` here as well: removed IDs are tombstones, the five
redundant duplicate IDs alias to their canonical writer, and research-only
IDs cannot be delivered as ship features on the audited iOS 26.6.1 target
(build 23G83). The one user-retained exception is
``FlatIconsEverywhere``; it stays active by explicit user order and is not
evidence of support.
"""

from packaging.version import Version

from src.devicemanagement.constants import (
    MobileGestaltDecision, mobilegestalt_decision,
)
from src.tweaks.registry import SPECS_BY_ID
from src.tweaks.tweak_names import TweakID


# Every TweakID whose apply path patches the device's MobileGestalt cache
# (CacheExtra / CacheData) through one of the MobileGestalt tweak classes.
# This is the non-registry half of the classification; registry specs carry
# ``TweakSpec.requires_gestalt`` instead. Keep this list in step with
# ``tweak_loader.get_mobilegestalt_tweaks()`` and the Eligibility spoofing
# tweaks in ``tweak_loader.load_eligibility()``.
MOBILEGESTALT_TWEAK_IDS = frozenset({
    # MobileGestalt page family (tweak_loader.get_mobilegestalt_tweaks)
    TweakID.DynamicIsland, TweakID.SupportsDynamicIsland, TweakID.ModelName,
    TweakID.BootChime, TweakID.EnableLGLPM, TweakID.DisableLGLPM,
    TweakID.ChargeLimit, TweakID.CollisionSOS, TweakID.TapToWake,
    TweakID.CameraButton, TweakID.Parallax, TweakID.StageManager,
    TweakID.iPadOS, TweakID.iPadOSCacheData, TweakID.iPadApps,
    TweakID.Shutter, TweakID.Pencil, TweakID.ActionButton,
    TweakID.InternalStorage, TweakID.InternalInstall, TweakID.SRD,
    TweakID.AOD, TweakID.AODVibrancy,
    # Eligibility-page MobileGestalt tweaks
    TweakID.AIGestalt, TweakID.SpoofModel, TweakID.SpoofHardware,
    TweakID.SpoofCPU,
})

# RdarFix is presented from the MobileGestalt page flow even though its
# payload is the managed IOMobileGraphicsFamily resolution plist, not a
# MobileGestalt cache patch. It is therefore gated by the same shared
# MobileGestalt decision: on a locked/unknown target it must be cleared,
# skipped by presets/summaries, and never delivered just because its plist
# route happens to be technically writable.
MOBILEGESTALT_FLOW_TWEAK_IDS = frozenset({
    TweakID.RdarFix,
})

# Registry IDs removed from the WorkSlop v10 product registry by explicit
# user order (2026-10-02): K1, placeholder/dead-reader entries, predicted
# pattern-hypothesis Liquid Glass entries presented as normal toggles, and
# the wrong BasicPlist/MobileGestalt-cache model. The TweakID enum members
# stay as tombstones so old presets can be parsed, but a tombstoned ID must
# always resolve to removed/skipped — never to an applied tweak.
REMOVED_TWEAK_IDS = frozenset({
    TweakID.GlassLegibility2,          # K1: UIViewGlassLegibilitySetting = 2
    TweakID.SolariumFeatureFlags,      # placeholder: no real flag set defined
    TweakID.DisableSolariumSwiftUI,    # dead reader on iOS 26.6.1
    TweakID.DisableGlassEverywhere,    # predicted / pattern hypothesis
    TweakID.DisallowGlassEverywhere,   # predicted / pattern hypothesis
    TweakID.DisableLockScreenSpecular, # predicted
    TweakID.DisableClockSpecular,      # predicted
    TweakID.DisableGlassLockScreen,    # predicted
    TweakID.DisableGlassDI,            # predicted
    TweakID.DisallowGlassDI,           # predicted
    TweakID.DisableIslandSpecular,     # predicted
    TweakID.ExcludeAllGlassShadows,    # predicted
    TweakID.FlatDockEverywhere,        # predicted
    TweakID.DisableGlassBlur,          # predicted
    TweakID.DisallowGlassKeyboard,     # predicted
    TweakID.DisableRefractionEverywhere,  # predicted
    TweakID.LGLPMGestalt,              # wrong BasicPlist/FileLocation.mga model
    TweakID.AIFeatureFlags,            # uncapped dead FeatureFlags channel (>26.1)
    TweakID.AIFeatureFlagsUI,          # uncapped dead FeatureFlags channel (>26.1)
    # Wave 10 Package 1 audit kills (AUDIT-FINAL-WAVE10 §4). The enum
    # members remain parseable for old presets, but these IDs never resolve
    # to an active spec or payload again.
    TweakID.SBMinimumLockscreenIdleTime,  # Settings-duplicate (Auto-Lock)
    TweakID.ShowBatteryPercentage,        # Settings-duplicate
    TweakID.KbAutocorrect,                # Settings-duplicate
    TweakID.KbPrediction,                 # Settings-duplicate
    TweakID.KbPredBar,                    # Settings-duplicate
    TweakID.SiriEnabled,                  # Settings-duplicate
    TweakID.SiriAutoPunct,                # Settings-duplicate
    TweakID.SiriVoiceTrigger,             # Settings-duplicate
    TweakID.SiriDataSharing,              # Settings-duplicate
    TweakID.NotifDisplayStyle,            # wrong domain/storage model
    TweakID.NotifPreview,                 # wrong domain/storage model
    TweakID.NotifScheduled,               # wrong domain/storage model
    TweakID.NotifSummarize,               # wrong domain/storage model
    TweakID.NotifAnnounce,                # wrong domain/storage model
    TweakID.NotifHighlights,              # wrong domain/storage model
    TweakID.NotifAlertType,               # wrong domain/storage model
    TweakID.NotifGrouping,                # wrong domain/storage model
    TweakID.NotifVisibility,              # wrong domain/storage model
    TweakID.NotifPriority,                # wrong domain/storage model
    TweakID.DisableSearchingWebsites,     # wrong value/type
    TweakID.SiriTriggerPhrase,            # wrong value/type
    TweakID.SiriVocab,                    # wrong value/type
    TweakID.DisableWidgetSpecular,        # dead-reader/pass-stripping LG row
    TweakID.DisableDockSpecular,          # dead-reader/pass-stripping LG row
    TweakID.DisableFolderSpecular,        # dead-reader/pass-stripping LG row
    TweakID.ExcludeClearGlassShadows,     # dead-reader/pass-stripping LG row
    TweakID.ExcludeDockShadow,            # dead-reader/pass-stripping LG row
    TweakID.ExcludeSearchShadow,          # dead-reader/pass-stripping LG row
    TweakID.DisableOuterRefraction,       # dead-reader/pass-stripping LG row
    TweakID.DisableSolariumHDR,           # dead-reader/pass-stripping LG row
    TweakID.DisableSpecularMotion,        # dead-reader/pass-stripping LG row
    TweakID.DisableSpecularEverywhere,    # dead-reader/pass-stripping LG row
    TweakID.DisableCompactChrome,         # target-ineligible (iOS 27 gate)
    TweakID.ClockAnim,                    # dead FeatureFlags channel on target
    TweakID.Lockscreen,                   # dead FeatureFlags channel on target
    TweakID.PhotoUI,                      # dead FeatureFlags channel on target
    TweakID.AI,                           # dead FeatureFlags channel on target
    TweakID.KioskMode,                    # dead FeatureFlags channel on target
})

# Backwards-compatible aliases for the five redundant duplicate rows in
# AUDIT-FINAL-WAVE10 §4.5. These names are *not* removed tombstones: an old
# preset naming one resolves to the single canonical writer below, so it
# can never create a second enabled writer for the same (location, key).
DEPRECATED_TWEAK_ALIASES = {
    TweakID.SuppressDICompletely: TweakID.HideDICompletely,
    TweakID.DisableParallax: TweakID.SBDisableIconParallax,
    TweakID.HideSearchAffordance: TweakID.SBHideSearchAffordance,
    TweakID.IconVisibility: TweakID.SBIconVisibility,
    TweakID.DisableClockSeconds: TweakID.DisableSecondsHand,
}

# Wave 10 audit target. Research-only containment is deliberately scoped
# to this audited target instead of silently rewriting the historical
# meaning of every older iOS version: on iOS 26.6.1 / build 23G83 these
# IDs may not be presented or delivered as supported ship features.
AUDIT_TARGET_VERSION = "26.6.1"
AUDIT_TARGET_BUILD = "23G83"

# Audit research-only IDs (AUDIT-FINAL-WAVE10 §5). Registry rows remain in
# the registry so the UI can show them locked with the audit reason on the
# target; non-registry families are classified here so presets, summaries,
# and the backend share the same containment decision. MobileGestalt IDs
# are already fail-closed by their own decision and are included so the
# research-only classification is complete in one place.
AUDIT_RESEARCH_ONLY_TWEAK_IDS = frozenset({
    # SpringBoard research registry rows
    TweakID.WatchOSCompatibility, TweakID.CustomLockDate,
    TweakID.AnimDragCoeff, TweakID.ShowSystemServices,
    # Internal research registry rows (canonical SBIconVisibility /
    # DisableSecondsHand included; their SpringBoard duplicates alias here)
    TweakID.SBBuildNumber, TweakID.RTL, TweakID.LTR, TweakID.SBIconVisibility,
    TweakID.iMessageDiagnosticsEnabled, TweakID.IDSDiagnosticsEnabled,
    TweakID.VCDiagnosticsEnabled, TweakID.AccessoryDeveloperEnabled,
    TweakID.KeyFlick, TweakID.DisableSecondsHand, TweakID.ShowButtonHints,
    TweakID.AppStoreDebug, TweakID.NotesDebugMode,
    TweakID.BKDigitizerVisualizeTouches, TweakID.BKHideAppleLogoOnLaunch,
    TweakID.EnableWakeGestureHaptic, TweakID.PlaySoundOnPaste,
    TweakID.AnnounceAllPastes, TweakID.KbGestureIntro, TweakID.KbAutoLists,
    TweakID.SiriSpeakerTTS, TweakID.SiriDeclined,
    # Eligibility research rows
    TweakID.EUEnabler, TweakID.AIEligibility, TweakID.CreateBRFolders,
    # Risky research rows
    TweakID.DisableOTAFile, TweakID.CustomResolution,
    # Status Bar / Daemons / PosterBoard / Templates control groups
    TweakID.StatusBar, TweakID.Daemons, TweakID.ClearScreenTimeAgentPlist,
    TweakID.PosterBoard, TweakID.Templates,
    # MobileGestalt-page adjacent research row (also MobileGestalt-gated)
    TweakID.RdarFix,
}) | MOBILEGESTALT_TWEAK_IDS

# DEVICE-TEST path (user doctrine, reaffirmed 2026-10-02): unproven is not
# the same as wrong. A candidate whose key/domain/value/reader-hypothesis/
# delivery structure survived the audit is *for* isolated device testing —
# locking it away makes the test the doctrine demands impossible. Only
# structurally wrong, dead-reader, wrong-delivery, settings-duplicate, or
# user-killed candidates stay hard-locked (REMOVED_TWEAK_IDS above).
#
# These three Liquid Glass rows were substantively re-verified before the
# unlock (payload trace, not UI state):
#   * SolariumForceFallback=true — spec (registry.py) writes GP =
#     FileLocation.globalPreferences
#     (src/tweaks/basic_plist_locations.py:20
#     "/var/Managed Preferences/mobile/.GlobalPreferences.plist"), exactly
#     the Hitori .batter provenance: ManagedPreferencesDomain + hidden-dot
#     .GlobalPreferences.plist (path_mapping maps "/var/Managed Preferences/"
#     to ManagedPreferencesDomain). Audit: key PARTIAL (tool lineage),
#     domain PASS, value PASS (bool true), reader UNKNOWN on 23G83.
#   * SBDisallowGlassTime=true, SBDisableGlassDock=true — same GP file,
#     bool true; audit 5-layer: exact claimed spelling (authenticity
#     unproven), GP is the claimed route, value PASS, reader UNKNOWN.
# All three ride BasicPlistTweak (value default True) into the single
# managed-GP plist staged by the apply pass (one writer per (location,key)
# is enforced by the registry audit test), and the Internal Options reset
# nulls that same GP file with a valid empty plist, so reset cleans the
# exact keys apply writes. Reader on iOS 26.6.1 is still UNPROVEN — that is
# what the device test is for; the GUI must say so on every enable.
DEVICE_TEST_TWEAK_IDS = frozenset({
    TweakID.SolariumForceFallback, TweakID.DisallowGlassTime,
    TweakID.DisableGlassDock,
})


def is_device_test_tweak(tweak_id) -> bool:
    """True for audit-verified-but-unproven candidates opened for isolated
    device testing (canonical ID wins; aliases resolve first)."""
    try:
        return canonical_tweak_id(tweak_id) in DEVICE_TEST_TWEAK_IDS
    except Exception:
        return False


# USER POLICY EXPANSION (2026-10-03): every audit research-only tweak that
# is a real registry tweak joins the device-test path — toggle enabled,
# UNPROVEN badge, one-time backup confirmation, Apply Journal entry — the
# same treatment the three Liquid Glass candidates already have. What
# stays hard-locked, with no path through here:
#   * removed/killed IDs (REMOVED_TWEAK_IDS) — wrong delivery, dead
#     readers, settings duplicates, user-killed candidates;
#   * non-registry research families (Status Bar / Daemons / PosterBoard /
#     Templates / Risky / Eligibility pages own their controls);
#   * MobileGestalt-gated tweaks on a locked/unknown build — the shared
#     MobileGestalt decision stays fail-closed and is evaluated BEFORE
#     this path in tweak_deliverability (RdarFix included).
def is_device_test_candidate(tweak_id) -> bool:
    """True when *tweak_id* may be enabled as an UNPROVEN device test.

    The original three Liquid Glass candidates always qualify. Every other
    audit research-only ID qualifies only when it is a registry tweak
    (``SPECS_BY_ID``); non-registry families and removed tombstones never
    do. Deliverability still applies every other gate (version range,
    device class, MobileGestalt) on top of this classification.
    """
    try:
        canonical = canonical_tweak_id(tweak_id)
    except Exception:
        return False
    if is_removed_tweak(canonical):
        return False
    if canonical in DEVICE_TEST_TWEAK_IDS:
        return True
    return (is_audit_research_only(canonical)
            and canonical in SPECS_BY_ID)


# Explicit user-retained exception (2026-10-02 17:21 WIB). It remains an
# active product row by user order; retention is not reader evidence and
# must never be read as proof that the archived v4 Liquid Glass set works.
AUDIT_USER_RETAINED_TWEAK_IDS = frozenset({
    TweakID.FlatIconsEverywhere,
})


def is_removed_tweak(tweak_id) -> bool:
    """True when *tweak_id* is a v10-removed tombstone (never applied)."""
    try:
        return tweak_id in REMOVED_TWEAK_IDS
    except Exception:
        return False

_MOBILEGESTALT_CLASS_NAMES = frozenset({
    "MobileGestaltTweak", "MobileGestaltPickerTweak",
    "MobileGestaltMultiTweak", "MobileGestaltCacheDataTweak",
})


def canonical_tweak_id(tweak_id):
    """Resolve a deprecated preset/UI ID to its canonical TweakID."""
    try:
        return DEPRECATED_TWEAK_ALIASES.get(tweak_id, tweak_id)
    except Exception:
        return tweak_id


def is_audit_target(device_version: str = "", device_build: str = "") -> bool:
    """True when the device evidence names the Wave 10 audited target."""
    version = str(device_version or "").strip()
    build = str(device_build or "").strip()
    return version == AUDIT_TARGET_VERSION or build == AUDIT_TARGET_BUILD


def is_audit_research_only(tweak_id) -> bool:
    """True when *tweak_id* is audit research-only (canonical ID wins)."""
    try:
        canonical = canonical_tweak_id(tweak_id)
        return (canonical in AUDIT_RESEARCH_ONLY_TWEAK_IDS
                and canonical not in AUDIT_USER_RETAINED_TWEAK_IDS)
    except Exception:
        return False


def is_audit_user_retained(tweak_id) -> bool:
    """True for the explicit user-retained Wave 10 exception."""
    try:
        return canonical_tweak_id(tweak_id) in AUDIT_USER_RETAINED_TWEAK_IDS
    except Exception:
        return False


def clear_audit_research_only_state(device_version: str = "",
                                    device_build: str = "",
                                    tweaks_dict=None) -> list:
    """Force enabled audit research-only tweaks off on the audited target.

    Used before apply/summary generation so stale ON state from a preset,
    AutoSave, or a previous device cannot be counted or delivered as a
    supported iOS 26.6.1 feature. Returns the names cleared. Non-target
    devices and the user-retained exception are untouched.

    Registry research-only tweaks are NOT cleared anymore (user policy
    2026-10-03): they are deliverable as UNPROVEN device tests, and the
    apply pass journals them as such. Only non-registry research families
    (Status Bar / Daemons / PosterBoard / Risky / Eligibility controls)
    and MobileGestalt-gated rows are still force-cleared — the latter via
    ``clear_unsupported_mobilegestalt_state`` on locked builds.
    """
    if not is_audit_target(device_version, device_build):
        return []
    if tweaks_dict is None:
        from src.tweaks.tweaks import tweaks as tweaks_dict  # late: avoids a cycle
    cleared = []
    for tweak_id, tweak in list(tweaks_dict.items()):
        if tweak is None or not getattr(tweak, "enabled", False):
            continue
        if not is_audit_research_only(tweak_id):
            continue
        if is_device_test_candidate(tweak_id):
            continue  # registry research-only: device-testable, not cleared
        try:
            tweak.set_enabled(False)
        except Exception:
            try:
                tweak.enabled = False
            except Exception:
                continue
        cleared.append(tweak_id.name if hasattr(tweak_id, "name") else str(tweak_id))
    return cleared


def requires_gestalt(tweak_id, tweak=None) -> bool:
    """True when *tweak_id* (or the live *tweak* object) is gated by the
    shared MobileGestalt decision.

    Classification is by delivery/presentation model, never by title text:
    registry spec flag, deprecated alias, central ID map, MobileGestalt tweak
    class, or the MobileGestalt-page flow set (RdarFix). RdarFix does not
    patch CacheExtra; it is included because the surface that presents it is
    the MobileGestalt flow, so a locked/unknown MobileGestalt target must not
    deliver it through the resolution-plist side door.
    """
    canonical = canonical_tweak_id(tweak_id)
    spec = SPECS_BY_ID.get(canonical)
    if spec is not None and getattr(spec, "requires_gestalt", False):
        return True
    if canonical in MOBILEGESTALT_TWEAK_IDS or canonical in MOBILEGESTALT_FLOW_TWEAK_IDS:
        return True
    if tweak_id in MOBILEGESTALT_TWEAK_IDS or tweak_id in MOBILEGESTALT_FLOW_TWEAK_IDS:
        return True
    if tweak is not None and type(tweak).__name__ in _MOBILEGESTALT_CLASS_NAMES:
        return True
    return False


def is_mobilegestalt_backed(tweak_id, tweak=None) -> bool:
    """True only for tweaks whose payload actually patches MobileGestalt.

    RdarFix is decision-gated (see ``requires_gestalt``) but is not itself a
    MobileGestalt-cache payload, so it is deliberately excluded here.
    """
    canonical = canonical_tweak_id(tweak_id)
    if canonical in MOBILEGESTALT_FLOW_TWEAK_IDS or tweak_id in MOBILEGESTALT_FLOW_TWEAK_IDS:
        return False
    spec = SPECS_BY_ID.get(canonical)
    if spec is not None and getattr(spec, "requires_gestalt", False):
        return True
    if canonical in MOBILEGESTALT_TWEAK_IDS or tweak_id in MOBILEGESTALT_TWEAK_IDS:
        return True
    return tweak is not None and type(tweak).__name__ in _MOBILEGESTALT_CLASS_NAMES


# Backend safety envelope for Risky CustomResolution. The bounds are the
# envelope of the canvas dimensions already used by RdarFixTweak's existing
# mode table (828..2868 wide, 1320..2868 high); they are a sanity gate against
# typos/absurd values, not a claim that every in-range pair works on every
# device. At least one dimension must be present (the loader's historical
# one-dimension behaviour), every present dimension must be a real int inside
# its envelope, and no unknown keys may ride the shared resolution plist.
CUSTOM_RESOLUTION_DIMENSION_RANGES = {
    "canvas_width": (828, 2868),
    "canvas_height": (1320, 2868),
}


def validate_custom_resolution(value) -> tuple:
    """Validate a CustomResolution payload for the backend apply pass.

    Returns ``(ok, reason_code, user_message)``. This is a fail-closed
    safety gate only: an in-range payload still has no device-proven effect
    claim on iOS 26.6.1.
    """
    if not isinstance(value, dict):
        return (False, "INVALID_CUSTOM_RESOLUTION",
                "Custom Resolution payload must be a dictionary of canvas dimensions.")
    unknown = sorted(set(value) - set(CUSTOM_RESOLUTION_DIMENSION_RANGES))
    if unknown:
        return (False, "INVALID_CUSTOM_RESOLUTION",
                "Custom Resolution may only set canvas_width/canvas_height; "
                f"unknown keys: {', '.join(unknown)}.")
    present = [key for key in CUSTOM_RESOLUTION_DIMENSION_RANGES if key in value]
    if not present:
        return (False, "INVALID_CUSTOM_RESOLUTION",
                "Custom Resolution needs at least one canvas dimension.")
    for key in present:
        raw = value.get(key)
        low, high = CUSTOM_RESOLUTION_DIMENSION_RANGES[key]
        if isinstance(raw, bool) or not isinstance(raw, int):
            return (False, "INVALID_CUSTOM_RESOLUTION",
                    f"Custom Resolution {key} must be an integer.")
        if raw < low or raw > high:
            return (False, "INVALID_CUSTOM_RESOLUTION",
                    f"Custom Resolution {key} must be between {low} and {high}.")
    return (True, "OK", "")


def decision_for_device(device) -> MobileGestaltDecision:
    """Shared decision for a Device-like object (or None)."""
    if device is None:
        return mobilegestalt_decision("", "")
    return mobilegestalt_decision(
        getattr(device, "build", "") or "",
        getattr(device, "version", "") or "")


def tweak_deliverability(tweak_id, device_version: str = "",
                         device_build: str = "", is_iphone: bool = True,
                         tweak=None) -> tuple:
    """Combine registry constraints + MobileGestalt capability.

    Returns ``(deliverable, reason_code, user_message)``. ``reason_code`` is
    a stable machine-readable string: a ``MobileGestaltDecision`` reason for
    capability failures, or ``VERSION_BELOW_MIN`` / ``VERSION_ABOVE_MAX`` /
    ``IPHONE_ONLY`` / ``IPAD_ONLY`` / ``OK``.

    Unknown device evidence never blocks ordinary tweaks (the registry's
    historical "no version yet" behaviour), but it always blocks
    MobileGestalt-backed tweaks: unknown is fail-closed there.
    """
    canonical = canonical_tweak_id(tweak_id)
    if is_removed_tweak(canonical) or is_removed_tweak(tweak_id):
        return (False, "REMOVED_TWEAK",
                "Removed from WorkSlop v10 by user order; it is never applied.")
    spec = SPECS_BY_ID.get(canonical)

    if spec is not None and device_version:
        try:
            if spec.min_version and Version(device_version) < Version(spec.min_version):
                return (False, "VERSION_BELOW_MIN",
                        f"Requires iOS {spec.min_version} or later.")
        except Exception:
            pass
        try:
            if spec.max_version and Version(device_version) > Version(spec.max_version):
                return (False, "VERSION_ABOVE_MAX",
                        f"Requires iOS {spec.max_version} or earlier.")
        except Exception:
            pass
    if spec is not None:
        if spec.ipad_only and is_iphone:
            return (False, "IPAD_ONLY", "This tweak is for iPad only.")
        if spec.iphone_only and not is_iphone:
            return (False, "IPHONE_ONLY", "This tweak is for iPhone only.")

    if requires_gestalt(canonical, tweak):
        # MobileGestalt stays fail-closed and is evaluated BEFORE the
        # device-test path: a research-only classification can never open
        # a MobileGestalt-gated tweak on a locked/unknown build (RdarFix
        # included, via the MobileGestalt-page flow set).
        decision = mobilegestalt_decision(device_build, device_version)
        if not decision.supported:
            return (False, decision.reason_code, decision.user_message)

    if (is_audit_research_only(canonical)
            and is_audit_target(device_version, device_build)):
        if canonical in SPECS_BY_ID:
            # Device-test path (expanded user policy 2026-10-03): every
            # research-only REGISTRY tweak may be enabled for an isolated
            # device test on the audited target — badge UNPROVEN, backup
            # confirmation, Apply Journal. Non-registry research families
            # stay locked here; their own pages own those controls.
            return (True, "DEVICE_TEST_OK",
                    "UNPROVEN — device test: classified research-only by "
                    "the Wave 10 audit; structure recorded, on-device "
                    "effect not proven. Full backup first, Low Power Mode "
                    "off, one candidate per apply, and never reset the "
                    "SpringBoard page on iOS 26.6.1.")
        return (False, "AUDIT_RESEARCH_ONLY",
                "Research-only in the Wave 10 audit; not a supported "
                "iOS 26.6.1 ship feature.")

    if is_device_test_tweak(canonical):
        # Deliverable, but honestly labelled: the structure is verified,
        # the on-device reader is not. Callers (GUI badge, journal, preset
        # summaries) surface DEVICE_TEST_OK instead of a plain OK so the
        # unproven status is never silently dropped.
        return (True, "DEVICE_TEST_OK",
                "UNPROVEN — device test: structure verified by audit, "
                "on-device effect not proven. Full backup first, Low Power "
                "Mode off, one candidate per apply, and never reset the "
                "SpringBoard page on iOS 26.6.1.")

    return (True, "OK", "")


def clear_unsupported_mobilegestalt_state(decision: MobileGestaltDecision = None,
                                          build: str = "", version: str = "",
                                          tweaks_dict=None) -> list:
    """Force every enabled MobileGestalt-gated tweak off.

    Used on device switches and before rendering/applying whenever the
    shared decision is locked or unknown, so a stale ON state can never
    survive into the model, a summary, AutoSave, or an apply. Returns the
    names of the tweaks that were cleared. A supported decision clears
    nothing. RdarFix is included via the MobileGestalt-page flow set.
    """
    if decision is None:
        decision = mobilegestalt_decision(build, version)
    if decision.supported:
        return []
    if tweaks_dict is None:
        from src.tweaks.tweaks import tweaks as tweaks_dict  # late: avoids a cycle
    cleared = []
    for tweak_id, tweak in list(tweaks_dict.items()):
        if tweak is None or not getattr(tweak, "enabled", False):
            continue
        if not requires_gestalt(tweak_id, tweak):
            continue
        try:
            tweak.set_enabled(False)
        except Exception:
            try:
                tweak.enabled = False
            except Exception:
                continue
        cleared.append(tweak_id.name if hasattr(tweak_id, "name") else str(tweak_id))
    return cleared
