#!/usr/bin/env python3
"""Offscreen GUI checks for the Wave 10 Home / Hide Search package.

Skips cleanly when PySide6 is unavailable. When Qt is present it verifies:

* the Liquid Glass section page renders the canonical Hide Search row and
  the SpringBoard section page does not;
* exactly one rendered switch exists for the Hide Search payload;
* Home's registry-derived catalogue lists Hide Search under Liquid Glass
  (not SpringBoard) and lists a synthetic new registry entry automatically
  after a catalogue refresh, with no Home code edit.

Run: QT_QPA_PLATFORM=offscreen python tools/test_wave10_home_hide_search_gui.py
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


try:
    from PySide6.QtWidgets import QApplication
except Exception as e:
    print(f"skipped: {type(e).__name__}: {e}")
    raise SystemExit(0)

app = QApplication([])

try:
    import src.qt.resources_rc  # noqa: F401  (registers :/icon resources)
except Exception:
    pass

from src.gui.ios.home import IOSHomePage
from src.gui.ios.tweaks import IOSSectionPage
from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.registry import SPECS_BY_SECTION, Section, TweakSpec
from src.tweaks.tweaks import TweakID


class _Settings:
    def value(self, *_args, **_kwargs):
        return ""

    def setValue(self, *_args, **_kwargs):
        pass

    def sync(self):
        pass


class _DeviceManager:
    devices = []

    def get_current_device_udid(self):
        return ""

    def get_current_device_version(self):
        return ""

    def get_current_device_build(self):
        return ""

    def get_current_device_model(self):
        return ""

    data_singleton = SimpleNamespace(current_device=None)


class _Window:
    def __init__(self):
        self.device_manager = _DeviceManager()
        self.settings = _Settings()

    def autosave_enabled(self):
        return True

    def open_presets_section(self):
        pass


def catalogue_line(page, section_value):
    for line in page.tweak_catalogue_lbl.text().splitlines():
        if line.startswith(section_value + ":"):
            return line
    return ""


print("\nsection pages render Hide Search only under Liquid Glass")
window = _Window()
liquid_page = IOSSectionPage(window, Section.LIQUID_GLASS)
springboard_page = IOSSectionPage(window, Section.SPRINGBOARD)
app.processEvents()
check("Liquid Glass section has the canonical switch",
      TweakID.SBHideSearchAffordance in liquid_page.content._switches)
check("SpringBoard section has no Hide Search switch",
      TweakID.SBHideSearchAffordance not in springboard_page.content._switches)
check("duplicate name renders nowhere as a switch",
      TweakID.HideSearchAffordance not in liquid_page.content._switches
      and TweakID.HideSearchAffordance not in springboard_page.content._switches)

print("\nHome catalogue is registry-derived")
home = IOSHomePage(window)
app.processEvents()
entries = {entry["id_name"]: entry for entry in home.tweak_catalogue_entries}
check("Home lists canonical Hide Search", "SBHideSearchAffordance" in entries)
check("Home places Hide Search in Liquid Glass",
      entries["SBHideSearchAffordance"]["section"] is Section.LIQUID_GLASS)
check("Home Liquid Glass line names Hide Search",
      "Hide Search Button on Home Screen" in catalogue_line(home, "Liquid Glass"))
check("Home SpringBoard line does not name Hide Search",
      "Hide Search Button on Home Screen" not in catalogue_line(home, "SpringBoard"))
check("Home keeps FlatIconsEverywhere listed",
      "FlatIconsEverywhere" in entries)

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
    home.refresh_tweak_catalogue()
    app.processEvents()
    refreshed = {entry["id_name"]: entry
                 for entry in home.tweak_catalogue_entries}
    check("Home lists synthetic new registry entry after refresh",
          refreshed.get("StatusBar", {}).get("title")
          == "Synthetic Home Probe")
    check("Home label shows the synthetic entry",
          "Synthetic Home Probe" in home.tweak_catalogue_lbl.text())
finally:
    SPECS_BY_SECTION[Section.LIQUID_GLASS].remove(synthetic)
    home.refresh_tweak_catalogue()

print(f"\nALL {PASS} CHECKS PASSED")
