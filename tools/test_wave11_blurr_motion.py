#!/usr/bin/env python3
"""Offline tests for the Blurr Motion integration (Wave 11).

Source dossier: ~/workspace/riset/wave11/DOSSIER-BLURR-MOTION.md — only
candidate B-1 (``SolariumIncreasedDiffusion``) passed the structural
audit: the key string exists in the iOS 23G83 binary inside the
DesignLibrary material cluster. This test pins the integration contract:

* one registry spec, section Liquid Glass, key
  ``SolariumIncreasedDiffusion``, managed ``.GlobalPreferences.plist``,
  bool ``True`` — and nothing else writes that key;
* it is a plain SWITCH (no slider/number control: no numeric schema is
  attested, so a numeric control would be an invented gimmick);
* it is a NORMAL tweak: deliverable on the audited target with reason
  ``OK`` — not removed, not audit-research-only, not a device-test
  candidate (so no UNPROVEN badge and no confirmation dialog path), and
  not MobileGestalt-gated;
* delivery is symmetric: enabled stages exactly
  ``{SolariumIncreasedDiffusion: True}`` into the managed GP payload,
  disabled stages nothing (and Reset Liquid Glass nulls that same GP
  file, so the key cannot survive a reset);
* the Home catalogue surfaces it automatically under Liquid Glass;
* the killed dossier candidates stay dead (no spec, still removed).

Run: python tools/test_wave11_blurr_motion.py
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
    # A PySide6 install whose QtWidgets cannot load (e.g. no system
    # libEGL on a headless box) is as good as absent for these
    # registry-level checks — fall back to the stub modules, exactly
    # like the other tools tests do when PySide6 is missing entirely.
    from PySide6 import QtWidgets  # noqa: F401
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
    canonical_tweak_id, is_audit_research_only, is_device_test_candidate,
    is_removed_tweak, requires_gestalt, tweak_deliverability,
)
from src.tweaks.registry import (
    SPECS, SPECS_BY_ID, SPECS_BY_SECTION, Kind, Section,
    home_tweak_catalogue,
)
from src.tweaks.tweaks import tweaks, TweakID

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def test_spec_shape():
    print("\nBlurr Motion spec shape (dossier B-1, nothing more)")
    spec = SPECS_BY_ID[TweakID.BlurrMotion]
    check("spec is in Liquid Glass", spec.section is Section.LIQUID_GLASS)
    check("spec renders in the Liquid Glass section list",
          TweakID.BlurrMotion in
          [s.id for s in SPECS_BY_SECTION[Section.LIQUID_GLASS]])
    check("title is Blurr Motion", spec.title == "Blurr Motion")
    check("key is the attested binary string",
          spec.key == "SolariumIncreasedDiffusion")
    check("primary domain is managed .GlobalPreferences.plist",
          spec.location is FileLocation.globalPreferences)
    check("location path is the managed GP path",
          spec.location.value
          == "/var/Managed Preferences/mobile/.GlobalPreferences.plist")
    check("value is bool True", spec.value is True)
    check("plain switch — NO slider/number control",
          spec.kind is Kind.SWITCH)
    check("no numeric range control is configured",
          spec.kind is not Kind.NUMBER)
    check("gated to iOS 26 like its family", spec.min_version == "26.0")
    check("description carries the honest grade (not proven)",
          spec.description is not None
          and "not proven" in spec.description)
    check("description makes no works claim",
          "works" not in (spec.description or "").lower().replace(
              "workslop", ""))

    writers = [
        s.id.name for s in SPECS
        if not s.disabled and s.factory is None
        and s.location is FileLocation.globalPreferences
        and s.key == "SolariumIncreasedDiffusion"
    ]
    check("registry has exactly one Blurr Motion writer",
          writers == ["BlurrMotion"], str(writers))

    # The alternate DesignLibrary domain is NOT integrated: nothing in the
    # registry writes com.apple.DesignLibrary.plist for this feature (the
    # dossier allows that second test only on an explicit user order).
    check("no spec targets the DesignLibrary plist",
          all("DesignLibrary" not in (s.location.value or "")
              for s in SPECS if not s.disabled))


def test_normal_tweak_no_badge_path():
    print("\nBlurr Motion is a normal tweak (no lock, no badge, no dialog)")
    check("canonical id resolves to itself",
          canonical_tweak_id(TweakID.BlurrMotion) is TweakID.BlurrMotion)
    check("not a removed tombstone",
          not is_removed_tweak(TweakID.BlurrMotion))
    check("not audit-research-only",
          not is_audit_research_only(TweakID.BlurrMotion))
    check("not a device-test candidate (=> no UNPROVEN badge, no "
          "confirmation dialog, no journal device-test path)",
          not is_device_test_candidate(TweakID.BlurrMotion))
    check("not MobileGestalt-gated",
          not requires_gestalt(TweakID.BlurrMotion))

    deliverable, reason, _msg = tweak_deliverability(
        TweakID.BlurrMotion, device_version="26.6.1", device_build="23G83")
    check("deliverable on the audited target 26.6.1/23G83",
          deliverable and reason == "OK", f"{deliverable} {reason}")
    deliverable, reason, _msg = tweak_deliverability(
        TweakID.BlurrMotion, device_version="26.0", device_build="")
    check("deliverable on iOS 26.0", deliverable and reason == "OK",
          f"{deliverable} {reason}")
    deliverable, reason, _msg = tweak_deliverability(
        TweakID.BlurrMotion, device_version="25.0", device_build="")
    check("still version-gated below iOS 26",
          not deliverable and reason == "VERSION_BELOW_MIN",
          f"{deliverable} {reason}")


def test_delivery_and_rollback_symmetry():
    print("\nBlurr Motion delivery + symmetric rollback")
    tweaks.pop(TweakID.BlurrMotion, None)
    tweak_loader.load_plist_tweaks()
    check("loader registers Blurr Motion", TweakID.BlurrMotion in tweaks)
    runtime = tweaks[TweakID.BlurrMotion]
    check("runtime tweak keeps GP location",
          runtime.file_location is FileLocation.globalPreferences)
    check("runtime tweak keeps key/value",
          runtime.key == "SolariumIncreasedDiffusion"
          and runtime.value is True)

    runtime.set_enabled(False)
    check("disabled stages nothing (rollback leaves no key behind)",
          runtime.apply_tweak({}) == {})
    runtime.set_enabled(True)
    payload = runtime.apply_tweak({})
    check("enabled stages exactly the one bool key into managed GP",
          payload == {FileLocation.globalPreferences:
                      {"SolariumIncreasedDiffusion": True}},
          str(payload))


def test_home_catalogue_surfaces_it():
    print("\nHome catalogue surfaces Blurr Motion automatically")
    by_name = {entry["id_name"]: entry
               for entry in home_tweak_catalogue()}
    check("catalogue lists Blurr Motion", "BlurrMotion" in by_name)
    check("catalogue places it under Liquid Glass",
          by_name["BlurrMotion"]["section"] is Section.LIQUID_GLASS)
    check("catalogue feature is Liquid Glass",
          by_name["BlurrMotion"]["feature"] == "Liquid Glass")


def test_killed_dossier_candidates_stay_dead():
    print("\nKilled dossier candidates were not integrated")
    # B-3: invented AI-claim name — zero hits in the 23G83 binary scan.
    check("no registry spec writes UIViewGlassBlurRadiusOverride",
          all(s.key != "UIViewGlassBlurRadiusOverride"
              for s in SPECS if not s.disabled))
    # B-2 is a separate later candidate: prepared, NOT integrated now.
    check("no registry spec writes SolariumTextFrost yet",
          all(s.key != "SolariumTextFrost"
              for s in SPECS if not s.disabled))
    # SolariumNoBlurReducedFrost was killed here as a wrong-direction
    # neighbour of SolariumIncreasedDiffusion — as a BLURR tweak. The
    # 2026-10-10 firmware research (iOS 26.1 23B85 vs 26.6.1 RC 23G82)
    # verified its reader alive in DesignLibrary and the user ordered
    # it in as its own honest experimental Liquid Glass spec instead,
    # so the key now legitimately exists (LGNoBlurReducedFrost); pin
    # its shape rather than its absence.
    check("SolariumNoBlurReducedFrost lives in its own v15 spec",
          SPECS_BY_ID[TweakID.LGNoBlurReducedFrost].key
          == "SolariumNoBlurReducedFrost")


def main():
    test_spec_shape()
    test_normal_tweak_no_badge_path()
    test_delivery_and_rollback_symmetry()
    test_home_catalogue_surfaces_it()
    test_killed_dossier_candidates_stay_dead()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
