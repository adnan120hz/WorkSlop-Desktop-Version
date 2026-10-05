#!/usr/bin/env python3
"""Offline tests for Liquid Glass Disable (Beta 1).

The payload/verify logic is adapted from the offline payload-lab
(~/workspace/riset/lg-global-plist/payload-lab/: g1_payload.py,
g2_payload.py, restore_map.py, rollback.py, verify_gate.py — 14/14 tests
+ 11/11 gate checks green there). This suite pins the same contract
against the repo integration:

* two registry specs in the new "Liquid Glass Disable (Beta 1)" section
  (G2 managed overlay / G1 HomeDomain device-file merge), both writing
  SolariumForceFallback with a REAL bool True, gated to iOS 26+;
* the frozen v4 set is untouched (its own SolariumForceFallback spec
  still builds a plain BasicPlistTweak exactly as before);
* G2 staging lands in the managed overlay dict; the apply gate accepts
  the resulting restore record and rejects wrong-type / missing records;
* G1 staging merges into the captured device base (never a tweak-only
  dict), fails closed without a base, and the fail-hard diff gate keeps
  100% of the original keys (lab parity: LOST / CHANGED / unexpected NEW
  all fail; another tweak's deliberately staged key is the only allowed
  difference);
* the rollback store keeps the FIRST captured original (never
  overwritten by a later, possibly already-tweaked file);
* domain/path constants match src.restore.path_mapping (drift guard).

Run: python tools/test_liquid_glass_disable.py
"""
import os
import plistlib
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_STORE_TMP = tempfile.mkdtemp(prefix="lgd_test_store_")
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


_REAL_QT = True
try:
    # A PySide6 install whose QtWidgets cannot load (e.g. no system
    # libEGL on a headless box) is as good as absent for these
    # registry-level checks — fall back to the stub modules, exactly
    # like the other tools tests do when PySide6 is missing entirely.
    from PySide6 import QtWidgets  # noqa: F401
except Exception:
    _REAL_QT = False
    _install_pyside_stubs()

from src.tweaks import lg_disable, tweak_loader
from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.capabilities import tweak_deliverability
from src.tweaks.registry import (
    SPECS_BY_ID, SPECS_BY_SECTION, SECTION_FEATURES, Kind, Section,
    home_tweak_catalogue,
)
from src.tweaks.tweak_classes import BasicPlistTweak
from src.tweaks.tweaks import tweaks, TweakID
from src.utils.file_to_restore import FileToRestore

PASS = 0
KEY = lg_disable.GP_KEY


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def _record(domain, rel_path, contents):
    return FileToRestore(contents=contents, restore_path=rel_path,
                         domain=domain, owner=501, group=501)


def _gate(files, **kwargs):
    return lg_disable.verify_apply_gate(files, **kwargs)


def test_registry_shape():
    print("\nregistry shape")
    check("section name is the feature name",
          Section.LIQUID_GLASS_DISABLE.value == "Liquid Glass Disable (Beta 1)")
    specs = SPECS_BY_SECTION[Section.LIQUID_GLASS_DISABLE]
    check("section holds exactly the two routes",
          [s.id for s in specs] == [TweakID.LGDisableG2, TweakID.LGDisableG1],
          str([s.id.name for s in specs]))
    g2 = SPECS_BY_ID[TweakID.LGDisableG2]
    g1 = SPECS_BY_ID[TweakID.LGDisableG1]
    check("G2 targets the managed overlay",
          g2.location is FileLocation.globalPreferences)
    check("G1 targets the HomeDomain device file",
          g1.location is FileLocation.globalPreferencesHomeDomain)
    check("both write the Beta 1 key",
          g2.key == KEY and g1.key == KEY)
    check("declared value is a real bool True",
          g2.value is True and type(g2.value) is bool)
    check("both are plain switches", g2.kind is Kind.SWITCH
          and g1.kind is Kind.SWITCH)
    check("gated to iOS 26+", g2.min_version == "26.0"
          and g1.min_version == "26.0")
    check("descriptions carry the honest Beta/unproven grade",
          "unproven" in (g2.description or "").lower()
          and "unproven" in (g1.description or "").lower())
    check("feature mapping joins HotLoad's Liquid Glass feature",
          SECTION_FEATURES[Section.LIQUID_GLASS_DISABLE] == "Liquid Glass")
    ids = {e["id"] for e in home_tweak_catalogue()}
    check("Home catalogue surfaces both routes",
          {TweakID.LGDisableG2, TweakID.LGDisableG1} <= ids)


def test_frozen_v4_untouched():
    print("\nfrozen v4 set untouched")
    spec = SPECS_BY_ID[TweakID.SolariumForceFallback]
    check("v4 spec still the managed overlay writer",
          spec.location is FileLocation.globalPreferences
          and spec.key == "SolariumForceFallback")
    tweak_loader.load_plist_tweaks()
    v4 = tweaks[TweakID.SolariumForceFallback]
    check("v4 instance is still a plain BasicPlistTweak",
          type(v4) is BasicPlistTweak)


def test_instances_and_deliverability():
    print("\ninstances + deliverability")
    g2 = tweaks[TweakID.LGDisableG2]
    g1 = tweaks[TweakID.LGDisableG1]
    check("G2 instance is the LGD tweak class",
          isinstance(g2, lg_disable.LGDG2Tweak))
    check("G1 instance is the LGD tweak class",
          isinstance(g1, lg_disable.LGDG1Tweak))
    for tid in (TweakID.LGDisableG2, TweakID.LGDisableG1):
        ok, code, _msg = tweak_deliverability(
            tid, device_version="26.6.1", device_build="23G83",
            is_iphone=True, tweak=tweaks[tid])
        check(f"{tid.name} deliverable on 26.6.1/23G83", ok and code == "OK",
              code)
        ok, code, _msg = tweak_deliverability(
            tid, device_version="25.0", device_build="",
            is_iphone=True, tweak=tweaks[tid])
        check(f"{tid.name} locked below iOS 26",
              not ok and code == "VERSION_BELOW_MIN", code)


def test_g2_staging_and_gate():
    print("\nG2 staging + gate")
    g2 = tweaks[TweakID.LGDisableG2]
    g2.set_enabled(False)
    staged = g2.apply_tweak({})
    check("disabled G2 stages nothing", staged == {} and not g2.staged)
    g2.set_enabled(True)
    staged = g2.apply_tweak({})
    check("enabled G2 stages the key as a real bool",
          staged == {FileLocation.globalPreferences: {KEY: True}}
          and type(staged[FileLocation.globalPreferences][KEY]) is bool
          and g2.staged)
    payload = plistlib.dumps(staged[FileLocation.globalPreferences])
    rec = _record(lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH, payload)
    check("gate accepts the staged G2 record",
          _gate([rec], g2_active=True, g1_active=False) == [])
    check("gate is silent when G2 did not stage",
          _gate([], g2_active=False, g1_active=False) == [])
    problems = _gate([], g2_active=True, g1_active=False)
    check("gate fails a missing G2 record", bool(problems)
          and "no restore record" in problems[0], str(problems))
    bad = _record(lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH,
                  plistlib.dumps({KEY: "true"}))
    problems = _gate([bad], g2_active=True, g1_active=False)
    check("gate rejects the string 'true' (not a bool)",
          bool(problems) and "real bool" in problems[0], str(problems))
    bad = _record(lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH,
                  plistlib.dumps({KEY: 1}))
    problems = _gate([bad], g2_active=True, g1_active=False)
    check("gate rejects the integer 1 (not a bool)",
          bool(problems) and "real bool" in problems[0], str(problems))
    bad = _record(lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH,
                  plistlib.dumps({"OtherKey": True}))
    problems = _gate([bad], g2_active=True, g1_active=False)
    check("gate rejects a record without the key",
          bool(problems) and "missing" in problems[0], str(problems))
    g2.set_enabled(False)


_BASE = {
    "AppleLanguages": ["en-US", "id-ID"],
    "AppleLocale": "en_US",
    "NSForceRightToLeftWritingDirection": False,
    "AKLastIDMSEnvironment": 0,
    "com.apple.finder.WindowState": {"Frame": "{{0, 0}, {320, 240}}"},
}


def test_g1_staging_and_gate():
    print("\nG1 staging + diff gate (payload-lab parity)")
    g1 = tweaks[TweakID.LGDisableG1]
    g1._lgd_base = None
    g1.set_enabled(True)
    staged = g1.apply_tweak({})
    check("G1 without a device base stages NOTHING (fail closed)",
          staged == {} and not g1.staged)
    problems = _gate([], g2_active=False, g1_active=True, g1_base=_BASE)
    check("gate fails when no G1 record was staged",
          bool(problems) and "no restore record" in problems[0],
          str(problems))

    g1._lgd_base = dict(_BASE)
    staged = g1.apply_tweak({})
    merged = staged[FileLocation.globalPreferencesHomeDomain]
    check("G1 stages base + key",
          set(_BASE) < set(merged) and merged[KEY] is True and g1.staged)
    check("staged key is a real bool", type(merged[KEY]) is bool)

    rec = _record(lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH,
                  plistlib.dumps(merged))
    check("gate accepts base + key",
          _gate([rec], g2_active=False, g1_active=True, g1_base=_BASE) == [])
    problems = _gate([rec], g2_active=False, g1_active=True, g1_base=None)
    check("gate refuses G1 without a captured base",
          bool(problems) and "no live device base" in problems[0],
          str(problems))

    lost = dict(merged)
    del lost["AppleLocale"]
    rec = _record(lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH,
                  plistlib.dumps(lost))
    problems = _gate([rec], g2_active=False, g1_active=True, g1_base=_BASE)
    check("diff gate fails on a LOST original key",
          any("LOST" in p for p in problems), str(problems))

    changed = dict(merged)
    changed["AppleLocale"] = "id_ID"
    rec = _record(lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH,
                  plistlib.dumps(changed))
    problems = _gate([rec], g2_active=False, g1_active=True, g1_base=_BASE)
    check("diff gate fails on a CHANGED original value",
          any("CHANGED" in p for p in problems), str(problems))

    extra = dict(merged)
    extra["InventedKey"] = True
    rec = _record(lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH,
                  plistlib.dumps(extra))
    problems = _gate([rec], g2_active=False, g1_active=True, g1_base=_BASE)
    check("diff gate fails on an unexpected NEW key",
          any("unexpected NEW key" in p for p in problems), str(problems))
    check("another tweak's staged key is the allowed difference",
          _gate([rec], g2_active=False, g1_active=True, g1_base=_BASE,
                g1_allowed_new={"InventedKey"}) == [])

    other = {"AppleICUDateTimeSymbols": {"a": "b"}}
    staged = g1.apply_tweak(
        {FileLocation.globalPreferencesHomeDomain: dict(other)})
    check("G1 merge keeps keys other tweaks staged into the same file",
          staged[FileLocation.globalPreferencesHomeDomain]
          ["AppleICUDateTimeSymbols"] == {"a": "b"})

    payload = lg_disable.build_g1_payload(_BASE, {KEY: True})
    check("build_g1_payload round-trips through its own gate",
          lg_disable.load_plist_dict(payload)[KEY] is True)
    try:
        lg_disable.build_g1_payload(_BASE, {KEY: "true"})
        raised = False
    except ValueError:
        raised = True
    check("build_g1_payload rejects a string 'true' for the bool key", raised)
    try:
        lg_disable.build_g2_payload({KEY: ["not", "flat"]})
        raised = False
    except ValueError:
        raised = True
    check("build_g2_payload rejects non-flat values", raised)
    check("payload-lab diff parity: clean diff passes",
          lg_disable.diff_gate({"a": 1}, {"a": 1, KEY: True},
                               allowed_new={KEY}) == [])
    g1.set_enabled(False)
    g1._lgd_base = None


def test_store_first_capture_wins():
    print("\nrollback store")
    udid = "TEST-UDID-0001"
    first = plistlib.dumps({"AppleLocale": "en_US"})
    second = plistlib.dumps({"AppleLocale": "en_US", KEY: True})
    check("no original before first save",
          not lg_disable.original_saved(udid)
          and lg_disable.load_original(udid) is None)
    check("first save persists",
          lg_disable.save_original_if_absent(udid, first, {"ios_version": "26.6.1"}))
    check("original loads back byte-for-byte",
          lg_disable.load_original(udid) == first)
    check("second save does NOT overwrite (first capture wins)",
          not lg_disable.save_original_if_absent(udid, second, {}))
    check("stored bytes are still the pristine first capture",
          lg_disable.load_original(udid) == first)
    meta = lg_disable.load_original_meta(udid)
    check("meta records sha1 of the first capture",
          meta is not None
          and meta["sha1"] == lg_disable.content_hash(first)
          and meta.get("saved_at"))
    check("restore map records domain/path/hash",
          lg_disable.restore_records(
              [_record(lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH, first)])
          == [{"domain": "HomeDomain",
               "relative_path": "Library/Preferences/.GlobalPreferences.plist",
               "sha1": lg_disable.content_hash(first), "size": len(first)}])


def test_domain_constants_no_drift():
    print("\ndomain/path constants vs src.restore.path_mapping")
    try:
        from src.restore.path_mapping import split_path_into_domain
        g2 = split_path_into_domain(
            FileLocation.globalPreferences.value)
        g1 = split_path_into_domain(
            FileLocation.globalPreferencesHomeDomain.value)
    except Exception:
        # pymobiledevice3 unavailable (stub env): verify the two prefix
        # mappings textually in the single source of truth instead.
        with open(os.path.join(os.path.dirname(__file__), "..",
                               "src", "restore", "path_mapping.py"),
                  encoding="utf-8") as fh:
            src_text = fh.read()
        g2 = ("ManagedPreferencesDomain", "mobile/.GlobalPreferences.plist")
        g1 = ("HomeDomain", "Library/Preferences/.GlobalPreferences.plist")
        check("path_mapping source keeps the managed prefix",
              '"/var/Managed Preferences/", "ManagedPreferencesDomain"' in src_text)
        check("path_mapping source keeps the /var/mobile prefix",
              '"/var/mobile/", "HomeDomain"' in src_text)
    check("G2 constants match path_mapping",
          g2 == (lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH), str(g2))
    check("G1 constants match path_mapping",
          g1 == (lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH), str(g1))


def test_gui_smoke():
    if not _REAL_QT:
        print("\nGUI smoke skipped (no real PySide6)")
        return
    print("\nGUI smoke (offscreen)")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    class _FakeDM:
        class data_singleton:  # noqa: N801 — mirrors the real attribute name
            current_device = None

        def get_current_device_version(self):
            return "26.6.1"

        def get_current_device_build(self):
            return "23G83"

        def get_current_device_model(self):
            return "iPhone17,1"

        def get_current_device_udid(self):
            return None

        def get_current_device_name(self):
            return ""

    class _FakeWindow:
        device_manager = _FakeDM()
        apply_in_progress = False

        def __init__(self):
            self.shown_pages = []

        def show_ios_page(self, index):
            self.shown_pages.append(index)

        def update_label(self, _txt):
            pass

        def alert_message(self, _msg):
            pass

    from src.gui.ios.liquid_glass_disable import IOSLiquidGlassDisablePage
    window = _FakeWindow()
    page = IOSLiquidGlassDisablePage(window)
    check("page constructs offscreen", page is not None)
    switches = page.content._switches
    check("page renders both route switches",
          TweakID.LGDisableG2 in switches and TweakID.LGDisableG1 in switches)
    page.refresh()  # no device: status line, no crash
    check("refresh with no device is safe", True)
    sw = switches[TweakID.LGDisableG2]
    sw.setChecked(True)
    check("toggling the G2 switch enables the registry tweak",
          tweaks[TweakID.LGDisableG2].enabled)
    sw.setChecked(False)
    check("toggling it back disables the tweak",
          not tweaks[TweakID.LGDisableG2].enabled)
    page._apply_btn.click()
    check("Open Apply navigates to the Apply page (index 6)",
          window.shown_pages == [6], str(window.shown_pages))
    page.focus_route("g2")
    check("Home tile focus marks the G2 route without enabling it",
          page._focused_route == "g2"
          and not tweaks[TweakID.LGDisableG2].enabled)
    page.focus_route("g1")
    check("Home tile focus marks the G1 route without enabling it",
          page._focused_route == "g1"
          and not tweaks[TweakID.LGDisableG1].enabled)
    page.focus_route("bogus")
    check("unknown focus route clears the marker",
          page._focused_route is None)
    tweaks[TweakID.LGDisableG2].set_enabled(False)
    tweaks[TweakID.LGDisableG1].set_enabled(False)


def main():
    tweak_loader.load_plist_tweaks()
    test_registry_shape()
    test_frozen_v4_untouched()
    test_instances_and_deliverability()
    test_g2_staging_and_gate()
    test_g1_staging_and_gate()
    test_store_first_capture_wins()
    test_domain_constants_no_drift()
    test_gui_smoke()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
