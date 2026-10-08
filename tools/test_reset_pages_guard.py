#!/usr/bin/env python3
"""Guard tests for get_resettable_pages (Fix A, 2026-10-09).

The Reset dialog died in its constructor when device info had not loaded
yet: get_current_device_version() returns "" with no device selected and
Version("") raises InvalidVersion, so the button looked completely dead.

Locks:
* unknown / empty / unparseable versions never raise and return the base
  page list with the version-gated Status Bar entry hidden (conservative);
* valid-version behavior is byte-for-byte what it was before the guard
  (Status Bar offered only when the device is known to be below iOS 27).

Run: python tools/test_reset_pages_guard.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils.pages import Page, get_resettable_pages

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


BASE = [
    Page.Springboard, Page.InternalOptions, Page.Daemons,
    Page.Tweaks, Page.LiquidGlass, Page.RiskyTweaks,
    Page.EUEnabler, Page.Gestalt,
]


class FakeDeviceManager:
    def __init__(self, version=None, raises=False):
        self._version = version
        self._raises = raises

    def get_current_device_version(self):
        if self._raises:
            raise RuntimeError("device went away")
        return self._version


def test_unknown_versions_never_raise():
    print("\nunknown versions: no raise, base list, Status Bar hidden")
    for version in ("", None, "   ", "garbage!!", "not.a.version"):
        pages = get_resettable_pages(FakeDeviceManager(version))
        check(f"version {version!r} returns the base list",
              pages == BASE, repr([p.name for p in pages]))
        check(f"version {version!r} hides Status Bar (conservative)",
              Page.StatusBar not in pages)
    check("a raising version getter does not raise",
          get_resettable_pages(FakeDeviceManager(raises=True)) == BASE)
    check("device_manager=None does not raise",
          get_resettable_pages(None) == BASE)


def test_valid_versions_unchanged():
    print("\nvalid versions: behavior exactly as before the guard")
    pages = get_resettable_pages(FakeDeviceManager("26.6.1"))
    check("iOS 26.6.1 offers Status Bar first",
          pages == [Page.StatusBar] + BASE, repr([p.name for p in pages]))
    check("iOS 16.0 offers Status Bar",
          get_resettable_pages(FakeDeviceManager("16.0"))[0] == Page.StatusBar)
    for version in ("27.0", "27.1", "28.0"):
        check(f"iOS {version} hides Status Bar",
              get_resettable_pages(FakeDeviceManager(version)) == BASE)


test_unknown_versions_never_raise()
test_valid_versions_unchanged()

print(f"\nALL {PASS} CHECKS PASSED")
