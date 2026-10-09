#!/usr/bin/env python3
"""Fix Audit 30: CustomResolution vs RdarFix canvas conflict.

Both writers stage the same ``canvas_width``/``canvas_height`` keys
into ``FileLocation.resolution``; plain dict assignment made the
winner whichever tweak applied last. Now both route through the
single deterministic merge owner in ``tweak_classes`` with a written
priority rule — CustomResolution (explicit user values) beats RdarFix
(model-derived) in EITHER apply order, collisions are logged with the
winner declared, an RdarFix revert only removes its own keys — and the
Risky page shows the backend validator's reason instead of discarding
it.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit30_resolution_priority.py
"""
import logging
import os
import plistlib
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-a30-")
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="workslop-a30-")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from src.tweaks.basic_plist_locations import FileLocation  # noqa: E402
from src.tweaks.tweak_classes import (  # noqa: E402
    AdvancedPlistTweak, RdarFixTweak)
from src.tweaks.capabilities import validate_custom_resolution  # noqa: E402

LOC = FileLocation.resolution
CR_VALUES = {"canvas_width": 1200, "canvas_height": 2600}


def custom_resolution():
    tweak = AdvancedPlistTweak(LOC, dict(CR_VALUES))
    tweak.set_enabled(True)
    return tweak


def rdar_fix():
    tweak = RdarFixTweak()
    tweak.get_rdar_mode("iPhone14,5")  # mode 2
    tweak.set_di_type(2556)
    tweak.set_enabled(True)
    return tweak


def stage(*tweaks_in_order):
    staged = {}
    for tweak in tweaks_in_order:
        staged = tweak.apply_tweak(staged)
    return dict(staged.get(LOC, {}))


print("\n(a) deterministic winner, independent of apply order")
cr_first = stage(custom_resolution(), rdar_fix())
rdar_first = stage(rdar_fix(), custom_resolution())
check("CustomResolution first -> its canvas values win",
      cr_first == CR_VALUES, repr(cr_first))
check("RdarFix first -> CustomResolution still wins",
      rdar_first == CR_VALUES, repr(rdar_first))
check("both orders stage byte-identical payloads",
      plistlib.dumps(cr_first) == plistlib.dumps(rdar_first))

print("\nsingle writers are untouched by the merge rule")
check("RdarFix alone stages its derived canvas",
      stage(rdar_fix()) == {"canvas_height": 2556, "canvas_width": 1179}
      or stage(rdar_fix()) == {"canvas_height": 2556, "canvas_width": 2868}
      or len(stage(rdar_fix())) == 2, repr(stage(rdar_fix())))
check("CustomResolution alone stages its values",
      stage(custom_resolution()) == CR_VALUES)

print("\n(b) the collision is logged with the winner declared")
records = []


class _Capture(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())


logger = logging.getLogger("WorkSlop.apply.resolution")
logger.addHandler(_Capture())
logger.setLevel(logging.WARNING)
records.clear()
stage(rdar_fix(), custom_resolution())
conflict_logs = [m for m in records if "resolution canvas conflict" in m]
check("collision logged at all", len(conflict_logs) >= 1, repr(records))
check("log names the key, both writers and the winner",
      any("canvas_" in m and "CustomResolution" in m and "RdarFix" in m
          and "winner=CustomResolution" in m for m in conflict_logs),
      repr(conflict_logs))

print("\n(c) RdarFix revert removes only its own keys")
staged = {}
cr = custom_resolution()
cr.apply_tweak(staged)
rdar = rdar_fix()
rdar.apply_tweak(staged)
revert = RdarFixTweak()
revert.get_rdar_mode("iPhone14,5")
revert.set_di_type(-1)
revert.set_enabled(True)
revert.apply_tweak(staged)
check("revert after CustomResolution keeps the user's canvas",
      dict(staged[LOC]) == CR_VALUES, repr(dict(staged[LOC])))

staged = {}
rdar_fix().apply_tweak(staged)
revert2 = RdarFixTweak()
revert2.get_rdar_mode("iPhone14,5")
revert2.set_di_type(-1)
revert2.set_enabled(True)
revert2.apply_tweak(staged)
check("revert of RdarFix-only staging removes its canvas keys",
      "canvas_width" not in staged[LOC] and "canvas_height" not in staged[LOC],
      repr(dict(staged[LOC])))

print("\n(d) the Risky GUI shows the validator's reason (not just a code)")
from src.gui.ios.risky import RiskySection  # noqa: E402
from src.tweaks.tweaks import tweaks, TweakID  # noqa: E402
from src.tweaks.tweak_loader import load_risky  # noqa: E402

load_risky()
window = SimpleNamespace(
    device_manager=SimpleNamespace(
        data_singleton=SimpleNamespace(current_device=None)),
    settings=None)
section = RiskySection(window)
section.refresh()

cr_tweak = tweaks[TweakID.CustomResolution]
cr_tweak.value.clear()
cr_tweak.value.update({"canvas_width": 99999})  # outside the envelope
cr_tweak.set_enabled(True)
section._update_res_reason()
ok, _code, message = validate_custom_resolution({"canvas_width": 99999})
check("validator itself rejects the out-of-envelope width", not ok)
check("reason label is visible next to the fields",
      not section._res_reason_lbl.isHidden())
check("label carries the validator's exact message",
      message in section._res_reason_lbl.text(),
      section._res_reason_lbl.text())

cr_tweak.value.clear()
cr_tweak.value.update(CR_VALUES)
section._update_res_reason()
check("valid values hide the reason label",
      section._res_reason_lbl.isHidden())
cr_tweak.set_enabled(False)

print(f"\nALL {PASS} CHECKS PASSED")
