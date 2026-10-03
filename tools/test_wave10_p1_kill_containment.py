#!/usr/bin/env python3
"""Offline tests for Wave 10 Package 1 (audit kill list + containment).

Covers AUDIT-FINAL-WAVE10 Package 1/3/4 decisions that were executed in
the registry and central capability gate:

* The kill-list registry rows are gone from SPECS_BY_ID and resolve as
  REMOVED_TWEAK tombstones; the five redundant duplicate rows alias to
  their canonical writers (checked separately below). The 2026-10-03
  verbatim v4 Liquid Glass restoration removed the Liquid Glass IDs from
  this kill list entirely — they are active v4 specs again, and this
  suite now pins them as RESTORED (spec present, not a tombstone).
* The five redundant duplicate IDs alias to exactly one canonical writer.
* Research-only IDs are classification only since Wave 11 (user order
  2026-10-03): they deliver as normal tweaks on iOS 26.6.1 / build 23G83,
  stale ON state is never force-cleared for that reason, and the
  user-retained FlatIconsEverywhere row stays active. Only the kill-list
  tombstones and MobileGestalt-gated rows stay locked.
* CustomGestaltTweaks is no longer rendered or applied as a product
  surface (static surface check; the backend only logs/ignores stale data).

Run: python tools/test_wave10_p1_kill_containment.py
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _install_pyside_stubs():
    class Dummy:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return Dummy()

        @staticmethod
        def tr(text, *args, **kwargs):
            return text

        @staticmethod
        def translate(_ctx, text, *args, **kwargs):
            return text

    def make_module(name):
        mod = types.ModuleType(name)

        def __getattr__(attr):
            if attr == "QT_TRANSLATE_NOOP":
                return lambda _ctx, text: text
            cls = type(attr, (Dummy,), {})
            setattr(mod, attr, cls)
            return cls

        mod.__getattr__ = __getattr__
        return mod

    for name in ("PySide6", "PySide6.QtCore", "PySide6.QtGui",
                 "PySide6.QtWidgets"):
        sys.modules[name] = make_module(name)
    sys.modules["PySide6"].QtCore = sys.modules["PySide6.QtCore"]
    sys.modules["PySide6"].QtGui = sys.modules["PySide6.QtGui"]
    sys.modules["PySide6"].QtWidgets = sys.modules["PySide6.QtWidgets"]


try:
    import PySide6  # noqa: F401
except Exception:
    _install_pyside_stubs()

try:
    import cffi  # noqa: F401
except Exception:
    _cffi = types.ModuleType("cffi")

    class _FFI:
        def cdef(self, *args, **kwargs):
            pass

        def new(self, *args, **kwargs):
            return object()

        def buffer(self, *args, **kwargs):
            return b""

    _cffi.FFI = _FFI
    sys.modules["cffi"] = _cffi

from src.tweaks import tweak_loader
from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.capabilities import (
    canonical_tweak_id, clear_audit_research_only_state,
    is_audit_research_only, is_device_test_tweak, is_removed_tweak,
    tweak_deliverability,
)
from src.tweaks.registry import SPECS, SPECS_BY_ID
from src.tweaks.tweak_classes import BasicPlistTweak
from src.tweaks.tweaks import tweaks, TweakID

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


TARGET = {"device_version": "26.6.1", "device_build": "23G83"}

REGISTRY_KILL_IDS = [
    # Settings-duplicates
    TweakID.SBMinimumLockscreenIdleTime, TweakID.ShowBatteryPercentage,
    TweakID.KbAutocorrect, TweakID.KbPrediction, TweakID.KbPredBar,
    TweakID.SiriEnabled, TweakID.SiriAutoPunct, TweakID.SiriVoiceTrigger,
    TweakID.SiriDataSharing,
    # Wrong domain / storage model (Notifications)
    TweakID.NotifDisplayStyle, TweakID.NotifPreview, TweakID.NotifScheduled,
    TweakID.NotifSummarize, TweakID.NotifAnnounce, TweakID.NotifHighlights,
    TweakID.NotifAlertType, TweakID.NotifGrouping, TweakID.NotifVisibility,
    TweakID.NotifPriority,
    # Wrong value / type
    TweakID.DisableSearchingWebsites, TweakID.SiriTriggerPhrase,
    TweakID.SiriVocab,
    # Dead Feature Flags channel (the five upstream FF specs stay dead)
    TweakID.ClockAnim, TweakID.Lockscreen,
    TweakID.PhotoUI, TweakID.AI, TweakID.KioskMode,
]

# v4 Liquid Glass IDs un-killed by the 2026-10-03 verbatim restoration:
# these resolve to their v4 specs again (payload proof lives in
# tools/test_wave11_lg_v4_verbatim.py). DisableCompactChrome is gated to
# iOS 27+ exactly as in v4, so on the 26.6.1 target it reports
# VERSION_BELOW_MIN, not OK.
RESTORED_V4_LG_IDS = [
    TweakID.DisableWidgetSpecular, TweakID.DisableDockSpecular,
    TweakID.DisableFolderSpecular, TweakID.ExcludeClearGlassShadows,
    TweakID.ExcludeDockShadow, TweakID.ExcludeSearchShadow,
    TweakID.DisableOuterRefraction, TweakID.DisableSolariumHDR,
    TweakID.DisableSpecularMotion, TweakID.DisableSpecularEverywhere,
]

DUPLICATE_ALIASES = {
    TweakID.SuppressDICompletely: TweakID.HideDICompletely,
    TweakID.DisableParallax: TweakID.SBDisableIconParallax,
    TweakID.HideSearchAffordance: TweakID.SBHideSearchAffordance,
    TweakID.IconVisibility: TweakID.SBIconVisibility,
    TweakID.DisableClockSeconds: TweakID.DisableSecondsHand,
}

SHIP_CANDIDATES = [
    TweakID.LockScreenFootnote, TweakID.AirDropDisableTimeLimit,
    TweakID.SBDontLockAfterCrash, TweakID.SBDontDimOrLockOnAC,
    TweakID.SBHideLowPowerAlerts, TweakID.SBHideACPower,
    TweakID.SBNeverBreadcrumb, TweakID.SBShowSupervisionTextOnLockScreen,
    TweakID.AirplaySupport, TweakID.SBAlwaysShowSystemApertureInSnapshots,
    TweakID.HideDICompletely, TweakID.SBShowAuthenticationEngineeringUI,
    TweakID.SBDisableIconParallax, TweakID.SBHideSearchAffordance,
]

REGISTRY_RESEARCH_IDS = [
    TweakID.WatchOSCompatibility,
    TweakID.CustomLockDate, TweakID.AnimDragCoeff, TweakID.ShowSystemServices,
    TweakID.SBBuildNumber, TweakID.RTL, TweakID.LTR, TweakID.SBIconVisibility,
    TweakID.iMessageDiagnosticsEnabled, TweakID.IDSDiagnosticsEnabled,
    TweakID.VCDiagnosticsEnabled, TweakID.AccessoryDeveloperEnabled,
    TweakID.KeyFlick, TweakID.DisableSecondsHand, TweakID.ShowButtonHints,
    TweakID.AppStoreDebug, TweakID.NotesDebugMode,
    TweakID.BKDigitizerVisualizeTouches, TweakID.BKHideAppleLogoOnLaunch,
    TweakID.EnableWakeGestureHaptic, TweakID.PlaySoundOnPaste,
    TweakID.AnnounceAllPastes, TweakID.KbGestureIntro, TweakID.KbAutoLists,
    TweakID.SiriSpeakerTTS, TweakID.SiriDeclined,
]


def test_registry_kills_and_tombstones():
    print("\nRegistry kill list is executed and tombstoned")
    for tid in REGISTRY_KILL_IDS:
        check(f"{tid.name} has no active spec", tid not in SPECS_BY_ID)
        check(f"{tid.name} is a removed tombstone", is_removed_tweak(tid))
        ok, code, _ = tweak_deliverability(tid, **TARGET)
        check(f"{tid.name} cannot deliver on target",
              not ok and code == "REMOVED_TWEAK", code)
    for tid in (TweakID.AIFeatureFlags, TweakID.AIFeatureFlagsUI):
        check(f"{tid.name} remains a removed tombstone", is_removed_tweak(tid))
        ok, code, _ = tweak_deliverability(tid, **TARGET)
        check(f"{tid.name} cannot deliver on target",
              not ok and code == "REMOVED_TWEAK", code)
    for tid in RESTORED_V4_LG_IDS:
        check(f"{tid.name} restored: has an active v4 spec",
              tid in SPECS_BY_ID)
        check(f"{tid.name} restored: not a tombstone",
              not is_removed_tweak(tid))
        ok, code, _ = tweak_deliverability(tid, **TARGET)
        check(f"{tid.name} restored: delivers on target",
              ok and code == "OK", code)
    ok, code, _ = tweak_deliverability(TweakID.DisableCompactChrome, **TARGET)
    check("DisableCompactChrome restored but v4-gated to iOS 27",
          not ok and code == "VERSION_BELOW_MIN", code)


def test_duplicate_aliases_have_one_writer():
    print("\nDuplicate rows alias to one canonical writer")
    for duplicate, canonical in DUPLICATE_ALIASES.items():
        check(f"{duplicate.name} has no active spec",
              duplicate not in SPECS_BY_ID)
        check(f"{duplicate.name} is not a removed tombstone",
              not is_removed_tweak(duplicate))
        check(f"{duplicate.name} aliases to {canonical.name}",
              canonical_tweak_id(duplicate) == canonical)
        check(f"{canonical.name} retains the active spec",
              canonical in SPECS_BY_ID)
    writers = {}
    for spec in SPECS:
        if spec.disabled or not spec.key or spec.factory is not None:
            continue
        writers.setdefault((spec.location, spec.key), []).append(spec.id.name)
    duplicates = {k: v for k, v in writers.items() if len(v) > 1}
    check("registry has one writer per (location, key)",
          not duplicates, str(duplicates))


def test_ship_candidates_remain_and_research_is_active():
    # Wave 11 spec (user order 2026-10-03): research-only classification
    # no longer contains delivery. Audit-passed rows — registry and
    # non-registry families alike — are normal activatable tweaks.
    print("\nShip-candidates remain; research-only rows are normal active tweaks")
    for tid in SHIP_CANDIDATES:
        check(f"{tid.name} retains an active spec", tid in SPECS_BY_ID)
        ok, code, _ = tweak_deliverability(tid, **TARGET)
        check(f"{tid.name} passes the central gate for verification",
              ok, code)
    for tid in REGISTRY_RESEARCH_IDS:
        check(f"{tid.name} retains a research spec", tid in SPECS_BY_ID)
        check(f"{tid.name} is audit research-only", is_audit_research_only(tid))
        ok, code, msg = tweak_deliverability(tid, **TARGET)
        check(f"{tid.name} delivers as a normal tweak (Wave 11)",
              ok and code == "OK" and "UNPROVEN" not in msg, code)
    for tid in (TweakID.DisableOTAFile,
                TweakID.CustomResolution, TweakID.StatusBar, TweakID.Daemons,
                TweakID.PosterBoard, TweakID.Templates):
        ok, code, _ = tweak_deliverability(tid, **TARGET)
        check(f"non-registry {tid.name} delivers as a normal tweak (Wave 11)",
              ok and code == "OK", code)
    # Eligibility exception (user order 2026-10-03, final build): the
    # Eligibility family (EUEnabler / AIEligibility / CreateBRFolders) is
    # blocked from iOS 26.2 beta 2 upward under the SAME shared
    # MobileGestalt build boundary — locked on the 26.6.1 target, still
    # open through iOS 26.2 beta 1. Full matrix in
    # tools/test_eligibility_boundary.py.
    for tid in (TweakID.EUEnabler, TweakID.AIEligibility,
                TweakID.CreateBRFolders):
        ok, code, _ = tweak_deliverability(tid, **TARGET)
        check(f"non-registry {tid.name} is build-locked on the target "
              f"(Eligibility boundary)", not ok and code != "OK", code)
        ok, code, _ = tweak_deliverability(
            tid, device_version="26.2", device_build="23C5027f")
        check(f"non-registry {tid.name} still delivers through 26.2 beta 1",
              ok and code == "OK", code)
    ok, code, _ = tweak_deliverability(
        TweakID.EUEnabler, device_version="26.1", device_build="")
    check("research rows also deliver off-target", ok, code)

    check("FlatIconsEverywhere retains an active spec",
          TweakID.FlatIconsEverywhere in SPECS_BY_ID)
    check("FlatIconsEverywhere is not research-contained",
          not is_audit_research_only(TweakID.FlatIconsEverywhere))
    ok, code, _ = tweak_deliverability(TweakID.FlatIconsEverywhere, **TARGET)
    check("FlatIconsEverywhere stays active by user order", ok, code)


DEVICE_TEST_IDS = [
    TweakID.SolariumForceFallback, TweakID.DisallowGlassTime,
    TweakID.DisableGlassDock,
]


def test_device_test_candidates_are_open_but_labelled():
    # Renamed in behaviour by the 2026-10-03 verbatim v4 restoration: the
    # three Liquid Glass rows are normal tweaks now — no DEVICE_TEST_OK
    # reason code, no UNPROVEN message, no device-test classification.
    print("\nRestored Liquid Glass rows are normal tweaks (2026-10-03)")
    for tid in DEVICE_TEST_IDS:
        check(f"{tid.name} retains an active v4 spec", tid in SPECS_BY_ID)
        check(f"{tid.name} is not a device-test tweak",
              not is_device_test_tweak(tid))
        check(f"{tid.name} is not audit research-contained",
              not is_audit_research_only(tid))
        ok, code, msg = tweak_deliverability(tid, **TARGET)
        check(f"{tid.name} delivers on target as a normal tweak",
              ok and code == "OK", code)
        check(f"{tid.name} deliverability message has no UNPROVEN label",
              "UNPROVEN" not in msg, msg[:40])
    # ON state for a restored (former device-test) row is not touched by
    # the research containment sweep: it is an ordinary active tweak.
    dummy = _DummyTweak()
    cleared = clear_audit_research_only_state(
        "26.6.1", "23G83",
        tweaks_dict={TweakID.SolariumForceFallback: dummy})
    check("restored row state survives the research clear",
          cleared == [] and dummy.enabled)
    # ...and a non-registry research family is a normal tweak now too
    # (Wave 11, user order 2026-10-03).
    ok, code, _ = tweak_deliverability(TweakID.StatusBar, **TARGET)
    check("non-registry research family is a normal tweak (Wave 11)",
          ok and code == "OK", code)
    # K1 (GlassLegibility2) was un-killed by the 2026-10-03 verbatim v4
    # restoration: it is an active v4 spec and delivers as a normal tweak.
    ok, code, _ = tweak_deliverability(TweakID.GlassLegibility2, **TARGET)
    check("K1 restored: delivers as normal tweak",
          ok and code == "OK", code)


class _DummyTweak:
    def __init__(self):
        self.enabled = True

    def set_enabled(self, value):
        self.enabled = value


def test_stale_state_and_loader_cleanup():
    print("\nStale research/removed/duplicate state cannot survive loading")
    dummy = _DummyTweak()
    cleared = clear_audit_research_only_state(
        "26.6.1", "23G83", tweaks_dict={TweakID.AnimDragCoeff: dummy})
    check("registry research rows are NOT force-cleared (Wave 11)",
          cleared == [] and dummy.enabled, str(cleared))
    dummy2 = _DummyTweak()
    cleared = clear_audit_research_only_state(
        "26.6.1", "23G83", tweaks_dict={TweakID.StatusBar: dummy2})
    check("non-registry research family is NOT force-cleared either (Wave 11)",
          cleared == [] and dummy2.enabled is True, str(cleared))
    dummy.enabled = True
    cleared = clear_audit_research_only_state(
        "26.1", "", tweaks_dict={TweakID.AnimDragCoeff: dummy})
    check("non-target clear is a no-op", cleared == [] and dummy.enabled)

    tweaks[TweakID.KbAutocorrect] = BasicPlistTweak(
        FileLocation.globalPreferences, "KeyboardAutocorrection")
    tweaks[TweakID.HideSearchAffordance] = BasicPlistTweak(
        FileLocation.springboard, "SBHomeScreenShowsSearchAffordance",
        value=False)
    tweak_loader.load_plist_tweaks()
    check("loader drops stale removed instances",
          TweakID.KbAutocorrect not in tweaks)
    check("loader drops stale duplicate instances",
          TweakID.HideSearchAffordance not in tweaks)
    check("loader keeps the canonical Hide Search writer",
          TweakID.SBHideSearchAffordance in tweaks)
    check("loader keeps user-retained FlatIconsEverywhere",
          TweakID.FlatIconsEverywhere in tweaks)


def test_custom_gestalt_surface_is_killed():
    print("\nCustomGestaltTweaks product surface is killed")
    root = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(root, "src/gui/ios/mobilegestalt.py"),
              encoding="utf-8") as f:
        gui_text = f.read()
    with open(os.path.join(root, "src/devicemanagement/device_manager.py"),
              encoding="utf-8") as f:
        backend_text = f.read()
    check("MobileGestalt page renders no Custom Gestalt Keys section",
          "Custom Gestalt Keys" not in gui_text)
    check("MobileGestalt page has no custom-key creation handler",
          "_on_add_custom_key" not in gui_text)
    check("backend never applies CustomGestaltTweaks payload",
          "CustomGestaltTweaks.apply_tweaks" not in backend_text)


test_registry_kills_and_tombstones()
test_duplicate_aliases_have_one_writer()
test_ship_candidates_remain_and_research_is_active()
test_stale_state_and_loader_cleanup()
test_device_test_candidates_are_open_but_labelled()
test_custom_gestalt_surface_is_killed()

print(f"\nALL {PASS} CHECKS PASSED")
