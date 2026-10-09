#!/usr/bin/env python3
"""Fix Audit 45: device-version parsing must never leak InvalidVersion.

Bare ``Version(device_version)`` calls threw packaging's
InvalidVersion raw when the device dropped mid-apply and the version
string came back empty/None/garbage. The safe helpers in
device_manager turn that into a human-readable "device may have
disconnected" NuggetException on the apply/reset paths, while valid
versions behave exactly as before.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit45_version_parse.py
"""
import os
import plistlib
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from packaging.version import InvalidVersion  # noqa: E402

from src.devicemanagement.device_manager import (  # noqa: E402
    DeviceManager, device_version_at_least, device_version_below,
    lg_reset_contents, require_device_version, try_parse_device_version)
from src.exceptions.nugget_exception import NuggetException  # noqa: E402

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}")


def raises_human(fn):
    """Human NuggetException (never a raw InvalidVersion)."""
    try:
        fn()
    except NuggetException as e:
        return "disconnected" in str(e) or "iOS version" in str(e), e
    except InvalidVersion:
        return False, None
    return False, None


# --- try_parse_device_version never raises ---------------------------------
print("try_parse_device_version: valid / empty / None / garbage")
check("valid version parses", str(try_parse_device_version("26.6.1")) == "26.6.1")
check("empty string -> None", try_parse_device_version("") is None)
check("None -> None", try_parse_device_version(None) is None)
check("whitespace -> None", try_parse_device_version("   ") is None)
check("garbage -> None (no InvalidVersion)",
      try_parse_device_version("not-a-version!!") is None)
check("non-string input tolerated",
      str(try_parse_device_version(27)) == "27")

# --- require_device_version: human error on failure ------------------------
print("require_device_version fails human-readably, never InvalidVersion")
ok, err = raises_human(lambda: require_device_version(""))
check("empty version -> human disconnect error", ok, repr(err))
ok, err = raises_human(lambda: require_device_version(None))
check("None version -> human disconnect error", ok, repr(err))
ok, err = raises_human(lambda: require_device_version("garbage!!"))
check("garbage version -> human disconnect error", ok, repr(err))
check("valid version still parses",
      str(require_device_version("27.0")) == "27.0")

# --- comparisons: normal path unchanged, failure path human -----------------
print("device_version_at_least / below")
check("27.0 >= 27.0", device_version_at_least("27.0", "27.0") is True)
check("26.6.1 < 27.0 (at_least False)",
      device_version_at_least("26.6.1", "27.0") is False)
check("26.6.1 below 27.0", device_version_below("26.6.1", "27.0") is True)
check("27.1 not below 27.0", device_version_below("27.1", "27.0") is False)
ok, _ = raises_human(lambda: device_version_at_least("", "27.0"))
check("empty version in comparison -> human error", ok)
ok, _ = raises_human(lambda: device_version_below(None, "27.0"))
check("None version in comparison -> human error", ok)

# --- lg_reset_contents: v4 bytes pinned, garbage fails humanly -------------
print("lg_reset_contents keeps v4 bytes; garbage fails humanly")
check("iOS 26 -> zero-byte (v4)", lg_reset_contents("26.6.1") == b"")
check("iOS 27 -> empty plist (v4)",
      lg_reset_contents("27.0") == plistlib.dumps({}))
check("empty version -> zero-byte (pinned behaviour)",
      lg_reset_contents("") == b"")
check("None version -> zero-byte (pinned behaviour)",
      lg_reset_contents(None) == b"")
ok, _ = raises_human(lambda: lg_reset_contents("garbage!!"))
check("garbage version -> human error, not InvalidVersion", ok)

# --- UI query never raises ---------------------------------------------------
print("get_current_device_partially_supported tolerates garbage")
mgr = object.__new__(DeviceManager)
mgr.data_singleton = SimpleNamespace(
    current_device=SimpleNamespace(version="garbage!!"))
check("garbage device version -> not partially supported, no raise",
      mgr.get_current_device_partially_supported() is False)
mgr.data_singleton = SimpleNamespace(
    current_device=SimpleNamespace(version="27.0"))
check("iOS 27 device -> partially supported",
      mgr.get_current_device_partially_supported() is True)
mgr.data_singleton = SimpleNamespace(current_device=None)
check("no device -> not partially supported",
      mgr.get_current_device_partially_supported() is False)

print(f"\nALL {PASS} CHECKS PASSED")
