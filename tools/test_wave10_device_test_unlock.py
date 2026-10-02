#!/usr/bin/env python3
"""Wave 10 device-test unlock + update-runner lifecycle + UI accuracy.

Verifies, for the three audit-verified Liquid Glass candidates
(SolariumForceFallback, DisallowGlassTime, DisableGlassDock):

* payload substance: spec key/location/value exactly as audited, the
  BasicPlistTweak apply path stages all three into the single managed
  .GlobalPreferences.plist, one writer per (location, key), and the reset
  nulls that same GP file (static source trace);
* gating: DEVICE_TEST_OK on the iOS 26.6.1 target (23G82/23G83), other
  research-only rows stay AUDIT_RESEARCH_ONLY-locked, killed K1 stays
  REMOVED_TWEAK, MobileGestalt stays fail-closed;
* GUI (offscreen): the three rows are enabled with an UNPROVEN badge, the
  one-time confirmation dialog gates enabling, ship-candidates are
  enabled, research-only rows are disabled with a reason, and Home's
  MobileGestalt status comes from the shared decision (Locked on
  23G82/23G83, Supported on 23C5027f) with unknown values hidden;
* the shared UpdateCheckRunner survives repeat clicks (the deleted-QThread
  regression) and delivers results on the GUI thread.

Run: QT_QPA_PLATFORM=offscreen ~/wsui-venv/bin/python \
    tools/test_wave10_device_test_unlock.py
"""
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


TARGET = {"device_version": "26.6.1", "device_build": "23G83"}

print("\ncffi stub (pymobiledevice3 import chain)")
try:
    import cffi as _real_cffi  # noqa: F401
except Exception:
    import types as _t

    _stub = _t.ModuleType("cffi")

    class _FFI:
        def cdef(self, *a, **k):
            pass

        def dlopen(self, *a, **k):
            raise OSError("stub")

        def set_source(self, *a, **k):
            pass

        def buffer(self, *a, **k):
            return b""

    _stub.FFI = _FFI
    sys.modules["cffi"] = _stub
    # The compiled cffi helper is absent without _cffi_backend; stub the
    # boundary module (same approach as tools/test_apply_journal.py).
    import types as _t2
    _cmod = _t2.ModuleType("src.tweaks.status_bar.status_bar_c.status_setter")

    class _Lib:
        def status_setter(self, *_a):
            return b""

    _cmod.ffi = _FFI()
    _cmod.lib = _Lib()
    sys.modules.setdefault(
        "src.tweaks.status_bar.status_bar_c.status_setter", _cmod)

from src.tweaks import tweak_loader  # noqa: E402
from src.tweaks.basic_plist_locations import FileLocation  # noqa: E402
from src.tweaks.capabilities import (  # noqa: E402
    is_audit_research_only, is_device_test_tweak, is_removed_tweak,
    tweak_deliverability,
)
from src.tweaks.registry import SPECS, SPECS_BY_ID  # noqa: E402
from src.tweaks.tweaks import TweakID, tweaks  # noqa: E402

DEVICE_TEST_IDS = [
    TweakID.SolariumForceFallback, TweakID.DisallowGlassTime,
    TweakID.DisableGlassDock,
]
EXPECTED_KEYS = {
    TweakID.SolariumForceFallback: "SolariumForceFallback",
    TweakID.DisallowGlassTime: "SBDisallowGlassTime",
    TweakID.DisableGlassDock: "SBDisableGlassDock",
}

print("\npayload substance (spec == audit)")
for tid, key in EXPECTED_KEYS.items():
    spec = SPECS_BY_ID[tid]
    check(f"{tid.name} key is audit-exact", spec.key == key, spec.key)
    check(f"{tid.name} writes managed GP",
          spec.location == FileLocation.globalPreferences, str(spec.location))
    check(f"{tid.name} value is bool True",
          spec.value is True and type(spec.value) is bool)
    check(f"{tid.name} is a device-test tweak", is_device_test_tweak(tid))
    check(f"{tid.name} not research-contained", not is_audit_research_only(tid))

tweak_loader.load_plist_tweaks()
print("\napply path stages all three into the one managed GP plist")
staged = {}
for tid in DEVICE_TEST_IDS:
    tw = tweaks[tid]
    tw.set_enabled(True)
    staged = tw.apply_tweak(staged)
    tw.set_enabled(False)
gp = staged.get(FileLocation.globalPreferences, {})
for tid, key in EXPECTED_KEYS.items():
    check(f"{key}=True staged in GP dict", gp.get(key) is True, str(gp))
check("exactly the three keys staged", set(gp) == set(EXPECTED_KEYS.values()),
      str(sorted(gp)))

writers = {}
for spec in SPECS:
    if spec.disabled or not spec.key or spec.factory is not None:
        continue
    writers.setdefault((spec.location, spec.key), []).append(spec.id.name)
dupes = {k: v for k, v in writers.items() if len(v) > 1}
check("one writer per (location, key)", not dupes, str(dupes))

print("\nreset nulls the same managed GP file (source trace)")
_root = os.path.join(os.path.dirname(__file__), "..")
with open(os.path.join(_root, "src/devicemanagement/device_manager.py"),
          encoding="utf-8") as fh:
    _dm = fh.read()
check("Internal Options reset nulls GP",
      "files_to_null.append(FileLocation.globalPreferences.value)" in _dm)
check("reset payload is a valid empty plist, never zero-byte",
      "reset_contents = plistlib.dumps({})" in _dm)

print("\ngating on the audited target")
for tid in DEVICE_TEST_IDS:
    ok, code, msg = tweak_deliverability(tid, **TARGET)
    check(f"{tid.name} delivers as DEVICE_TEST_OK on 23G83",
          ok and code == "DEVICE_TEST_OK", code)
    check(f"{tid.name} message warns UNPROVEN", "UNPROVEN" in msg)
    ok, code, _ = tweak_deliverability(
        tid, device_version="26.6.1", device_build="23G82")
    check(f"{tid.name} delivers as DEVICE_TEST_OK on 23G82",
          ok and code == "DEVICE_TEST_OK", code)
ok, code, msg = tweak_deliverability(TweakID.AnimDragCoeff, **TARGET)
check("research-only registry tweak is device-testable (2026-10-03 policy)",
      ok and code == "DEVICE_TEST_OK" and "UNPROVEN" in msg, code)
ok, code, _ = tweak_deliverability(TweakID.SBBuildNumber, **TARGET)
check("Internal research-only registry tweak is device-testable",
      ok and code == "DEVICE_TEST_OK", code)
ok, code, _ = tweak_deliverability(TweakID.StatusBar, **TARGET)
check("non-registry research family stays locked",
      not ok and code == "AUDIT_RESEARCH_ONLY", code)
ok, code, _ = tweak_deliverability(TweakID.GlassLegibility2, **TARGET)
check("killed K1 stays REMOVED_TWEAK", not ok and code == "REMOVED_TWEAK", code)
check("K1 is a removed tombstone", is_removed_tweak(TweakID.GlassLegibility2))
ok, code, _ = tweak_deliverability(TweakID.ModelName, **TARGET)
check("MobileGestalt fail-closed on 23G83", not ok, code)
ok, code, _ = tweak_deliverability(TweakID.RdarFix, **TARGET)
check("RdarFix (MG flow) stays fail-closed on 23G83", not ok, code)
from src.tweaks.capabilities import is_device_test_candidate  # noqa: E402
check("K1 is not a device-test candidate",
      not is_device_test_candidate(TweakID.GlassLegibility2))
check("removed tombstone is not a device-test candidate",
      not is_device_test_candidate(TweakID.DisableSolariumSwiftUI))
check("MG tweak is not device-testable on target classification alone",
      not is_device_test_candidate(TweakID.ModelName))
check("research-only registry tweak is a device-test candidate",
      is_device_test_candidate(TweakID.AnimDragCoeff))
ok, code, _ = tweak_deliverability(TweakID.LockScreenFootnote, **TARGET)
check("ship-candidate delivers OK", ok and code == "OK", code)

print("\napp version stays 10.0")
from src.version import App_Version  # noqa: E402
check("App_Version is 10.0", App_Version == "10.0", App_Version)

# ---------------------------------------------------------------- GUI ----
try:
    from PySide6.QtWidgets import QApplication
except Exception as e:
    print(f"\nGUI part skipped: {type(e).__name__}: {e}")
    print(f"\nALL {PASS} CHECKS PASSED (non-GUI)")
    raise SystemExit(0)

app = QApplication([])

try:
    import src.qt.resources_rc  # noqa: F401
except Exception:
    pass

from src.gui.ios.home import IOSHomePage  # noqa: E402
from src.gui.ios.tweaks import IOSSectionPage  # noqa: E402
from src.tweaks.registry import Section  # noqa: E402


class _Settings:
    def value(self, *_args, **_kwargs):
        return ""

    def setValue(self, *_args, **_kwargs):
        pass

    def sync(self):
        pass


class _Device:
    name = "iPhone 14"
    connected_via_usb = True
    version = "26.6.1"
    build = "23G83"


class _DeviceManager:
    def __init__(self, build="23G83", version="26.6.1"):
        self._build = build
        self._version = version
        self.devices = [_Device()]

    def get_current_device_udid(self):
        return "wave10-offscreen-udid-0001"

    def get_current_device_version(self):
        return self._version

    def get_current_device_build(self):
        return self._build

    def get_current_device_model(self):
        return "iPhone14,5"

    def get_current_device_name(self):
        return "iPhone 14"

    def get_current_device_is_supported_by_fork(self):
        return True

    def get_current_device_partially_supported(self):
        return False

    data_singleton = SimpleNamespace(current_device=None)


class _Window:
    def __init__(self, build="23G83", version="26.6.1"):
        self.device_manager = _DeviceManager(build, version)
        self.settings = _Settings()

    def autosave_enabled(self):
        return True

    def open_presets_section(self):
        pass

    def change_selected_device(self, index):
        pass

    def refresh_devices(self):
        pass


print("\nGUI: Tweaks pages on stub 23G83 (single decision source)")
window = _Window()
lg_page = IOSSectionPage(window, Section.LIQUID_GLASS)
sb_page = IOSSectionPage(window, Section.SPRINGBOARD)
in_page = IOSSectionPage(window, Section.INTERNAL)
app.processEvents()

for tid in DEVICE_TEST_IDS:
    sw = lg_page.content._switches[tid]
    check(f"{tid.name} switch enabled on 23G83", sw.isEnabled())
from PySide6.QtWidgets import QLabel  # noqa: E402
badge_texts = [w.text() for w in lg_page.findChildren(QLabel)]
check("UNPROVEN device-test badge rendered",
      any("UNPROVEN" in tx and "device test" in tx for tx in badge_texts),
      str([tx for tx in badge_texts if "UNPROVEN" in tx][:2]))

ship = TweakID.SBDontLockAfterCrash
check("ship-candidate switch enabled",
      sb_page.content._switches[ship].isEnabled())
check("ship-candidate FlatIconsEverywhere enabled",
      lg_page.content._switches[TweakID.FlatIconsEverywhere].isEnabled())
research = TweakID.SBBuildNumber
rsw = in_page.content._switches[research]
check("research-only registry switch ENABLED as device test (2026-10-03 policy)",
      rsw.isEnabled())
in_badge_texts = [w.text() for w in in_page.findChildren(QLabel)]
check("research-only row carries the UNPROVEN badge",
      any("UNPROVEN" in tx for tx in in_badge_texts))

print("\nGUI: device-test confirmation dialog gates enabling")
import src.gui.ios.tweaks as tweaks_gui  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

orig_question = QMessageBox.question
try:
    QMessageBox.question = staticmethod(
        lambda *a, **k: QMessageBox.StandardButton.No)
    tweaks_gui.tweaks[DEVICE_TEST_IDS[0]].set_enabled(False)
    lg_page.content._on_registry_switch(DEVICE_TEST_IDS[0], True)
    check("declining confirmation keeps tweak off",
          not tweaks_gui.tweaks[DEVICE_TEST_IDS[0]].enabled)
    QMessageBox.question = staticmethod(
        lambda *a, **k: QMessageBox.StandardButton.Yes)
    lg_page.content._on_registry_switch(DEVICE_TEST_IDS[0], True)
    check("accepting confirmation enables tweak",
          tweaks_gui.tweaks[DEVICE_TEST_IDS[0]].enabled)
    tweaks_gui.tweaks[DEVICE_TEST_IDS[0]].set_enabled(False)
finally:
    QMessageBox.question = orig_question

print("\nGUI: Home MobileGestalt status follows the shared decision")
for build, expected in (("23G82", "Locked"), ("23G83", "Locked"),
                        ("23C5027f", "Supported")):
    home = IOSHomePage(_Window(build=build))
    app.processEvents()
    got = home._info_values["gestalt"].text()
    check(f"Home gestalt on {build} is {expected}", got == expected, got)
check("serial row hidden without data", home._info_rows["serial"].isHidden())
check("capacity chip hidden without data", home._capacity_chip.isHidden())
check("Home shows brand logo, no phone", hasattr(home, "_brand_logo")
      and not hasattr(home, "_phone"))
check("tweak list card present on Home",
      home._catalogue_card.objectName() == "tweakListCard")

print("\nGUI: Status Bar page contained honestly on 23G83")
from src.gui.ios.statusbar import IOSStatusBarPage  # noqa: E402
sbstatus = IOSStatusBarPage(_Window())
app.processEvents()
sbstatus._apply_ios27_gating()
check("full-signal switch disabled on target",
      not sbstatus.full_signal_switch.isEnabled())
check("containment note carries the shared gate message",
      "Research-only" in sbstatus._signal_note.text(),
      sbstatus._signal_note.text()[:60])
check("classic rows disabled with reason shown",
      "Research-only" in sbstatus._gate_note.text())

print("\nupdate runner: repeat clicks cannot crash (deleted-QThread fix)")
import src.controllers.web_request_handler as wrh  # noqa: E402
from src.gui.update_check import UpdateCheckRunner  # noqa: E402


class _FakeResult:
    outcome = "up_to_date"


def _fake_check(*_a, **_k):
    time.sleep(0.05)
    return _FakeResult()


orig_check = wrh.check_for_update
wrh.check_for_update = _fake_check
try:
    runner = UpdateCheckRunner()
    got = []
    runner.result_ready.connect(got.append)
    check("first start accepted", runner.start())
    check("concurrent start ignored", not runner.start())
    deadline = time.time() + 10
    while not got and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    check("first result delivered", len(got) == 1)
    deadline = time.time() + 10
    while runner.busy and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    check("runner idle after finish", not runner.busy)
    # The regression: a second click after the first thread finished used
    # to dereference a deleted C++ QThread. It must start cleanly again.
    check("second start after finish accepted", runner.start())
    deadline = time.time() + 10
    while len(got) < 2 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    check("second result delivered", len(got) == 2)
finally:
    wrh.check_for_update = orig_check

print(f"\nALL {PASS} CHECKS PASSED")
