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
``AUDIT-FINAL-WAVE10.md`` here as well: removed IDs are tombstones and the
five redundant duplicate IDs alias to their canonical writer.

Wave 11 policy (user order 2026-10-03): the audit classification is kept as
a record, but "research-only / not yet verified on-device" is no longer a
delivery lock. Every tweak whose key/domain/value/delivery structure
survived the audit is a normal, user-activatable tweak — an unverified
tweak that cannot be switched on can never be device-tested at all. Only
structurally dead entries stay hard-locked: the ``REMOVED_TWEAK_IDS``
tombstones (wrong domain/storage model, dead FeatureFlags channel,
wrong value/type, Settings duplicates) and MobileGestalt-backed tweaks on
a locked/unknown build (``mobilegestalt_decision`` stays fail-closed and
is always evaluated before anything else here).
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

# The eligibility files-based family (EUEnabler / AIEligibility /
# CreateBRFolders) writes eligibility.plist and the os_eligibility folders,
# not the MobileGestalt cache — but by user order (2026-10-03) Eligibility
# is blocked from iOS 26.2 beta 2 upward, exactly the MobileGestalt build
# boundary: open through iOS 26.2 beta 1 (build 23C5027f), locked from
# build 23C5035e (and every later build, 23G82/23G83 included). These IDs
# are therefore gated by the SAME shared ``mobilegestalt_decision`` — one
# source of truth for the boundary, no second version check anywhere.
# The spoofing members of the Eligibility page (AIGestalt / SpoofModel /
# SpoofHardware / SpoofCPU) are MobileGestalt tweaks and already live in
# MOBILEGESTALT_TWEAK_IDS above.
ELIGIBILITY_BOUNDARY_TWEAK_IDS = frozenset({
    TweakID.EUEnabler, TweakID.AIEligibility, TweakID.CreateBRFolders,
})

# User-facing explanation shown wherever an Eligibility control is locked
# by the shared build boundary (UI tooltip + backend skip reason).
ELIGIBILITY_LOCKED_MESSAGE = (
    "Eligibility is blocked on iOS 26.2 beta 2 and later "
    "(build 23C5035e and newer); it is only available through "
    "iOS 26.2 beta 1 (build 23C5027f)."
)


def requires_eligibility_boundary(tweak_id) -> bool:
    """True when *tweak_id* belongs to the Eligibility files-based family
    that shares the MobileGestalt build boundary (see
    ``ELIGIBILITY_BOUNDARY_TWEAK_IDS``). Classification is by tweak ID,
    never by title text."""
    try:
        return canonical_tweak_id(tweak_id) in ELIGIBILITY_BOUNDARY_TWEAK_IDS
    except Exception:
        return False


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
    # The v4 Liquid Glass IDs (GlassLegibility2, SolariumFeatureFlags,
    # DisableSolariumSwiftUI, the predicted/specular/shadow rows,
    # LGLPMGestalt) are NOT here any more: the user ordered the v4 Liquid
    # Glass set restored verbatim on 2026-10-03, so those IDs resolve to
    # their v4 specs again. The Wave 10 audit reasoning is preserved in
    # AUDIT-FINAL-WAVE10; the restoration is a user product decision, not
    # an audit upgrade.
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
    # The specular/shadow/refraction v4 Liquid Glass rows and
    # DisableCompactChrome also left this set with the 2026-10-03 verbatim
    # v4 restoration (see the note at the top of this set).
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

# Audit research-only IDs (AUDIT-FINAL-WAVE10 §5), kept as the audit
# record. Wave 11 (user order 2026-10-03): membership in this set is
# classification only — it no longer locks, clears, badges, or skips
# anything by itself. Every entry whose structure passed the audit is a
# normal activatable tweak; the structurally dead ones live in
# REMOVED_TWEAK_IDS instead. MobileGestalt IDs are included so the
# classification is complete in one place; they stay fail-closed through
# the MobileGestalt decision, not through this set.
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

# DEVICE-TEST classification (retired as a gate, Wave 11, user order
# 2026-10-03): unproven is not the same as wrong, and a candidate that
# cannot be switched on can never be device-tested. The three Liquid Glass
# rows that opened this path in Wave 10 (SolariumForceFallback,
# SBDisallowGlassTime, SBDisableGlassDock) became plain v4 specs with the
# 2026-10-03 verbatim v4 restoration, and the same "audit passed -> normal
# active tweak" rule now covers every research-only entry (see
# is_device_test_candidate). This explicit set stays empty: nothing is
# labelled or gated as a device test any more. Only structurally wrong,
# dead-reader, wrong-delivery, settings-duplicate, or user-killed
# candidates stay hard-locked (REMOVED_TWEAK_IDS above).
DEVICE_TEST_TWEAK_IDS = frozenset()


def is_device_test_tweak(tweak_id) -> bool:
    """True for audit-verified-but-unproven candidates opened for isolated
    device testing (canonical ID wins; aliases resolve first)."""
    try:
        return canonical_tweak_id(tweak_id) in DEVICE_TEST_TWEAK_IDS
    except Exception:
        return False


def is_device_test_candidate(tweak_id) -> bool:
    """True when *tweak_id* is an explicit device-test-only candidate.

    Wave 11 (user order 2026-10-03): nothing is a device-test-only
    candidate any more. Every audit research-only ID whose structure
    survived became a normal activatable tweak, so this classification is
    exactly ``DEVICE_TEST_TWEAK_IDS`` (empty). It is kept as a function
    because the GUI badge/confirmation plumbing imports it; it must never
    light up again unless a future user order repopulates the set.
    Removed tombstones never qualify.
    """
    try:
        canonical = canonical_tweak_id(tweak_id)
    except Exception:
        return False
    if is_removed_tweak(canonical):
        return False
    return canonical in DEVICE_TEST_TWEAK_IDS


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
    """Force enabled audit research-only tweaks off — RETIRED (Wave 11).

    User order 2026-10-03: a tweak that passed the structure audit is a
    normal activatable tweak; "not yet verified on-device" is no longer a
    reason to clear, lock, or skip it (an unverified tweak that cannot be
    switched on can never be device-tested at all). This function
    therefore clears nothing and always returns []. It remains importable
    because the GUI rebuild path and the backend apply pass call it;
    MobileGestalt-gated state is still force-cleared on locked builds by
    ``clear_unsupported_mobilegestalt_state``, which is unchanged.
    """
    return []


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

    if requires_eligibility_boundary(canonical):
        # Eligibility (EUEnabler / AIEligibility / CreateBRFolders) is
        # blocked from iOS 26.2 beta 2 upward by user order (2026-10-03).
        # The boundary is the SAME shared mobilegestalt_decision used
        # above — exact build authoritative, version fallback, unknown
        # fail-closed. No second version comparison lives here; the
        # locked reason_code is the decision's own, only the explanation
        # names Eligibility.
        decision = mobilegestalt_decision(device_build, device_version)
        if not decision.supported:
            return (False, decision.reason_code, ELIGIBILITY_LOCKED_MESSAGE)

    # Wave 11 (user order 2026-10-03): the audit research-only
    # classification no longer gates delivery. Registry rows and
    # non-registry families alike (Internal, SpringBoard, Status Bar,
    # Daemons, PosterBoard, Templates, Risky, Eligibility) are normal
    # activatable tweaks once their structure passed the audit; only the
    # REMOVED_TWEAK_IDS tombstones above (structurally dead: wrong
    # domain/storage model, dead delivery channel, wrong value/type,
    # Settings duplicates) and the MobileGestalt gate above stay locked.
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

    The Eligibility files-based family (``ELIGIBILITY_BOUNDARY_TWEAK_IDS``)
    shares this decision's build boundary (blocked from iOS 26.2 beta 2
    up, user order 2026-10-03), so the same locked/unknown decision also
    force-clears those tweaks here — one clearer for everything the
    boundary locks, called from the same places as before.
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
        if not (requires_gestalt(tweak_id, tweak)
                or requires_eligibility_boundary(tweak_id)):
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
