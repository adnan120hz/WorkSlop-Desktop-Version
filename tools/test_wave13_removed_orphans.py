#!/usr/bin/env python3
"""Wave 13 audit test: removed-but-untombstoned orphan TweakIDs.

Two Liquid Glass IDs were dropped from the product registry by the Wave 10
audit (registry.py comments still say "REMOVED"), but their names were
never added to ``REMOVED_TWEAK_IDS``:

* ``GranularSpringBoard`` — invented key ``SBGranularGlass`` (not a real
  SpringBoard preference).
* ``StatusBarOverrides`` — once mis-registered as a plist key; the live
  feature uses the separate StatusBar archive mechanism instead.

Because they were not tombstoned, an old preset naming either ID parsed
fine, passed ``tweak_deliverability`` as ``OK``, and then hit
``target is None: continue`` in the preset applier — silently dropped,
with nothing recorded in ``last_skipped``. This test pins the corrected
behaviour: both IDs resolve to ``REMOVED_TWEAK``, and neither has an
active registry spec or payload, so tombstoning them cannot change any
delivered bytes.

Run: python tools/test_wave13_removed_orphans.py
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _install_pyside_stubs():
    class Dummy:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return Dummy()

    for name in ("PySide6", "PySide6.QtCore", "PySide6.QtGui",
                 "PySide6.QtWidgets"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__getattr__ = lambda _n: Dummy  # noqa: B023
            sys.modules[name] = mod
    core = sys.modules["PySide6.QtCore"]
    core.QT_TRANSLATE_NOOP = lambda _c, s, *a, **k: s


_install_pyside_stubs()

from src.tweaks.tweak_names import TweakID  # noqa: E402
from src.tweaks.capabilities import (  # noqa: E402
    is_removed_tweak, tweak_deliverability,
)
from src.tweaks.registry import SPECS_BY_ID  # noqa: E402

FAILED = []


def check(label, condition):
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        FAILED.append(label)


ORPHANS = (TweakID.GranularSpringBoard, TweakID.StatusBarOverrides)

for tid in ORPHANS:
    # No active spec/instance exists, so tombstoning cannot change any
    # payload — this is a bookkeeping fix only.
    check(f"{tid.name} has no active registry spec", tid not in SPECS_BY_ID)
    check(f"{tid.name} is tombstoned in REMOVED_TWEAK_IDS",
          is_removed_tweak(tid))
    deliverable, reason, _msg = tweak_deliverability(
        tid, "26.6.1", "23G83")
    check(f"{tid.name} deliverability is REMOVED_TWEAK on target",
          not deliverable and reason == "REMOVED_TWEAK")

# Controls: the fix must not swallow live neighbours.
check("SolariumForceFallback stays live/deliverable",
      not is_removed_tweak(TweakID.SolariumForceFallback)
      and tweak_deliverability(TweakID.SolariumForceFallback,
                                "26.6.1", "23G83")[1] == "OK")
check("ForceSolariumFallback alias still resolves to the live tweak",
      tweak_deliverability(TweakID.ForceSolariumFallback,
                            "26.6.1", "23G83")[1] == "OK")

if FAILED:
    print(f"\n{len(FAILED)} CHECK(S) FAILED")
    sys.exit(1)
print("\nALL CHECKS PASSED")
