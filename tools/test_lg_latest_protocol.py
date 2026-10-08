#!/usr/bin/env python3
"""Offline tests for the Liquid Glass (Latest) payload.

Pins the payload contract (see src/tweaks/lg_latest.py):

* the registry carries one switch, LGDisableLatest, in the Liquid
  Glass Disable section, built by its own factory, while the removed
  Beta 1 G1/G2 routes have NO spec and their IDs are recorded as
  removed tombstones (v14.0);
* the apply planner merges the device's own three files: the SwiftUI
  file gains SolariumForceFallback as a real bool true (created from an
  empty base when the device does not carry it yet), .GlobalPreferences
  gains exactly the two lock-screen keys, and the SpringBoard file
  gains the specular key — the payload bytes are NEVER empty;
* every merge keeps 100% of the device's original keys, and the plan
  refuses (NuggetException) without a .GlobalPreferences.plist base;
* rollback plans from FRESH captures: exactly this payload's keys are
  removed from the three files, every other key survives, and a file
  absent from the fresh capture yields no payload;
* the tweak stages nothing through the sparse dict and fails closed
  without an armed base.

Delivery honesty (step8 audit S8): the SolariumForceFallback reader is
firmware-verified alive in iOS 26.6.1, but the on-screen effect is NOT
proven — these tests pin the payload, never an effect claim.

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
from src.tweaks import lg_disable, lg_latest, tweak_loader
from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.capabilities import is_removed_tweak, tweak_deliverability
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


def test_registry_shape():
    print("\nregistry shape (+ v14.0 G1/G2 removal)")
    spec = SPECS_BY_ID[TweakID.LGDisableLatest]
    check("Latest spec lives in the LGD section",
          spec.section is Section.LIQUID_GLASS_DISABLE)
    check("section holds Squair (test) + Latest only",
          [s.id for s in SPECS_BY_SECTION[Section.LIQUID_GLASS_DISABLE]]
          == [TweakID.LGDisableSquairTest, TweakID.LGDisableLatest],
          str([s.id.name
               for s in SPECS_BY_SECTION[Section.LIQUID_GLASS_DISABLE]]))
    check("removed G1/G2 have no registry spec",
          TweakID.LGDisableG1 not in SPECS_BY_ID
          and TweakID.LGDisableG2 not in SPECS_BY_ID)
    check("G1/G2 are recorded removed tombstones (old names still parse)",
          is_removed_tweak(TweakID.LGDisableG1)
          and is_removed_tweak(TweakID.LGDisableG2)
          and TweakID["LGDisableG1"] is TweakID.LGDisableG1)
    check("Squair + Latest are NOT removed",
          not is_removed_tweak(TweakID.LGDisableSquairTest)
          and not is_removed_tweak(TweakID.LGDisableLatest))
    check("spec mirrors the HomeDomain GP file",
          spec.location is FileLocation.globalPreferencesHomeDomain)
    check("declared value is a real bool True", spec.value is True
          and type(spec.value) is bool)
    check("gated to iOS 26+", spec.min_version == "26.0")
    check("description carries the honest device-test grade",
          "isolated device test" in (spec.description or "").lower()
          and "verified alive" in (spec.description or "").lower())
    ids = {e["id"] for e in home_tweak_catalogue()}
    check("Home catalogue surfaces Squair + Latest, not G1/G2",
          {TweakID.LGDisableSquairTest, TweakID.LGDisableLatest} <= ids
          and TweakID.LGDisableG1 not in ids
          and TweakID.LGDisableG2 not in ids)
    tweak_loader.load_plist_tweaks()
    tweak = tweaks[TweakID.LGDisableLatest]
    check("factory built the Latest tweak class",
          isinstance(tweak, lg_latest.LGDLatestTweak))
    check("no runtime instance exists for the removed routes",
          TweakID.LGDisableG1 not in tweaks
          and TweakID.LGDisableG2 not in tweaks)
    ok, code, _msg = tweak_deliverability(
        TweakID.LGDisableLatest, device_version="26.6.1",
        device_build="23G82", is_iphone=True, tweak=tweak)
    check("deliverable on 26.6.1/23G82", ok and code == "OK", code)
    ok, code, _msg = tweak_deliverability(
        TweakID.LGDisableLatest, device_version="25.0",
        device_build="", is_iphone=True, tweak=tweak)
    check("locked below iOS 26", not ok and code == "VERSION_BELOW_MIN",
          code)


def test_apply_planner():
    print("\napply planner (three-file merge)")
    payloads = lg_latest.plan_latest_apply_payloads(
        dict(GP_BASE), dict(SWIFTUI_BASE), dict(SB_BASE))
    check("plan yields exactly three inject tuples", len(payloads) == 3)
    check("all tuples target HomeDomain with forced metadata",
          all(p[0] == "HomeDomain" and p[3] == 0o100644
              and p[4] == 501 and p[5] == 501 for p in payloads))

    swiftui = _payload(payloads, lg_latest.SWIFTUI_REL_PATH)
    parsed = _parsed(swiftui)
    check("SwiftUI keeps every device key (superset merge)",
          all(parsed.get(k) == v for k, v in SWIFTUI_BASE.items()))
    check("SwiftUI carries SolariumForceFallback",
          parsed.get("SolariumForceFallback") is True)
    check("SolariumForceFallback is a real bool (not int 1)",
          type(parsed.get("SolariumForceFallback")) is bool)

    gp = _payload(payloads, lg_latest.G1_REL_PATH)
    parsed = _parsed(gp)
    check(".GlobalPreferences keeps every device key",
          all(parsed.get(k) == v for k, v in GP_BASE.items()))
    for key in lg_latest.GP_KEYS:
        check(f".GlobalPreferences carries {key} as a real bool true",
              parsed.get(key) is True and type(parsed.get(key)) is bool)

    sb = _payload(payloads, lg_latest.SB_REL_PATH)
    parsed = _parsed(sb)
    check("SpringBoard keeps every device key",
          all(parsed.get(k) == v for k, v in SB_BASE.items()))
    check("SpringBoard carries the specular key as a real bool true",
          parsed.get(lg_latest.SB_KEY) is True
          and type(parsed.get(lg_latest.SB_KEY)) is bool)
    check("SpringBoard payload bytes are never empty",
          len(sb[2]) > 0 and isinstance(parsed, dict))

    # SwiftUI file absent on device -> created from an empty base.
    payloads = lg_latest.plan_latest_apply_payloads(dict(GP_BASE))
    swiftui = _payload(payloads, lg_latest.SWIFTUI_REL_PATH)
    check("absent SwiftUI file is created with exactly our key",
          _parsed(swiftui) == {"SolariumForceFallback": True})
    sb = _payload(payloads, lg_latest.SB_REL_PATH)
    check("absent SpringBoard file still yields a non-empty payload",
          _parsed(sb) == {lg_latest.SB_KEY: True} and len(sb[2]) > 0)

    # extra_inserts ride the GP merge (same-pass deliberate keys).
    payloads = lg_latest.plan_latest_apply_payloads(
        dict(GP_BASE), None, None,
        extra_inserts={"StagedByOtherTweak": True})
    gp = _payload(payloads, lg_latest.G1_REL_PATH)
    check("extra_inserts ride the .GlobalPreferences merge",
          _parsed(gp).get("StagedByOtherTweak") is True)

    # Fail closed: no GP base, no plan.
    for bad_base in (None, "not-a-dict", 42):
        try:
            lg_latest.plan_latest_apply_payloads(bad_base)
            raised = False
        except NuggetException:
            raised = True
        check(f"plan refuses a missing/unusable GP base ({bad_base!r})",
              raised)
    # Fail closed: an unusable SwiftUI base is refused, never dropped.
    try:
        lg_latest.plan_latest_apply_payloads(
            dict(GP_BASE), swiftui_base="not-a-dict")
        raised = False
    except NuggetException:
        raised = True
    check("plan refuses an unparseable SwiftUI base", raised)


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


def test_tweak_staging_contract():
    print("\ntweak staging contract (never the sparse pass)")
    tweak = tweaks[TweakID.LGDisableLatest]
    tweak.set_enabled(True)
    tweak._lgd_gp_base = None
    staged = tweak.apply_tweak({})
    check("unarmed (no device base) stages nothing and is not staged",
          staged == {} and tweak.staged is False)
    tweak._lgd_gp_base = dict(GP_BASE)
    tweak._lgd_swiftui_base = dict(SWIFTUI_BASE)
    tweak._lgd_springboard_base = dict(SB_BASE)
    staged = tweak.apply_tweak({})
    check("armed tweak marks staged without touching the sparse dict",
          staged == {} and tweak.staged is True)
    tweak._lgd_gp_base = None
    tweak._lgd_swiftui_base = None
    tweak._lgd_springboard_base = None
    tweak.set_enabled(False)
    staged = tweak.apply_tweak({})
    check("disabled tweak is never staged",
          staged == {} and tweak.staged is False)


def main():
    test_registry_shape()
    test_apply_planner()
    test_rollback_planner()
    test_tweak_staging_contract()
    print(f"\n{PASS} checks passed")


if __name__ == "__main__":
    main()
