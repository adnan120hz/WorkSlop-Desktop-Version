#!/usr/bin/env python3
"""Fix Audit 9: the S8 switches are locked until the route can run.

Backend (unchanged): the Squair + Latest payloads ride the S8 full
backup (all data) route only on iOS 26.6.1 builds 23G82/23G83
(``lgd_full_route_applicable``, fail-closed). Before this fix the UI
switches stayed enabled with no device — or on any other build — and
the apply then silently skipped the payloads.

This suite stubs the device (offscreen, no hardware) and proves:
* no device            -> both S8 switches disabled, reason tooltip set,
                          and a programmatic toggle cannot enable them;
* wrong build (26.6.1/23G71, 26.1, iOS 27) -> disabled the same way;
* iOS 26.6.1 build 23G82 (and 23G83) + device -> switches enabled and
  toggling drives the registry tweak;
* the dedicated S8 page status line states the lock (and the route
  distinction) when gated, and not when the build qualifies;
* no user-facing gate text uses "unverified" / "not verified".

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit9_s8_ui_gate.py
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
from src.gui.ios.liquid_glass_disable import IOSLiquidGlassDisablePage  # noqa: E402
from src.gui.ios.tweaks import IOSSectionPage, _s8_route_lock_reason  # noqa: E402
from src.tweaks.registry import Section  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402
from src.tweaks.tweaks import tweaks  # noqa: E402

S8_IDS = (TweakID.LGDisableSquairTest, TweakID.LGDisableLatest)


class _DeviceManager:
    """Stub device manager: no hardware, exact getter surface."""

    def __init__(self, udid=None, version="", build=""):
        device = None
        if udid:
            device = SimpleNamespace(
                udid=udid, name="Stub iPhone", version=version,
                build=build, model="iPhone17,1", hardware="D17AP",
                cpu="t8110", connected_via_usb=True)
        self._udid = udid
        self._version = version
        self._build = build
        self.data_singleton = SimpleNamespace(current_device=device)

    def get_current_device_udid(self):
        return self._udid

    def get_current_device_version(self):
        return self._version

    def get_current_device_build(self):
        return self._build

    def get_current_device_model(self):
        return "iPhone17,1"

    def get_current_device_name(self):
        return "Stub iPhone"


class _Window:
    apply_in_progress = False

    def __init__(self, udid=None, version="", build=""):
        self.device_manager = _DeviceManager(udid, version, build)
        self.shown_pages = []

    def show_ios_page(self, index):
        self.shown_pages.append(index)

    def update_label(self, _txt):
        pass

    def alert_message(self, _msg):
        pass


def _reset_s8():
    for tid in S8_IDS:
        if tid in tweaks:
            tweaks[tid].set_enabled(False)


def _section_switches(udid, version, build):
    _reset_s8()
    window = _Window(udid, version, build)
    page = IOSSectionPage(window, Section.LIQUID_GLASS_DISABLE)
    app.processEvents()
    return page


print("\nHelper: only the two S8 ids, only outside the exact window")
check("non-S8 tweak is never S8-locked",
      _s8_route_lock_reason(TweakID.SBDontLockAfterCrash,
                            "", "", False) == "")
check("no device locks the S8 switch",
      "23G82" in _s8_route_lock_reason(
          TweakID.LGDisableLatest, "26.6.1", "23G83", False))
check("23G82 with a device is unlocked",
      _s8_route_lock_reason(TweakID.LGDisableLatest,
                            "26.6.1", "23G82", True) == "")
check("23G83 with a device is unlocked",
      _s8_route_lock_reason(TweakID.LGDisableSquairTest,
                            "26.6.1", "23G83", True) == "")
check("wrong build with a device is locked",
      _s8_route_lock_reason(TweakID.LGDisableLatest,
                            "26.6.1", "23G71", True) != "")

CASES = [
    # (label, udid, version, build, expect_enabled)
    ("no device", None, "", "", False),
    ("wrong build 26.6.1/23G71", "STUB", "26.6.1", "23G71", False),
    ("older iOS 26.1", "STUB", "26.1", "23B85", False),
    ("iOS 27", "STUB", "27.0", "24A435", False),
    ("iOS 26.6.1 build 23G82", "STUB", "26.6.1", "23G82", True),
    ("iOS 26.6.1 build 23G83", "STUB", "26.6.1", "23G83", True),
]

print("\nSection switches follow the S8 gate")
for label, udid, version, build, expect_enabled in CASES:
    page = _section_switches(udid, version, build)
    for tid in S8_IDS:
        sw = page.content._switches.get(tid)
        card = page.content._switch_cards.get(tid)
        check(f"{label}: {tid.name} switch present", sw is not None)
        check(f"{label}: {tid.name} switch enabled == {expect_enabled}",
              bool(sw.isEnabled()) == expect_enabled,
              f"gui={sw.isEnabled()}")
        check(f"{label}: {tid.name} card enabled == {expect_enabled}",
              bool(card.isEnabled()) == expect_enabled)
        if expect_enabled:
            sw.setChecked(True)
            check(f"{label}: {tid.name} toggle enables the tweak",
                  tweaks[tid].enabled)
            sw.setChecked(False)
            check(f"{label}: {tid.name} toggle back disables it",
                  not tweaks[tid].enabled)
        else:
            check(f"{label}: {tid.name} locked switch carries the reason",
                  "23G82" in sw.toolTip(), sw.toolTip()[:60])
            sw.setChecked(True)  # programmatic: guarded, must not enable
            check(f"{label}: {tid.name} cannot be enabled while locked",
                  not tweaks[tid].enabled and not sw.isChecked())
            sw.setChecked(False)
    _reset_s8()

print("\nDedicated S8 page: honest status line per device state")
for label, udid, version, build, expect_enabled in CASES:
    _reset_s8()
    window = _Window(udid, version, build)
    page = IOSLiquidGlassDisablePage(window)
    app.processEvents()
    page.refresh()
    text = page._status_label.text()
    sw = page.content._switches[TweakID.LGDisableLatest]
    check(f"{label}: page switch enabled == {expect_enabled}",
          bool(sw.isEnabled()) == expect_enabled)
    check(f"{label}: status names the full-backup (all data) route",
          "full backup (all data)" in text, text[:70])
    if expect_enabled:
        check(f"{label}: status does not claim a lock",
              "locked" not in text.lower(), text[:70])
    else:
        check(f"{label}: status states the lock with its window",
              "locked" in text.lower() and "23G82" in text, text[:70])
        check(f"{label}: status separates Partial Restore / iOS 27 routes",
              "Partial Restore" in text and "iOS 27" in text, text[:70])
    lowered = text.lower()
    check(f"{label}: status avoids unverified/not verified wording",
          "unverified" not in lowered and "not verified" not in lowered)
_reset_s8()

print(f"\nALL {PASS} CHECKS PASSED")
