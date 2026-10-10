#!/usr/bin/env python3
"""Offline tests for the Liquid Glass (Latest) REMOVAL contract (v15).

The "Liquid Glass (Latest)" full-backup payload — the "Liquid Glass
iOS 26.6.1 RC S8" switch — was removed from the product in v15 by
explicit user order (2026-10-10) after the author's own iOS 26.6.1
device test showed no on-screen effect. This file replaces the old
apply-protocol suite for that payload and pins the removal instead:

* the registry carries NO spec for LGDisableLatest, the Liquid Glass
  Disable section holds the Squair test payload only, and the Home
  catalogue no longer surfaces it;
* the TweakID enum member survives as a tombstone (old presets and
  journals still parse the name) and is recorded in REMOVED_TWEAK_IDS,
  so it resolves to removed/skipped — never to a tweak instance;
* no runtime instance exists and the DeviceManager apply path can no
  longer arm, stage, or deliver it (the marker bridge is gone);
* the rollback planner in src/tweaks/lg_latest.py SURVIVES, so a
  device that applied the payload under v14 can still strip exactly
  its four keys from fresh captures — removal planning is surgical,
  keeps every unrelated key, and fails closed without a fresh
  .GlobalPreferences.plist capture;
* the firmware-research specs that replace the hunt
  (LGForceFallbackUIKit / LGNoBlurReducedFrost) carry the exact
  firmware keys, the audited reader-home locations, a real bool
  true, the iOS 26+ gate, and the honest not-proven description
  grade. (LGForceFallbackSwiftUI was removed in v15.1: on the
  author's device the key worked but could not be switched back
  off; it is a tombstone now, and the Remove Tweaks dialog stages
  its key = false into com.apple.SwiftUI.plist instead.)

Run: python tools/test_lg_latest_protocol.py
"""
import os
import plistlib
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_STORE_TMP = tempfile.mkdtemp(prefix="lgd_latest_test_store_")
os.environ["LGD_STORE_DIR"] = _STORE_TMP


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
    from PySide6 import QtWidgets  # noqa: F401
except Exception:
    _install_pyside_stubs()

from src.exceptions.nugget_exception import NuggetException
from src.tweaks import lg_latest, tweak_loader
from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.capabilities import is_removed_tweak
from src.tweaks.registry import (
    SPECS_BY_ID, SPECS_BY_SECTION, Section, home_tweak_catalogue,
)
from src.tweaks.tweaks import tweaks, TweakID

PASS = 0

GP_BASE = {
    "AppleLanguages": ["en-US", "id-ID"],
    "AppleLocale": "en_US",
    "NSForceRightToLeftWritingDirection": False,
    "AKLastIDMSEnvironment": 0,
}
SWIFTUI_BASE = {"ExistingSwiftUIKey": "keep", "Another": 3}
SB_BASE = {"SBExisting": True, "SBNumber": 42}


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def _payload(payloads, rel_path):
    for p in payloads:
        if p[1] == rel_path:
            return p
    raise AssertionError(f"no payload for {rel_path}")


def _parsed(payload):
    return plistlib.loads(payload[2])


def test_removal_shape():
    print("\nremoval shape (v15: S8/Latest retired)")
    check("no registry spec for LGDisableLatest",
          TweakID.LGDisableLatest not in SPECS_BY_ID)
    check("LGD section holds the Squair test payload only",
          [s.id for s in SPECS_BY_SECTION[Section.LIQUID_GLASS_DISABLE]]
          == [TweakID.LGDisableSquairTest],
          str([s.id.name
               for s in SPECS_BY_SECTION[Section.LIQUID_GLASS_DISABLE]]))
    check("removed G1/G2 still have no registry spec",
          TweakID.LGDisableG1 not in SPECS_BY_ID
          and TweakID.LGDisableG2 not in SPECS_BY_ID)
    check("LGDisableLatest is a recorded removed tombstone",
          is_removed_tweak(TweakID.LGDisableLatest))
    check("G1/G2 remain recorded removed tombstones",
          is_removed_tweak(TweakID.LGDisableG1)
          and is_removed_tweak(TweakID.LGDisableG2))
    check("old names still parse (presets/journals keep loading)",
          TweakID["LGDisableLatest"] is TweakID.LGDisableLatest
          and TweakID["LGDisableG1"] is TweakID.LGDisableG1)
    check("Squair is NOT removed",
          not is_removed_tweak(TweakID.LGDisableSquairTest))
    ids = {e["id"] for e in home_tweak_catalogue()}
    check("Home catalogue surfaces Squair, not Latest/G1/G2",
          TweakID.LGDisableSquairTest in ids
          and TweakID.LGDisableLatest not in ids
          and TweakID.LGDisableG1 not in ids
          and TweakID.LGDisableG2 not in ids)
    tweak_loader.load_plist_tweaks()
    check("no runtime instance exists for any removed route",
          TweakID.LGDisableLatest not in tweaks
          and TweakID.LGDisableG1 not in tweaks
          and TweakID.LGDisableG2 not in tweaks)
    check("the Squair instance still loads",
          TweakID.LGDisableSquairTest in tweaks)
    dm_path = os.path.join(os.path.dirname(__file__), "..", "src",
                           "devicemanagement", "device_manager.py")
    with open(dm_path, encoding="utf-8") as fh:
        dm_src = fh.read()
    check("apply path can no longer arm Latest",
          "_lgd_prepare_latest" not in dm_src
          and "plan_latest_apply_payloads" not in dm_src)
    check("rollback planner is still wired into DeviceManager",
          "plan_latest_rollback_payloads" in dm_src)


def test_rollback_planner():
    print("\nrollback planner (fresh capture, surgical removal)")
    fresh_gp = dict(GP_BASE)
    fresh_gp.update({k: True for k in lg_latest.GP_KEYS})
    fresh_gp["SolariumForceFallback"] = True  # unrelated here: keep
    fresh_sw = dict(SWIFTUI_BASE)
    fresh_sw["SolariumForceFallback"] = True
    fresh_sb = dict(SB_BASE)
    fresh_sb[lg_latest.SB_KEY] = True
    payloads, note = lg_latest.plan_latest_rollback_payloads(
        fresh_gp, fresh_sw, fresh_sb)
    check("rollback yields three payloads + honest note",
          len(payloads) == 3 and "were removed" in note)
    gp = _parsed(_payload(payloads, lg_latest.G1_REL_PATH))
    check("rollback removes exactly the two GP keys",
          all(k not in gp for k in lg_latest.GP_KEYS)
          and all(gp.get(k) == v for k, v in GP_BASE.items()))
    check("rollback keeps an unrelated SolariumForceFallback in GP",
          gp.get("SolariumForceFallback") is True)
    sw = _parsed(_payload(payloads, lg_latest.SWIFTUI_REL_PATH))
    check("rollback removes SolariumForceFallback from SwiftUI only",
          "SolariumForceFallback" not in sw
          and all(sw.get(k) == v for k, v in SWIFTUI_BASE.items()))
    sb_payload = _payload(payloads, lg_latest.SB_REL_PATH)
    sb = _parsed(sb_payload)
    check("rollback removes the specular key, keeps the rest, non-empty",
          lg_latest.SB_KEY not in sb
          and all(sb.get(k) == v for k, v in SB_BASE.items())
          and len(sb_payload[2]) > 0)

    # Files absent from the fresh capture yield no payload for them.
    payloads, _ = lg_latest.plan_latest_rollback_payloads(fresh_gp)
    check("absent SwiftUI/SpringBoard captures yield only the GP payload",
          len(payloads) == 1
          and payloads[0][1] == lg_latest.G1_REL_PATH)

    # Fail closed without a fresh GP capture.
    try:
        lg_latest.plan_latest_rollback_payloads(None)
        raised = False
    except NuggetException:
        raised = True
    check("rollback refuses without a fresh GP capture", raised)


def test_replacement_specs():
    print("\nfirmware-research replacement specs (2026-10-10)")
    cases = (
        (TweakID.LGForceFallbackUIKit, "UISolariumForceFallback",
         FileLocation.uikit),
        (TweakID.LGNoBlurReducedFrost, "SolariumNoBlurReducedFrost",
         FileLocation.swiftui),
    )
    # v15.1: the SwiftUI enable switch is a tombstone. On the author's
    # iOS 26.6.1 device the key WORKED (glass off) but could not be
    # taken back — a disabled spec stages no file, and no page reset
    # rewrites com.apple.SwiftUI.plist. It must never resolve to an
    # active spec again; the Remove Tweaks dialog stages
    # SolariumForceFallback = false into that file instead.
    check("LGForceFallbackSwiftUI: tombstoned, no active spec",
          TweakID.LGForceFallbackSwiftUI not in SPECS_BY_ID
          and is_removed_tweak(TweakID.LGForceFallbackSwiftUI))
    for tid, key, location in cases:
        spec = SPECS_BY_ID[tid]
        check(f"{tid.name}: lives in the Liquid Glass section",
              spec.section is Section.LIQUID_GLASS)
        check(f"{tid.name}: exact firmware key", spec.key == key,
              spec.key)
        check(f"{tid.name}: audited reader-home location",
              spec.location is location, spec.location.value)
        check(f"{tid.name}: real bool true", spec.value is True
              and type(spec.value) is bool)
        check(f"{tid.name}: gated to iOS 26+", spec.min_version == "26.0")
        check(f"{tid.name}: not removed",
              not is_removed_tweak(tid))
        desc = (spec.description or "").lower()
        check(f"{tid.name}: description carries the honest grade",
              "not proven" in desc and "isolated device test" in desc)
    check("FileLocation.swiftui is the SwiftUI suite file",
          FileLocation.swiftui.value
          == "/var/mobile/Library/Preferences/com.apple.SwiftUI.plist")


def main():
    test_removal_shape()
    test_rollback_planner()
    test_replacement_specs()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
