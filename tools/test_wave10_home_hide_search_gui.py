#!/usr/bin/env python3
"""Offscreen GUI checks for the Wave 10 Home / Hide Search package.

Skips cleanly when PySide6 is unavailable. When Qt is present it verifies:

* the SpringBoard section page renders the canonical Hide Search row and
  the Liquid Glass section page does not (v4 placement, restored verbatim
  2026-10-03 — supersedes the Wave 10 move into the Liquid Glass menu);
* exactly one rendered switch exists for the Hide Search payload;
* the registry places Hide Search under SpringBoard, the restored v4
  Home shows its fixed nine feature tiles (no rebuild-era catalogue),
  and a synthetic new registry entry renders in a rebuilt section page
  with no page code edit.

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


print("\nsection pages render Hide Search only under SpringBoard (v4)")
window = _Window()
liquid_page = IOSSectionPage(window, Section.LIQUID_GLASS)
springboard_page = IOSSectionPage(window, Section.SPRINGBOARD)
app.processEvents()
check("SpringBoard section has the canonical switch (v4 placement)",
      TweakID.SBHideSearchAffordance in springboard_page.content._switches)
check("Liquid Glass section has no Hide Search switch",
      TweakID.SBHideSearchAffordance not in liquid_page.content._switches)
check("duplicate name renders nowhere as a switch",
      TweakID.HideSearchAffordance not in liquid_page.content._switches
      and TweakID.HideSearchAffordance not in springboard_page.content._switches)

print("\nregistry places Hide Search in SpringBoard; v4 Home tiles fixed")
from PySide6.QtWidgets import QLabel  # noqa: E402
from src.tweaks.registry import SPECS_BY_ID  # noqa: E402
check("registry section of Hide Search is SpringBoard (v4)",
      SPECS_BY_ID[TweakID.SBHideSearchAffordance].section
      is Section.SPRINGBOARD)
home = IOSHomePage(window)
app.processEvents()
tile_titles = [title.text() for _icon, _res, title, _sub in home._tiles]
check("v4 Home has the ten feature tiles (G1/G2 removed in v14.0)",
      tile_titles == ["Tweaks", "Liquid Glass", "App Data", "MobileGestalt",
                      "PosterBoard", "Daemons", "Status Bar", "Custom Icon",
                      "Passcode Theme", "Liquid Glass iOS 26.6.1 RC S8"],
      str(tile_titles))
check("Home has no Hide Search tile (it lives in the SpringBoard page)",
      not any("Hide Search" in t for t in tile_titles))

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
    rebuilt = IOSSectionPage(window, Section.LIQUID_GLASS)
    app.processEvents()
    labels = [w.text() for w in rebuilt.findChildren(QLabel)]
    check("synthetic new registry entry renders with no page code edit",
          "Synthetic Home Probe" in labels, str(labels[:3]))
    rebuilt.close()
finally:
    SPECS_BY_SECTION[Section.LIQUID_GLASS].remove(synthetic)

print(f"\nALL {PASS} CHECKS PASSED")
