#!/usr/bin/env python3
"""Audit 71: a disk-full protective backup must fail honestly.

Before the fix, ``perform_protective_backup`` swallowed
``NotEnoughDiskSpaceError`` ("ignoring, backup data is preserved"), so an
incomplete backup was announced as "Protective Backup Complete" and the
iOS 27 Phase 1 in restore.py only *logged* manifest rows whose payloads
were missing before marching on to the wipe/restore.

Pinned here:
1. ``NotEnoughDiskSpaceError`` propagates out of
   ``perform_protective_backup`` (a healthy backup still returns normally).
2. Phase 1 of ``_restore_ios27`` aborts with ``NuggetException`` when the
   backup manifest promises payloads that are missing on disk — before any
   restore touches the device.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit71_disk_full_honest.py
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

from pymobiledevice3.exceptions import NotEnoughDiskSpaceError

from src.exceptions.nugget_exception import NuggetException
from src.restore import protective
from src.restore import restore as restore_mod

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


# --- stubs for perform_protective_backup -------------------------------------

class FakeBackupService:
    """Stand-in for ProtectiveBackupService (mobilebackup2 surface only)."""

    def __init__(self, lockdown_client, include_posterboard=False, fail=False):
        self._fail = fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get_will_encrypt(self):
        return False

    async def backup(self, **kwargs):
        if self._fail:
            raise NotEnoughDiskSpaceError()
        kwargs["progress_callback"](50.0)
        return None


async def _passthrough_watchdog(factory, progress_callback, operation="backup"):
    return await factory(lambda *a, **k: None)


def run_backup(fail):
    real_svc = protective.ProtectiveBackupService
    real_wd = protective.run_with_stall_watchdog
    protective.ProtectiveBackupService = (
        lambda lc, include_posterboard=False: FakeBackupService(
            lc, include_posterboard, fail=fail))
    protective.run_with_stall_watchdog = _passthrough_watchdog
    try:
        return asyncio.run(protective.perform_protective_backup(
            object(), tempfile.mkdtemp(prefix="gn_audit71_"),
            progress_callback=lambda v: None,
            include_photos=True, include_keychain=None,
            include_afc_media=False))
    finally:
        protective.ProtectiveBackupService = real_svc
        protective.run_with_stall_watchdog = real_wd


def test_disk_full_propagates():
    print("\nperform_protective_backup: disk-full is not swallowed")
    raised = None
    try:
        run_backup(fail=True)
    except NotEnoughDiskSpaceError as e:
        raised = e
    check("NotEnoughDiskSpaceError propagates to the caller", raised is not None)

    result = run_backup(fail=False)
    check("healthy backup still completes", result is False,
          f"is_encrypted={result}")


# --- stubs for _restore_ios27 Phase 1 ----------------------------------------

class FakeLockdown:
    def __init__(self, udid):
        self.udid = udid

    async def close(self):
        pass


def run_ios27(missing):
    root = tempfile.mkdtemp(prefix="gn_audit71_p1_")
    prepared = types.SimpleNamespace(
        root=root, manifest_password="", master=False, media_src="")
    calls = {"restore": 0, "phase3": 0}

    real_clean = restore_mod.clean_backup_for_restore
    real_verify = restore_mod.verify_backup_payloads
    real_restore = restore_mod.perform_restore
    real_phase3 = restore_mod._restore_protective_backup
    restore_mod.clean_backup_for_restore = lambda *a, **k: (0, 0)
    restore_mod.verify_backup_payloads = lambda *a, **k: list(missing)

    async def fake_restore(**kwargs):
        calls["restore"] += 1

    async def fake_phase3(*a, **k):
        calls["phase3"] += 1

    restore_mod.perform_restore = fake_restore
    restore_mod._restore_protective_backup = fake_phase3
    try:
        asyncio.run(restore_mod._restore_ios27(
            types.SimpleNamespace(files=[object()]), False,
            FakeLockdown("UDID-AUDIT71"), lambda v: None,
            prepared_backup_root=prepared, inject_files=[]))
    finally:
        restore_mod.clean_backup_for_restore = real_clean
        restore_mod.verify_backup_payloads = real_verify
        restore_mod.perform_restore = real_restore
        restore_mod._restore_protective_backup = real_phase3
    return calls


def test_phase1_missing_payload_aborts():
    print("\n_restore_ios27 Phase 1: missing promised payloads abort the apply")
    raised = None
    try:
        calls = run_ios27(missing=["deadbeef001"])
    except NuggetException as e:
        raised = e
        calls = {"restore": -1, "phase3": -1}
    check("NuggetException raised for missing payloads", raised is not None)
    check("error names the incompleteness",
          raised is not None and "incomplete" in str(raised).lower())
    check("no device restore was attempted", calls["restore"] <= 0)


def main():
    test_disk_full_propagates()
    test_phase1_missing_payload_aborts()
    print(f"\nPASS {PASS} checks")


if __name__ == "__main__":
    main()
