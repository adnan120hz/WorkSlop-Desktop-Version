#!/usr/bin/env python3
"""Round-10 audit: MobileGestalt decision matrix + CacheData guardrails.

* The shared MobileGestalt decision is fail-closed: allowlisted build
  -> supported; 26.6.1 builds -> locked; unknown build with a 26.2+
  version -> locked; no evidence -> unknown (never supported).
* MobileGestaltCacheDataTweak raises BEFORE writing on short data or
  a missing pattern, and a disabled tweak touches nothing.

Run: python tools/test_audit_mobilegestalt.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.devicemanagement.constants import mobilegestalt_decision
from src.exceptions.nugget_exception import NuggetException
from src.tweaks.tweak_classes import MobileGestaltCacheDataTweak

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-10: MobileGestalt")
    d = mobilegestalt_decision("23G83", "26.6.1")
    check("26.6.1 final build is locked", d.state == "locked"
          and not d.supported, d.reason_code)
    d = mobilegestalt_decision("23G82", "26.6.1")
    check("26.6.1 RC build is locked", d.state == "locked")
    d = mobilegestalt_decision("", "26.6.1")
    check("26.2+ version without build is locked",
          d.state == "locked", d.reason_code)
    d = mobilegestalt_decision("", "26.1")
    check("pre-26.2 version is supported", d.supported
          and d.source == "version")
    d = mobilegestalt_decision("", "")
    check("no evidence is unknown, never supported",
          d.state == "unknown" and not d.supported)
    d = mobilegestalt_decision("99Z999", "")
    check("unknown build alone stays unknown", d.state == "unknown")
    d = mobilegestalt_decision("99Z999", "27.0")
    check("iOS 27 version is locked", d.state == "locked")

    tw = MobileGestaltCacheDataTweak(slice_start=1616, slice_length=200)
    tw.set_enabled(True)
    short = {"CacheData": b"\x00" * 100}
    try:
        tw.apply_tweak(dict(short))
        raised = False
    except NuggetException:
        raised = True
    check("short CacheData raises before writing", raised)

    flat = {"CacheData": b"\x00" * 2000}
    snapshot = dict(flat)
    try:
        tw.apply_tweak(flat)
        raised = False
    except NuggetException:
        raised = True
    check("missing pattern raises", raised)
    check("failed apply leaves the plist untouched", flat == snapshot)

    tw2 = MobileGestaltCacheDataTweak(slice_start=1616, slice_length=200)
    src = {"CacheData": b"\x01" * 10}
    check("disabled CacheData tweak is a no-op",
          tw2.apply_tweak(src) == src)

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
