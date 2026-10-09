#!/usr/bin/env python3
"""Fix Audit 84 (device_manager part): LGD state-reset failures are logged.

``_lgd_prepare_squair`` / ``_lgd_prepare_latest`` clear the tweak's
stale staged state before arming; a failure there used to vanish into
``except: pass``. It is now logged through the module logger
(``GoldenNugget.protective`` via log_warn) — behaviour otherwise
unchanged: arming still continues, still unarmed when disabled.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit84_lgd_reset_logging.py
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

import src.devicemanagement.device_manager as dm_mod  # noqa: E402
from src.devicemanagement.device_manager import DeviceManager  # noqa: E402
from src.tweaks.tweaks import TweakID  # noqa: E402

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}")


class ExplodingState:
    """Tweak stand-in whose state attributes refuse assignment."""

    enabled = False

    def __setattr__(self, name, value):
        raise RuntimeError(f"state frozen: {name}")


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages: list = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def run_prepare(method_name, tweak_id):
    """Run one LGD prepare with an exploding tweak; return log lines."""
    mgr = object.__new__(DeviceManager)
    fake_tweaks = dict(dm_mod.tweaks)
    fake_tweaks[tweak_id] = ExplodingState()
    real_tweaks = dm_mod.tweaks
    dm_mod.tweaks = fake_tweaks
    handler = Capture()
    logger = logging.getLogger("GoldenNugget.protective")
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        asyncio.run(getattr(mgr, method_name)())
    finally:
        dm_mod.tweaks = real_tweaks
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    return handler.messages


print("Squair state-reset failure is logged, not swallowed")
msgs = run_prepare("_lgd_prepare_squair", TweakID.LGDisableSquairTest)
check("a warning was logged", len(msgs) >= 1, repr(msgs))
check("log names the failure",
      any("could not reset" in m and "state frozen" in m for m in msgs),
      repr(msgs))

print("Latest state-reset failure is logged, not swallowed")
msgs = run_prepare("_lgd_prepare_latest", TweakID.LGDisableLatest)
check("a warning was logged", len(msgs) >= 1, repr(msgs))
check("log names the failure",
      any("could not reset" in m and "state frozen" in m for m in msgs),
      repr(msgs))

print("source no longer swallows the LGD resets silently")
src = open(os.path.join(os.path.dirname(__file__), "..",
                        "src", "devicemanagement",
                        "device_manager.py")).read()
for fn in ("_lgd_prepare_squair", "_lgd_prepare_latest"):
    body = src.split(f"async def {fn}", 1)[1].split("\n    async def ", 1)[0]
    check(f"{fn} logs its state-reset failure",
          "could not reset" in body and "log_warn" in body)

print(f"\nALL {PASS} CHECKS PASSED")
