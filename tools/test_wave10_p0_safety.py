#!/usr/bin/env python3
"""Offline tests for the Wave 10 P0 safety gates (no device needed).

Covers the non-reset half of AUDIT-FINAL-WAVE10 Package 0:

* ``RdarFix`` follows the shared MobileGestalt decision even though it
  writes the resolution plist, not the MobileGestalt cache.
* ``AIFeatureFlags`` / ``AIFeatureFlagsUI`` are removed tombstones and can
  never generate the dead FeatureFlags Global.plist payload.
* Registry FeatureFlags specs were capped at iOS 26.1 in Package 0;
  Wave 10 Package 1 supersedes that disposition and removes them as
  tombstones, so they can never generate the dead channel payload.
* Risky ``CustomResolution`` is fenced by the backend validator: canvas
  keys only, real ints only, inside the existing RDAR canvas envelope.

The zero-byte reset half is covered by ``tools/test_reset_no_capture.py``.

Run: python tools/test_wave10_p0_safety.py
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.devicemanagement.constants import mobilegestalt_decision
from src.tweaks import tweak_loader
from src.tweaks.capabilities import (
    is_removed_tweak, tweak_deliverability, validate_custom_resolution,
)
from src.tweaks.registry import SPECS_BY_ID
from src.tweaks.tweak_classes import FeatureFlagTweak, RdarFixTweak
from src.tweaks.tweaks import tweaks, TweakID

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


LOCKED = mobilegestalt_decision("23G83", "26.6.1")
SUPPORTED = mobilegestalt_decision("23C5027f", "26.2")


def test_rdarfix_follows_mobilegestalt_decision():
    print("\nRdarFix is gated by the MobileGestalt-page decision")
    check("23G83 decision is locked", not LOCKED.supported, LOCKED.reason_code)
    check("23C5027f decision is supported", SUPPORTED.supported)

    ok, code, _ = tweak_deliverability(
        TweakID.RdarFix, device_version="26.6.1", device_build="23G83")
    check("RdarFix is not deliverable on 23G83", not ok, code)
    ok, code, _ = tweak_deliverability(
        TweakID.RdarFix, device_version="26.2", device_build="23C5027f")
    check("RdarFix is deliverable on a supported build", ok, code)
    ok, code, _ = tweak_deliverability(TweakID.RdarFix)
    check("RdarFix fails closed with no device", not ok, code)

    stale = RdarFixTweak()
    stale.set_enabled(True)
    tweaks[TweakID.RdarFix] = stale
    device = SimpleNamespace(build="23G83", version="26.6.1",
                             model="iPhone14,5")
    tweak_loader.load_rdar_fix(device, LOCKED)
    check("locked load forces a stale RdarFix off",
          tweaks[TweakID.RdarFix].enabled is False)

    tweaks.pop(TweakID.RdarFix, None)
    supported_device = SimpleNamespace(
        build="23C5027f", version="26.2", model="iPhone14,5")
    tweak_loader.load_rdar_fix(supported_device, SUPPORTED)
    check("supported load registers RdarFix", TweakID.RdarFix in tweaks)
    check("supported RdarFix resolves its model mode",
          tweaks[TweakID.RdarFix].mode == 2)


def test_ai_featureflags_are_tombstones():
    print("\nAIFeatureFlags / AIFeatureFlagsUI can never deliver")
    for tid in (TweakID.AIFeatureFlags, TweakID.AIFeatureFlagsUI):
        for build, version in (("23G83", "26.6.1"), ("23C5027f", "26.2")):
            ok, code, _ = tweak_deliverability(
                tid, device_version=version, device_build=build)
            check(f"{tid.name} is removed on {build}", not ok, code)
            check(f"{tid.name} reason is REMOVED_TWEAK",
                  code == "REMOVED_TWEAK", code)

        stale = FeatureFlagTweak(flag_category="Siri", flag_names=["x"])
        stale.set_enabled(True)
        tweaks[tid] = stale

    device = SimpleNamespace(build="23G83", version="26.6.1",
                             model="iPhone14,5", hardware="", cpu="")
    tweak_loader.load_eligibility(device, LOCKED)
    check("eligibility load drops stale AIFeatureFlags",
          TweakID.AIFeatureFlags not in tweaks)
    check("eligibility load drops stale AIFeatureFlagsUI",
          TweakID.AIFeatureFlagsUI not in tweaks)


def test_registry_featureflags_are_removed():
    print("\nRegistry FeatureFlags specs are removed tombstones (Package 1)")
    for tid in (TweakID.ClockAnim, TweakID.Lockscreen, TweakID.PhotoUI,
                TweakID.AI, TweakID.KioskMode):
        check(f"{tid.name} has no active spec", tid not in SPECS_BY_ID)
        check(f"{tid.name} is a removed tombstone", is_removed_tweak(tid))
        ok, code, _ = tweak_deliverability(
            tid, device_version="26.6.1", device_build="23G83")
        check(f"{tid.name} is not deliverable on 26.6.1",
              not ok and code == "REMOVED_TWEAK", code)


def test_custom_resolution_validator():
    print("\nCustomResolution backend validator")
    ok, code, _ = validate_custom_resolution(
        {"canvas_width": 1179, "canvas_height": 2556})
    check("in-range pair passes", ok, code)
    ok, _, _ = validate_custom_resolution({"canvas_width": 1179})
    check("single dimension passes (historical behaviour)", ok)

    bad_payloads = [
        ({"canvas_width": 100}, "below width envelope"),
        ({"canvas_height": 9999}, "above height envelope"),
        ({"canvas_width": "1179"}, "string dimension"),
        ({"canvas_width": True}, "bool dimension"),
        ({"canvas_width": 1179, "evil": 1}, "unknown key"),
        ({}, "no dimensions"),
        (None, "non-dict payload"),
    ]
    for payload, label in bad_payloads:
        ok, code, _ = validate_custom_resolution(payload)
        check(f"{label} is rejected", not ok, code)
        check(f"{label} reason is stable",
              code == "INVALID_CUSTOM_RESOLUTION", code)


test_rdarfix_follows_mobilegestalt_decision()
test_ai_featureflags_are_tombstones()
test_registry_featureflags_are_removed()
test_custom_resolution_validator()

print(f"\nALL {PASS} CHECKS PASSED")
