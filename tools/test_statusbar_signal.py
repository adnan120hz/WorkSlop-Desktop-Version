#!/usr/bin/env python3
"""Offline tests for the named "Full Signal Bars (No SIM Visual)" recipe.

Pins the classic-binary contract only (no device, no GUI):

* the staged blob is always the 3,944-byte classic struct and survives a
  serialize -> deserialize -> serialize round trip byte-for-byte;
* enabling the feature sets exactly the owned fields (primary GSM bar count
  + item 4 and item 6 visibility) and nothing else;
* the predicate is strict — bars alone, one item alone, or a wrong bar
  value never count as the feature;
* unset clears only the owned override flags, leaving unrelated overrides;
* a fresh tweak (what Page.StatusBar reset stages) has the feature off.

Run: python tools/test_statusbar_signal.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


try:
    from src.tweaks.status_bar.status_bar_tweak import (
        FULL_SIGNAL_BARS, FULL_SIGNAL_FILE, StatusBarTweak)
    from src.tweaks.status_bar.status_setter import (
        Setter, StatusBarItem, _deserialize_override, _serialize_override)
except Exception as e:  # cffi/struct unavailable in this interpreter
    print(f"skipped: {type(e).__name__}: {e}")
    raise SystemExit(0)


def decode(tweak):
    return _deserialize_override(tweak.setter.get_data())


def test_struct_size_and_roundtrip():
    print("\nstruct size + round trip")
    data = Setter().get_data()
    check("fresh blob is 3944 bytes", len(data) == 3944, str(len(data)))
    check("round trip is byte-stable",
          _serialize_override(_deserialize_override(data)) == data)
    tweak = StatusBarTweak()
    tweak.set_full_signal_bars_no_sim()
    blob = tweak.setter.get_data()
    check("feature blob is 3944 bytes", len(blob) == 3944)
    check("feature round trip is byte-stable",
          _serialize_override(_deserialize_override(blob)) == blob)


def test_owned_fields_exact():
    print("\nowned fields")
    tweak = StatusBarTweak()
    # Unrelated state that must survive untouched.
    tweak.set_carrier_override("KeepMe")
    tweak.set_wifi_signal_strength_bars(3)
    tweak.set_item_override(StatusBarItem.MainBatteryStatusBarItem, False)
    before = decode(tweak)

    tweak.set_full_signal_bars_no_sim()
    ov = decode(tweak)
    check("bar override flag set", ov.overrideGSMSignalStrengthBars == 1)
    check("bar value is FULL_SIGNAL_BARS",
          ov.values.GSMSignalStrengthBars == FULL_SIGNAL_BARS,
          str(ov.values.GSMSignalStrengthBars))
    i4 = StatusBarItem.CellularSignalStrengthStatusBarItem.value
    i6 = StatusBarItem.CellularServiceStatusBarItem.value
    check("item 4 override flag set", ov.overrideItemIsEnabled[i4] == 1)
    check("item 4 shown", ov.values.itemIsEnabled[i4] == 1)
    check("item 6 override flag set", ov.overrideItemIsEnabled[i6] == 1)
    check("item 6 shown", ov.values.itemIsEnabled[i6] == 1)
    # Nothing else moved.
    from cffi import FFI
    ffi = FFI()
    check("carrier string untouched",
          ffi.string(ov.values.serviceString).decode()
          == ffi.string(before.values.serviceString).decode() == "KeepMe")
    check("wifi bars untouched", ov.values.wifiSignalStrengthBars == 3)
    i12 = StatusBarItem.MainBatteryStatusBarItem.value
    check("battery item override untouched",
          ov.overrideItemIsEnabled[i12] == 1
          and ov.values.itemIsEnabled[i12] == 0)
    check("secondary GSM untouched",
          ov.overrideSecondaryGSMSignalStrengthBars == 0)
    check("raw GSM untouched", ov.overrideGSMSignalStrengthRaw == 0)
    check("service string override flag untouched by feature",
          ov.overrideServiceString == before.overrideServiceString)


def test_predicate_strictness():
    print("\npredicate strictness")
    tweak = StatusBarTweak()
    check("fresh tweak: feature off",
          not tweak.is_full_signal_bars_no_sim_enabled())
    tweak.set_gsm_signal_strength_bars(FULL_SIGNAL_BARS)
    check("bars alone: feature off",
          not tweak.is_full_signal_bars_no_sim_enabled())
    tweak.set_item_override(
        StatusBarItem.CellularSignalStrengthStatusBarItem, True)
    check("bars + item 4 only: feature off",
          not tweak.is_full_signal_bars_no_sim_enabled())
    tweak.set_full_signal_bars_no_sim()
    check("full recipe: feature on", tweak.is_full_signal_bars_no_sim_enabled())
    tweak.set_gsm_signal_strength_bars(FULL_SIGNAL_BARS + 1)
    check("wrong bar value: feature off",
          not tweak.is_full_signal_bars_no_sim_enabled())
    tweak.set_full_signal_bars_no_sim()
    tweak.unset_item_override(StatusBarItem.CellularServiceStatusBarItem)
    check("item 6 cleared: feature off",
          not tweak.is_full_signal_bars_no_sim_enabled())


def test_unset_clears_only_owned():
    print("\nunset semantics")
    tweak = StatusBarTweak()
    tweak.set_carrier_override("KeepMe")
    tweak.set_full_signal_bars_no_sim()
    tweak.unset_full_signal_bars_no_sim()
    ov = decode(tweak)
    check("bar flag cleared", ov.overrideGSMSignalStrengthBars == 0)
    i4 = StatusBarItem.CellularSignalStrengthStatusBarItem.value
    i6 = StatusBarItem.CellularServiceStatusBarItem.value
    check("item 4 flag cleared", ov.overrideItemIsEnabled[i4] == 0)
    check("item 6 flag cleared", ov.overrideItemIsEnabled[i6] == 0)
    check("carrier override still present", ov.overrideServiceString == 1)
    check("feature predicate off after unset",
          not tweak.is_full_signal_bars_no_sim_enabled())


def test_bar_value_roundtrip():
    print("\nbar value data layer (device-matrix arms)")
    for value in (4, 5):
        tweak = StatusBarTweak()
        tweak.set_gsm_signal_strength_bars(value)
        ov = decode(tweak)
        check(f"bars={value} round-trips",
              ov.values.GSMSignalStrengthBars == value)


def test_staging_and_describe():
    print("\nstaging + describe")
    tweak = StatusBarTweak()
    files = []
    tweak.apply_classic_tweak(files)
    check("disabled tweak stages nothing", files == [])
    tweak.set_enabled(True)
    tweak.set_full_signal_bars_no_sim()
    tweak.apply_classic_tweak(files)
    check("exactly one classic file staged", len(files) == 1)
    staged = files[0]
    check("HomeDomain", staged.domain == "HomeDomain", staged.domain)
    check("classic path",
          staged.restore_path == "/Library/SpringBoard/statusBarOverrides",
          staged.restore_path)
    check("staged contents are the 3944-byte struct",
          len(staged.contents) == 3944)

    desc = tweak.describe_full_signal_bars_no_sim()
    check("describe id", desc["id"] == "statusbar.full_signal_bars_no_sim")
    check("describe name", desc["name"] == "Full Signal Bars (No SIM Visual)")
    check("describe bars", desc["bars"] == FULL_SIGNAL_BARS)
    check("describe items", desc["items"] == [4, 6], str(desc["items"]))
    check("describe file", desc["file"] == FULL_SIGNAL_FILE)

    ops = tweak.describe_active_operations()
    check("one named op when only the feature is on", len(ops) == 1
          and ops[0]["id"] == "statusbar.full_signal_bars_no_sim")
    tweak.set_carrier_override("Extra")
    ops = tweak.describe_active_operations()
    generic = [o for o in ops if o["id"] == "statusbar.overrides"]
    check("generic op excludes owned flags",
          len(generic) == 1 and generic[0]["count"] == 1,
          str(ops))


def test_fresh_struct_is_feature_off():
    print("\nreset-shaped fresh struct")
    fresh = StatusBarTweak()
    check("fresh predicate off", not fresh.is_full_signal_bars_no_sim_enabled())
    check("fresh staged bytes are defaults",
          fresh.setter.get_data() == Setter().get_data())


test_struct_size_and_roundtrip()
test_owned_fields_exact()
test_predicate_strictness()
test_unset_clears_only_owned()
test_bar_value_roundtrip()
test_staging_and_describe()
test_fresh_struct_is_feature_off()

print(f"\nALL {PASS} CHECKS PASSED")
