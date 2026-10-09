"""Wave 12 — Liquid Glass Tweaks (Nugget), verbatim from Nugget v7.4.1.

Proves the second Liquid Glass set shipped in UI-2/UI-3 is byte-faithful
to leminlimez/Nugget v7.4.1 (tag v7.4.1, commit
26e0c50ec114ca3a4ff6ab2fb4ae309abfd39fa1):

* 8 plist tweaks from upstream ``src/tweaks/tweak_loader.py``
  ``load_liquidglass()`` (lines 381-419): same file location
  (/var/Managed Preferences/mobile/.GlobalPreferences.plist), same
  keys, same values/types, same Enabled/Disabled/Default staging.
* 8 Solarium FeatureFlag tweaks from upstream ``load_featureflags()``
  (lines 203-213): same categories, flag names and inverted semantics,
  staged as {'Enabled': False} records exactly as upstream.
* The set lives OUTSIDE the registry (the WorkSlop v4 set is guarded
  separately by test_wave11_lg_v4_verbatim) under its own TweakIDs.
* GUI glue: the subsection exists at the bottom of the Liquid Glass
  section, is hidden in the WorkSlop UI and visible in both Nugget
  interfaces; its three-state controls drive the tweak objects with
  upstream's set_value/set_enabled operations.

Run: python tools/test_wave12_nugget_lg.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.qt.resources_rc  # noqa: F401,E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

app = QApplication([])

# No usbmuxd in the test environment: device refresh can end in a
# modal error dialog. Dismiss modals instead of blocking forever
# (same strategy as tools/test_wave10_ui_rebuild.py).
from PySide6.QtCore import QTimer  # noqa: E402

_modal_killer = QTimer()
_modal_killer.timeout.connect(
    lambda: (QApplication.activeModalWidget().close()
             if QApplication.activeModalWidget() is not None else None))
_modal_killer.start(50)

checks = 0


def check(name, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        print(f"FAIL: {name} {detail}", flush=True)
        sys.exit(1)
    print(f"  ok: {name}", flush=True)


GP_PATH = "/var/Managed Preferences/mobile/.GlobalPreferences.plist"

print("payload: plist tweaks (upstream load_liquidglass, lines 385-417)")
from src.tweaks.basic_plist_locations import FileLocation  # noqa: E402
from src.tweaks.nugget_lg import load_nugget_lg_tweaks  # noqa: E402
from src.tweaks.tweaks import tweaks  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402

load_nugget_lg_tweaks()

PLIST_EXPECTED = [
    (TweakID.NuggetForceSolariumFallback, "SolariumForceFallback", False),
    (TweakID.NuggetDisableSolarium, "com.apple.SwiftUI.DisableSolarium", False),
    (TweakID.NuggetIgnoreSolariumLinkedOnCheck,
     "com.apple.SwiftUI.IgnoreSolariumLinkedOnCheck", False),
    (TweakID.NuggetNoLiquidClock, "SBDisallowGlassTime", False),
    (TweakID.NuggetNoLiquidDock, "SBDisableGlassDock", False),
    (TweakID.NuggetDisableSpecularMotion,
     "SBDisableSpecularEverywhereUsingLSSAssertion", False),
    (TweakID.NuggetDisableOuterRefraction, "SolariumDisableOuterRefraction", False),
    (TweakID.NuggetDisableSolariumHDR, "SolariumAllowHDR", True),
]
for tid, key, invert in PLIST_EXPECTED:
    tw = tweaks[tid]
    check(f"{tid.name} location is upstream .GlobalPreferences.plist",
          tw.file_location == FileLocation.globalPreferences
          and tw.file_location.value == GP_PATH)
    check(f"{tid.name} key", tw.key == key, tw.key)
    check(f"{tid.name} starts disabled (upstream Default)",
          tw.enabled is False)
    check(f"{tid.name} initial value",
          tw.value is (False if invert else True), repr(tw.value))
    # Upstream "Enabled" radio: set_value(not invert_values)
    tw.set_value(not invert)
    staged = tw.apply_tweak({})
    check(f"{tid.name} Enabled stages key={not invert}",
          staged == {FileLocation.globalPreferences: {key: not invert}},
          repr(staged))
    # Upstream "Disabled" radio: set_value(invert_values)
    tw.set_value(invert)
    staged = tw.apply_tweak({})
    check(f"{tid.name} Disabled stages key={invert}",
          staged == {FileLocation.globalPreferences: {key: invert}},
          repr(staged))
    # Upstream "Default" radio: set_enabled(False) stages nothing
    tw.set_enabled(False)
    check(f"{tid.name} Default stages nothing", tw.apply_tweak({}) == {})
    tw.set_value(True)  # restore neutral state for later GUI checks
    tw.set_enabled(False)

print("payload: feature flags (upstream load_featureflags, lines 203-213)")
FF_EXPECTED = [
    (TweakID.NuggetSolariumFFSwiftUI, "SwiftUI", ["Solarium"]),
    (TweakID.NuggetSolariumFFSpringBoard, "SpringBoard", ["SolariumElasticHUD"]),
    (TweakID.NuggetSolariumFFIconServices, "IconServices",
     ["EnhancedGlass", "SolariumCornerRadius"]),
    (TweakID.NuggetSolariumFFDocumentCamera, "DocumentCamera",
     ["CaptureLiquidGlass"]),
    (TweakID.NuggetSolariumFFPhotos, "Photos", ["SolariumGridMagicPocket"]),
    (TweakID.NuggetSolariumFFAppleMediaServices, "AppleMediaServices",
     ["Solarium"]),
    (TweakID.NuggetSolariumFFSharing, "Sharing", ["ShareSheetSolarium"]),
    (TweakID.NuggetSolariumFFMail, "Mail", ["SolariumSearch"]),
]
for tid, category, flags in FF_EXPECTED:
    tw = tweaks[tid]
    check(f"{tid.name} category/flags/inverted",
          tw.flag_category == category and tw.flag_names == flags
          and tw.inverted is True and tw.is_list is True)
    tw.set_enabled(True)
    staged = tw.apply_tweak({})
    check(f"{tid.name} enabled stages inverted Enabled records",
          staged == {category: {f: {"Enabled": False} for f in flags}},
          repr(staged))
    tw.set_enabled(False)
    check(f"{tid.name} disabled stages nothing", tw.apply_tweak({}) == {})

print("registry isolation: the Nugget set never enters the WorkSlop set")
from src.tweaks.registry import SPECS_BY_ID  # noqa: E402
nugget_ids = [tid for tid, _, _ in PLIST_EXPECTED] + [t for t, _, _ in FF_EXPECTED]
check("all 16 Nugget tweaks loaded", len(nugget_ids) == 16
      and all(t in tweaks for t in nugget_ids))
check("no Nugget ID is a registry (WorkSlop set) spec",
      all(t not in SPECS_BY_ID for t in nugget_ids))
first = tweaks[TweakID.NuggetDisableSolarium]
load_nugget_lg_tweaks()
check("loader is idempotent (live objects kept)",
      tweaks[TweakID.NuggetDisableSolarium] is first)

print("GUI glue: subsection reachability and controls")
from src.controllers.settings import Settings  # noqa: E402
from src.controllers.translator import Translator  # noqa: E402
from src.devicemanagement.device_manager import DeviceManager  # noqa: E402
from src.gui.ios.theme_manager import ThemeManager  # noqa: E402
from src.gui.main_window import MainWindow  # noqa: E402

def pump(times=5):
    """Flush queued theme/visibility work before asserting on it.

    Theme switches travel through queued signals whose delivery depth
    differs between Qt builds (6.11 needed more pumps than 6.12 in CI,
    2026-10-09); assert only on the settled state.
    """
    from PySide6.QtCore import QCoreApplication, QEventLoop
    for _ in range(times):
        app.processEvents(QEventLoop.AllEvents, 50)
        QCoreApplication.sendPostedEvents()


win = MainWindow(device_manager=DeviceManager(),
                 translator=Translator(app, Settings()))
win.resize(1280, 800)
win.show()
pump()

content = win.ios_liquidglass.content
box = content._nugget_lg_box
check("subsection exists at the bottom of the Liquid Glass section",
      box is not None)
# Do not depend on whatever theme a previous run left in QSettings:
# drive the UI to the WorkSlop theme explicitly, then settle.
win.apply_theme(ThemeManager.IOS)
pump()
check("hidden in WorkSlop UI",
      win.theme_manager.current_theme == ThemeManager.IOS
      and not box.isVisible())


def _tri_buttons(label_text):
    """Return {name: button} of the three-state row for a Nugget label."""
    for lbl in box.findChildren(QLabel):
        if lbl.text() == label_text:
            card = lbl.parent()
            out = {}
            for btn in card.findChildren(QPushButton):
                out[btn.text()] = btn
            return out
    return {}


win.apply_theme(ThemeManager.CLASSIC)
win.show_ios_page(9)
pump()
check("visible in Nugget UI", box.isVisible())
btns = _tri_buttons("Disable Liquid Glass")
check("three-state row found (Default/Enabled/Disabled)",
      set(btns) == {"Default", "Enabled", "Disabled"}, str(set(btns)))
tw = tweaks[TweakID.NuggetDisableSolarium]
btns["Enabled"].click()
app.processEvents()
check("Enabled drives upstream set_value(True)",
      tw.enabled and tw.value is True)
check("Enabled stages the upstream payload",
      tw.apply_tweak({}) == {FileLocation.globalPreferences:
                              {"com.apple.SwiftUI.DisableSolarium": True}})
btns["Disabled"].click()
app.processEvents()
check("Disabled drives upstream set_value(False)",
      tw.enabled and tw.value is False)
btns["Default"].click()
app.processEvents()
check("Default disables the tweak (stages nothing)",
      not tw.enabled and tw.apply_tweak({}) == {})

win.apply_theme(ThemeManager.FULL_NUGGET)
app.processEvents()
# Full Nugget (third interface) does not host the iOS-style page at
# all: it lands on the vendored original Nugget v7.4.1 Liquid Glass
# page whose tri-state radios drive this same Nugget set.
check("Full Nugget shows the original Nugget Liquid Glass page",
      win.content_stack.currentWidget() is win.nugget_stack
      and win.nugget_stack.currentWidget()
      is win._nugget_ui.liquidGlassPage)
check("iOS-hosted Liquid Glass page is not the Full Nugget surface",
      not box.isVisible())
from PySide6.QtWidgets import QRadioButton  # noqa: E402
_radios = win._nugget_ui.forceSolariumFallbackBtns
_enabled = None
for _i in range(_radios.count()):
    _w = _radios.itemAt(_i).widget()
    if isinstance(_w, QRadioButton) and _w.text() == "Enabled":
        _enabled = _w
check("original Nugget radio row exists (Force Solarium Fallback)",
      _enabled is not None)
_ff = tweaks[TweakID.NuggetForceSolariumFallback]
_enabled.click()
app.processEvents()
check("Full Nugget radio drives the same Nugget tweak object",
      _ff.enabled and _ff.value is True)
win.apply_theme(ThemeManager.IOS)
app.processEvents()
check("hidden again back in WorkSlop UI", not box.isVisible())

win.close()
print(f"\nALL {checks} CHECKS PASSED")
