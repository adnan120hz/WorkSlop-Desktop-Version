#!/usr/bin/env python3
"""Offline tests for the Wave 10 Home / Hide Search package.

Covers, without a device:

* canonical ``SBHideSearchAffordance`` is presented in Section.LIQUID_GLASS,
  not SpringBoard, with its payload unchanged (managed SpringBoard location,
  key ``SBHomeScreenShowsSearchAffordance``, value False);
* the retired ``HideSearchAffordance`` name has no spec of its own, aliases
  to the canonical ID, and the loader keeps exactly one runtime writer;
* HotLoad feature membership follows the section move automatically;
* the Home catalogue is derived from the live registry sections, so a
  synthetic new registry entry is listed without editing Home;
* the user-retained ``FlatIconsEverywhere`` exception stays in Liquid Glass.

Run: python tools/test_wave10_home_hide_search.py
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

from src.controllers.hotload import FEATURE_TWEAKS
from src.tweaks import tweak_loader
from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.capabilities import canonical_tweak_id, is_audit_user_retained
from src.tweaks.registry import (
    SPECS, SPECS_BY_ID, SPECS_BY_SECTION, Section, TweakSpec,
    home_tweak_catalogue,
)
from src.tweaks.tweaks import tweaks, TweakID

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def test_hide_search_section_and_single_writer():
    print("\nHide Search canonical presentation + single writer")
    spec = SPECS_BY_ID[TweakID.SBHideSearchAffordance]
    check("canonical Hide Search spec is in Liquid Glass",
          spec.section is Section.LIQUID_GLASS)
    check("canonical Hide Search is not rendered from SpringBoard specs",
          TweakID.SBHideSearchAffordance not in
          [s.id for s in SPECS_BY_SECTION[Section.SPRINGBOARD]])
    check("canonical Hide Search is in Liquid Glass specs",
          TweakID.SBHideSearchAffordance in
          [s.id for s in SPECS_BY_SECTION[Section.LIQUID_GLASS]])
    check("payload location unchanged", spec.location is FileLocation.springboard)
    check("payload key unchanged",
          spec.key == "SBHomeScreenShowsSearchAffordance")
    check("payload value unchanged", spec.value is False)

    check("duplicate HideSearchAffordance has no active spec",
          TweakID.HideSearchAffordance not in SPECS_BY_ID)
    check("duplicate name aliases to canonical",
          canonical_tweak_id(TweakID.HideSearchAffordance)
          is TweakID.SBHideSearchAffordance)

    writers = [
        s.id.name for s in SPECS
        if not s.disabled and s.factory is None
        and s.location is FileLocation.springboard
        and s.key == "SBHomeScreenShowsSearchAffordance"
    ]
    check("registry has exactly one Hide Search writer",
          writers == ["SBHideSearchAffordance"], str(writers))

    tweaks.pop(TweakID.HideSearchAffordance, None)
    tweak_loader.load_plist_tweaks()
    check("loader registers canonical Hide Search",
          TweakID.SBHideSearchAffordance in tweaks)
    check("loader does not register duplicate Hide Search",
          TweakID.HideSearchAffordance not in tweaks)
    runtime = tweaks[TweakID.SBHideSearchAffordance]
    check("runtime tweak keeps SpringBoard location",
          runtime.file_location is FileLocation.springboard)
    check("runtime tweak keeps key/value",
          runtime.key == "SBHomeScreenShowsSearchAffordance"
          and runtime.value is False)


def test_hotload_feature_membership_follows_section():
    print("\nHotLoad feature membership follows the section move")
    check("SBHideSearchAffordance belongs to Liquid Glass feature",
          "SBHideSearchAffordance" in FEATURE_TWEAKS["Liquid Glass"])
    check("SBHideSearchAffordance no longer belongs to Springboard feature",
          "SBHideSearchAffordance" not in FEATURE_TWEAKS["Springboard"])
    check("duplicate name is not a separate HotLoad member",
          "HideSearchAffordance" not in FEATURE_TWEAKS["Liquid Glass"]
          and "HideSearchAffordance" not in FEATURE_TWEAKS["Springboard"])


def test_home_catalogue_is_registry_derived():
    print("\nHome catalogue derives from the registry")
    entries = home_tweak_catalogue()
    by_name = {entry["id_name"]: entry for entry in entries}
    check("catalogue lists canonical Hide Search",
          "SBHideSearchAffordance" in by_name)
    check("catalogue places Hide Search under Liquid Glass",
          by_name["SBHideSearchAffordance"]["section"] is Section.LIQUID_GLASS)
    check("catalogue feature for Hide Search is Liquid Glass",
          by_name["SBHideSearchAffordance"]["feature"] == "Liquid Glass")
    check("catalogue has no duplicate Hide Search entry",
          "HideSearchAffordance" not in by_name)
    check("catalogue keeps FlatIconsEverywhere in Liquid Glass",
          by_name["FlatIconsEverywhere"]["section"] is Section.LIQUID_GLASS)
    check("FlatIconsEverywhere remains the user-retained exception",
          is_audit_user_retained(TweakID.FlatIconsEverywhere))

    synthetic = TweakSpec(
        id=TweakID.StatusBar,
        section=Section.LIQUID_GLASS,
        title="Synthetic Home Probe",
        location=FileLocation.springboard,
        key="SyntheticHomeProbe",
        value=False,
    )
    SPECS_BY_SECTION[Section.LIQUID_GLASS].append(synthetic)
    try:
        refreshed = {entry["id_name"]: entry
                     for entry in home_tweak_catalogue()}
        check("synthetic new registry entry appears automatically",
              "StatusBar" in refreshed
              and refreshed["StatusBar"]["title"] == "Synthetic Home Probe")
        injected = home_tweak_catalogue(
            {Section.LIQUID_GLASS: [synthetic]})
        check("injectable catalogue source lists only the synthetic entry",
              len(injected) == 1
              and injected[0]["id_name"] == "StatusBar")
    finally:
        SPECS_BY_SECTION[Section.LIQUID_GLASS].remove(synthetic)


test_hide_search_section_and_single_writer()
test_hotload_feature_membership_follows_section()
test_home_catalogue_is_registry_derived()

print(f"\nALL {PASS} CHECKS PASSED")
