#!/usr/bin/env python3
"""Gating matrix: stub devices 26.6.1 / 26.1 / 27.x / no-device.

User report 2026-10-03: tweaks stayed reachable on unsupported iOS
(example: Risky "Set a Custom Device Resolution"). Every family must
consult the ONE shared deliverability decision — GUI switch state and
backend verdict must agree per device. Also covers the new registry
tweak "Disable Thermal" (audit: launchd disabled.plist, daemon
com.apple.thermalmonitord) end to end: registry, Home catalogue,
deliverability, and merged disabled.plist staging with the Daemons tweak.

Run: QT_QPA_PLATFORM=offscreen ~/wsui-venv/bin/python \
    tools/test_wave10_gating_matrix.py
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


from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

import src.qt.resources_rc  # noqa: E402,F401
from src.gui.ios.tweaks import IOSSectionPage  # noqa: E402
from src.tweaks.capabilities import tweak_deliverability  # noqa: E402
from src.tweaks.registry import SPECS_BY_ID, Section, home_tweak_catalogue  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402


class _Settings:
    def value(self, *_a, **_k):
        return ""

    def setValue(self, *_a, **_k):
        pass

    def sync(self):
        pass


class _Device:
    def __init__(self, version, build):
        self.version = version
        self.build = build
        self.model = "iPhone14,5"
        self.hardware = "D17AP"
        self.cpu = "t8110"
        self.name = "Stub"
        self.connected_via_usb = True
        self.udid = "STUB"


class _DeviceManager:
    def __init__(self, version="", build=""):
        self.devices = [_Device(version, build)] if version else []
        self.current_device_index = 0
        self.data_singleton = SimpleNamespace(
            current_device=self.devices[0] if self.devices else None)

    def get_current_device_udid(self):
        return "STUB" if self.devices else None


class _Window:
    def __init__(self, version="", build=""):
        self.device_manager = _DeviceManager(version, build)
        self.settings = _Settings()

    def autosave_enabled(self):
        return True

    def open_presets_section(self):
        pass

    def change_selected_device(self, index):
        pass

    def refresh_devices(self):
        pass


DEVICES = [
    ("26.6.1 (23G83)", "26.6.1", "23G83"),
    ("26.1", "26.1", ""),
    ("27.x", "27.0", "24A435"),
    ("no-device", "", ""),
]

print("\nTweaks page switches follow the shared decision")
for label, version, build in DEVICES:
    window = _Window(version, build)
    sb = IOSSectionPage(window, Section.SPRINGBOARD)
    internal = IOSSectionPage(window, Section.INTERNAL)
    app.processEvents()
    targets = [
        (sb, TweakID.SBDontLockAfterCrash, "ship-candidate"),
        (internal, TweakID.SBBuildNumber, "research registry"),
        (internal, TweakID.DisableThermal, "Disable Thermal"),
    ]
    for page, tid, kind in targets:
        sw = page.content._switches.get(tid)
        check(f"{label}: {tid.name} switch present", sw is not None)
        ok, code, _ = tweak_deliverability(
            tid, device_version=version, device_build=build)
        check(f"{label}: {tid.name} ({kind}) switch == backend",
              bool(sw.isEnabled()) == bool(ok),
              f"gui={sw.isEnabled()} backend={ok}/{code}")
    # MobileGestalt-backed rows (RdarFix lives outside section pages, but
    # the backend verdict is the guarantee): locked everywhere except a
    # supported build.
    ok, code, _ = tweak_deliverability(
        TweakID.RdarFix, device_version=version, device_build=build)
    mg_supported = build in ("23C5027f",) or version.startswith("26.1")
    check(f"{label}: RdarFix MG fail-closed={not mg_supported}",
          ok == (mg_supported and code == "DEVICE_TEST_OK") or not ok
          if not mg_supported else ok, code)

print("\nDisable Thermal: registry + catalogue + merged staging")
spec = SPECS_BY_ID.get(TweakID.DisableThermal)
check("DisableThermal has a registry spec", spec is not None)
check("spec is Internal / disabledDaemons / thermalmonitord",
      spec.section is Section.INTERNAL
      and spec.location.value == "/var/db/com.apple.xpc.launchd/disabled.plist"
      and spec.key == "com.apple.thermalmonitord"
      and spec.value is True)
entries = {e["id_name"]: e for e in home_tweak_catalogue()}
check("Home catalogue lists Disable Thermal",
      entries.get("DisableThermal", {}).get("title") == "Disable Thermal")
ok, code, _ = tweak_deliverability(
    TweakID.DisableThermal, device_version="26.6.1", device_build="23G83")
check("Disable Thermal deliverable on 26.6.1 (daemon channel)",
      ok and code == "OK", code)

from src.tweaks.basic_plist_locations import FileLocation  # noqa: E402
from src.tweaks.tweak_loader import load_daemons, load_plist_tweaks  # noqa: E402
from src.tweaks.tweaks import tweaks  # noqa: E402
load_plist_tweaks()
load_daemons()
for tid in (TweakID.DisableThermal, TweakID.Daemons):
    if tid in tweaks:
        tweaks[tid].set_enabled(False)
thermal = tweaks[TweakID.DisableThermal]
daemons = tweaks[TweakID.Daemons]
thermal.set_enabled(True)
daemons.set_enabled(True)
daemons.set_multiple_values(["com.apple.thermalmonitord"], True)
staged = {}
staged = daemons.apply_tweak(staged)
staged = thermal.apply_tweak(staged)
merged = staged.get(FileLocation.disabledDaemons, {})
check("merged disabled.plist keeps daemon keys after Advanced apply",
      merged.get("com.apple.thermalmonitord") is True, str(merged))
staged2 = {}
staged2 = thermal.apply_tweak(staged2)
staged2 = daemons.apply_tweak(staged2)
merged2 = staged2.get(FileLocation.disabledDaemons, {})
check("merge works in the other apply order too",
      merged2.get("com.apple.thermalmonitord") is True, str(merged2))
thermal.set_enabled(False)
daemons.set_enabled(False)

print("\nRisky: CustomResolution obeys the shared decision + range validator")
from src.gui.ios.risky import RiskySection  # noqa: E402
from src.tweaks.capabilities import validate_custom_resolution  # noqa: E402
for label, version, build in DEVICES:
    window = _Window(version, build)
    risky = RiskySection(window)
    risky.refresh()
    app.processEvents()
    sw = risky._switches[TweakID.CustomResolution]
    ok, code, _ = tweak_deliverability(
        TweakID.CustomResolution, device_version=version,
        device_build=build)
    check(f"{label}: CustomResolution switch == backend",
          bool(sw.isEnabled()) == bool(ok),
          f"gui={sw.isEnabled()} backend={ok}/{code}")
    check(f"{label}: locked switch carries a reason",
          ok or bool(sw.toolTip()), sw.toolTip()[:40])
good = validate_custom_resolution({"canvas_width": 1179})
check("validator accepts an in-range payload", good[0], str(good))
bad = validate_custom_resolution({"canvas_width": 100})
check("validator rejects an out-of-range payload", not bad[0], str(bad))
bad2 = validate_custom_resolution({"canvas_width": "wide"})
check("validator rejects a non-int payload", not bad2[0], str(bad2))

print(f"\nALL {PASS} CHECKS PASSED")
