#!/usr/bin/env python3
"""Audit 38: thermalmonitord single-owner merge.

Before the fix, ``com.apple.thermalmonitord`` had two writers into
``FileLocation.disabledDaemons`` — the registry "Disable Thermal"
BasicPlistTweak (value True) and the Daemons AdvancedPlistTweak
(``Daemon.thermalmonitord``). Basic used plain assignment and
Advanced used ``dict.update``, so the staged disabled.plist was
last-write-wins: with Disable Thermal ON and the Daemons thermal
toggle OFF, applying Daemons last staged ``False`` (re-enabled) and
applying it first staged ``True`` — same user intent, two results.

The fix routes both writers through the one
``merge_disabled_plist`` owner in ``tweak_classes`` (logical OR for
bool values). This test proves both apply orders now stage the
identical dict and identical plist bytes for every combination,
and that the final value is the logical OR (disabled if either
writer requests it).

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit38_thermal_owner.py
"""
import inspect
import os
import plistlib
import sys

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

from src.tweaks.basic_plist_locations import FileLocation  # noqa: E402
from src.tweaks.tweak_classes import (  # noqa: E402
    AdvancedPlistTweak, BasicPlistTweak, merge_disabled_plist,
)

THERMAL = "com.apple.thermalmonitord"
LOC = FileLocation.disabledDaemons


def fresh_pair(daemons_thermal):
    """Fresh instances (no shared global state) for one scenario."""
    thermal = BasicPlistTweak(LOC, THERMAL, value=True)
    thermal.set_enabled(True)
    daemons = AdvancedPlistTweak(
        LOC, {THERMAL: daemons_thermal, "com.apple.gamed": True},
        allowed_keys={THERMAL, "com.apple.gamed"})
    daemons.set_enabled(True)
    return thermal, daemons


def stage_in_order(first, second):
    staged = {}
    staged = first.apply_tweak(staged)
    staged = second.apply_tweak(staged)
    return staged.get(LOC, {})


def plist_bytes(payload):
    return plistlib.dumps(payload, fmt=plistlib.FMT_BINARY, sort_keys=True)


print("\nAudit 38: single owner is the shared merge helper")
check("merge_disabled_plist exists and is callable",
      callable(merge_disabled_plist))
check("BasicPlistTweak routes disabledDaemons through the owner",
      "merge_disabled_plist" in inspect.getsource(BasicPlistTweak.apply_tweak))
check("AdvancedPlistTweak routes disabledDaemons through the owner",
      "merge_disabled_plist" in inspect.getsource(AdvancedPlistTweak.apply_tweak))

print("\nAudit 38: helper is OR, commutative and idempotent")
for a, b, want in [(True, True, True), (True, False, True),
                   (False, True, True), (False, False, False)]:
    got_ab = merge_disabled_plist({THERMAL: a}, {THERMAL: b})[THERMAL]
    got_ba = merge_disabled_plist({THERMAL: b}, {THERMAL: a})[THERMAL]
    check(f"OR({a},{b}) == {want} in both directions",
          got_ab is want and got_ba is want, f"ab={got_ab} ba={got_ba}")
check("helper merging is idempotent",
      merge_disabled_plist({THERMAL: True}, {THERMAL: True}) == {THERMAL: True})
check("helper keeps unrelated keys from both sides",
      merge_disabled_plist({"a": True}, {"b": False}) == {"a": True, "b": False})

print("\nAudit 38: both apply orders stage identical disabled.plist")
# The original conflict: Disable Thermal ON vs Daemons thermal OFF.
for daemons_thermal, want, label in [
        (True, True, "both request disable"),
        (False, True, "CONFLICT: thermal ON, daemons thermal OFF -> OR wins"),
]:
    thermal, daemons = fresh_pair(daemons_thermal)
    order1 = stage_in_order(daemons, thermal)
    thermal2, daemons2 = fresh_pair(daemons_thermal)
    order2 = stage_in_order(thermal2, daemons2)
    check(f"{label}: dicts identical across orders", order1 == order2,
          f"{order1} vs {order2}")
    check(f"{label}: plist bytes identical across orders",
          plist_bytes(order1) == plist_bytes(order2))
    check(f"{label}: final thermal value is OR result",
          order1.get(THERMAL) is want, str(order1))
    check(f"{label}: unrelated daemon keys survive both orders",
          order1.get("com.apple.gamed") is True
          and order2.get("com.apple.gamed") is True)

print("\nAudit 38: single-writer cases still behave")
# Only Daemons writes (Disable Thermal off): its value stands.
thermal_off = BasicPlistTweak(LOC, THERMAL, value=True)
thermal_off.set_enabled(False)
daemons_on = AdvancedPlistTweak(
    LOC, {THERMAL: True}, allowed_keys={THERMAL})
daemons_on.set_enabled(True)
s1 = stage_in_order(daemons_on, thermal_off)
s2 = stage_in_order(thermal_off, daemons_on)
check("daemons-only ON stages True in both orders",
      s1 == s2 == {THERMAL: True}, f"{s1} vs {s2}")

thermal_off2 = BasicPlistTweak(LOC, THERMAL, value=True)
thermal_off2.set_enabled(False)
daemons_off = AdvancedPlistTweak(
    LOC, {THERMAL: False}, allowed_keys={THERMAL})
daemons_off.set_enabled(True)
s1 = stage_in_order(daemons_off, thermal_off2)
s2 = stage_in_order(thermal_off2, daemons_off)
check("daemons-only OFF stages False in both orders",
      s1 == s2 == {THERMAL: False}, f"{s1} vs {s2}")
check("daemons-only OFF bytes identical across orders",
      plist_bytes(s1) == plist_bytes(s2))

# Only Disable Thermal writes (Daemons tweak disabled): True stands.
thermal_on = BasicPlistTweak(LOC, THERMAL, value=True)
thermal_on.set_enabled(True)
daemons_disabled = AdvancedPlistTweak(
    LOC, {THERMAL: False}, allowed_keys={THERMAL})
daemons_disabled.set_enabled(False)
s1 = stage_in_order(daemons_disabled, thermal_on)
s2 = stage_in_order(thermal_on, daemons_disabled)
check("thermal-only ON stages True in both orders",
      s1 == s2 == {THERMAL: True}, f"{s1} vs {s2}")

print("\nAudit 38: real loader instances (registry + Daemons tweak)")
from src.tweaks.tweak_loader import load_daemons, load_plist_tweaks  # noqa: E402
from src.tweaks.tweaks import tweaks  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402

load_plist_tweaks()
load_daemons()
thermal = tweaks[TweakID.DisableThermal]
daemons = tweaks[TweakID.Daemons]
try:
    thermal.set_enabled(True)
    daemons.set_enabled(True)
    # Explicit OFF in Daemons is the conflicting writer from the audit.
    daemons.set_multiple_values([THERMAL], False)
    staged_a = {}
    staged_a = daemons.apply_tweak(staged_a)
    staged_a = thermal.apply_tweak(staged_a)
    staged_b = {}
    staged_b = thermal.apply_tweak(staged_b)
    staged_b = daemons.apply_tweak(staged_b)
    dict_a = staged_a.get(LOC, {})
    dict_b = staged_b.get(LOC, {})
    check("real tweaks: dicts identical across orders", dict_a == dict_b,
          f"{dict_a} vs {dict_b}")
    check("real tweaks: plist bytes identical across orders",
          plist_bytes(dict_a) == plist_bytes(dict_b))
    check("real tweaks: OR keeps thermal disabled (True)",
          dict_a.get(THERMAL) is True and dict_b.get(THERMAL) is True,
          str(dict_a))
finally:
    thermal.set_enabled(False)
    daemons.set_enabled(False)

print(f"\nALL {PASS} CHECKS PASSED")
