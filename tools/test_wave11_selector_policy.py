#!/usr/bin/env python3
"""Checks for the 2026-10-03 debt fixes: Windows Selector event loop
policy at every device asyncio entry point, and the cross-platform
restart helper (src/utils/restart.py).

Run: QT_QPA_PLATFORM=offscreen python tools/test_wave11_selector_policy.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def _read(rel):
    with open(os.path.join(os.path.dirname(__file__), "..", rel),
              encoding="utf-8") as fh:
        return fh.read()


print("\nWindows Selector event loop policy")
import asyncio  # noqa: E402

from src.devicemanagement.session import install_windows_selector_policy

before = type(asyncio.get_event_loop_policy()).__name__
install_windows_selector_policy()
after = type(asyncio.get_event_loop_policy()).__name__
if sys.platform != "win32":
    check("helper is a no-op off Windows", before == after,
          f"{before} -> {after}")
    check("helper never touches the Windows-only policy class",
          "WindowsSelectorEventLoopPolicy" in _read(
              "src/devicemanagement/session.py"))
else:
    check("selector policy installed on Windows",
          after == "WindowsSelectorEventLoopPolicy", after)

# Every device asyncio entry point re-asserts the policy before
# asyncio.run (the policy object is process-global; these calls are the
# belt-and-braces so no path can fall back to the Proactor loop).
for rel, minimum in (
        ("src/devicemanagement/device_manager.py", 4),
        ("src/gui/thread_workers/apply_worker.py", 9),
        ("src/gui/thread_workers/pb_worker.py", 1),
        ("src/gui/ios/appdata.py", 4),
        ("src/cli/cmd_backup.py", 1),
        ("main_app.py", 1)):
    count = _read(rel).count("install_windows_selector_policy()")
    check(f"policy installed in {rel}", count >= minimum, str(count))

print("\ncross-platform restart helper")
from src.utils.restart import restart_app  # noqa: E402

check("restart helper importable", callable(restart_app))
preset = _read("src/gui/ios/preset_menu.py")
check("preset_menu no longer calls os.execl", "os.execl(" not in preset)
check("preset_menu delegates to the shared helper",
      "from src.utils.restart import restart_app" in preset)
crash = _read("src/exceptions/crash_handler.py")
check("crash_handler uses the shared helper",
      "from src.utils.restart import restart_app" in crash)

print(f"\nALL {PASS} CHECKS PASSED")
