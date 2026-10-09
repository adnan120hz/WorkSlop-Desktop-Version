#!/usr/bin/env python3
"""Audit 41: an iOS 27 Phase 2 rejection must fail the apply honestly.

Before the fix, a sparse restore dropped with ZERO progress on every
attempt (i.e. the device rejected it — no tweak landed) was only logged
("tweaks are NOT applied") and the flow sailed on through Phase 3 to a
final "iOS 27 restore completed successfully".

Pinned here:
1. Zero-progress rejection on all attempts -> ``NuggetException`` reaches
   the caller; Phase 3 never runs; no final 100% "success" progress.
2. A clean Phase 2 still completes the whole flow (control).
3. A drop *after* real progress (the expected reboot signature) still
   completes — that behaviour is untouched.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit41_phase2_reject_honest.py
"""
import asyncio
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication

_app = QCoreApplication.instance() or QCoreApplication([])

from pymobiledevice3.exceptions import ConnectionTerminatedError

from src.exceptions.nugget_exception import NuggetException
from src.restore import restore as restore_mod

PASS = 0
UDID = "UDID-AUDIT41"


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


class FakeLockdown:
    def __init__(self, udid):
        self.udid = udid

    async def close(self):
        pass


def run_ios27(perform_restore_impl):
    root = tempfile.mkdtemp(prefix="gn_audit41_")
    prepared = types.SimpleNamespace(
        root=root, manifest_password="", master=False, media_src="")
    calls = {"restore": [], "phase3": 0}
    progress = []

    real_clean = restore_mod.clean_backup_for_restore
    real_verify = restore_mod.verify_backup_payloads
    real_restore = restore_mod.perform_restore
    real_phase3 = restore_mod._restore_protective_backup
    real_skip = restore_mod.skip_all_setup27
    real_sleep = asyncio.sleep

    restore_mod.clean_backup_for_restore = lambda *a, **k: (0, 0)
    restore_mod.verify_backup_payloads = lambda *a, **k: []

    async def fake_restore(**kwargs):
        calls["restore"].append(kwargs)
        await perform_restore_impl(kwargs)

    async def fake_phase3(*a, **k):
        calls["phase3"] += 1

    async def fake_skip(*a, **k):
        pass

    async def fast_sleep(seconds):
        await real_sleep(0)

    restore_mod.perform_restore = fake_restore
    restore_mod._restore_protective_backup = fake_phase3
    restore_mod.skip_all_setup27 = fake_skip
    asyncio.sleep = fast_sleep
    try:
        asyncio.run(restore_mod._restore_ios27(
            types.SimpleNamespace(files=[object()]), False,
            FakeLockdown(UDID), progress.append,
            prepared_backup_root=prepared, inject_files=[]))
    finally:
        restore_mod.clean_backup_for_restore = real_clean
        restore_mod.verify_backup_payloads = real_verify
        restore_mod.perform_restore = real_restore
        restore_mod._restore_protective_backup = real_phase3
        restore_mod.skip_all_setup27 = real_skip
        asyncio.sleep = real_sleep
    return calls, progress


def test_zero_progress_rejection_fails():
    print("\nPhase 2: zero-progress rejection on every attempt fails the apply")

    async def reject(kwargs):
        raise ConnectionTerminatedError("device dropped at 0%")

    raised = None
    try:
        calls, progress = run_ios27(reject)
    except NuggetException as e:
        raised = e
        calls, progress = {"restore": [1, 2], "phase3": 0}, []
    check("NuggetException reaches the caller", raised is not None)
    check("error says no tweaks were applied",
          raised is not None and "no tweaks were applied" in str(raised))
    check("both sparse attempts were made first", len(calls["restore"]) == 2)
    check("Phase 3 protective restore never ran", calls["phase3"] == 0)
    check("no final 100% success progress emitted", 100 not in progress)


def test_clean_phase2_completes():
    print("\nPhase 2: a clean sparse restore still completes (control)")

    async def ok(kwargs):
        kwargs["progress_callback"](42.0)

    calls, progress = run_ios27(ok)
    check("flow completed without raising", True)
    check("Phase 3 protective restore ran", calls["phase3"] == 1)
    check("final 100% progress emitted", 100 in progress)


def test_progress_drop_still_completes():
    print("\nPhase 2: drop after real progress (reboot signature) still completes")

    async def drop_after_progress(kwargs):
        kwargs["progress_callback"](55.0)
        raise ConnectionTerminatedError("device rebooted mid-restore")

    calls, progress = run_ios27(drop_after_progress)
    check("flow completed without raising", True)
    check("Phase 3 protective restore ran", calls["phase3"] == 1)


def main():
    test_zero_progress_rejection_fails()
    test_clean_phase2_completes()
    test_progress_drop_still_completes()
    print(f"\nPASS {PASS} checks")


if __name__ == "__main__":
    main()
