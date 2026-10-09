#!/usr/bin/env python3
"""Audit 72: Phase 2 retries must target the SAME device; picker locked.

Before the fix, the iOS 27 Phase 2 cooldown retry called
``perform_restore(lockdown_client=None)``, whose bare
``create_using_usbmux()`` attaches to the FIRST usbmux device — with two
phones plugged in, the retry could restore to the wrong iPhone. The GUI
device picker also stayed live mid-apply.

Pinned here:
1. The retry passes the UDID snapshotted at apply start; the first attempt
   uses the original lockdown client.
2. ``perform_restore`` with ``udid=`` connects via
   ``create_using_usbmux(serial=<udid>)`` (and without it, legacy behaviour).
3. ``toggle_thread_btns`` locks every device picker during an apply and
   unlocks it afterwards.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit72_udid_snapshot_picker.py
"""
import asyncio
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

_app = QApplication.instance() or QApplication([])

from pymobiledevice3.exceptions import ConnectionTerminatedError

import src.restore as restore_pkg
from src.restore import restore as restore_mod

PASS = 0
UDID = "UDID-SNAPSHOT-72"


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


def test_retry_uses_snapshot_udid():
    print("\n_restore_ios27: Phase 2 retry is pinned to the snapshot UDID")
    root = tempfile.mkdtemp(prefix="gn_audit72_")
    prepared = types.SimpleNamespace(
        root=root, manifest_password="", master=False, media_src="")
    lock = FakeLockdown(UDID)
    seen = []

    real_clean = restore_mod.clean_backup_for_restore
    real_verify = restore_mod.verify_backup_payloads
    real_restore = restore_mod.perform_restore
    real_phase3 = restore_mod._restore_protective_backup
    real_skip = restore_mod.skip_all_setup27
    real_sleep = asyncio.sleep

    restore_mod.clean_backup_for_restore = lambda *a, **k: (0, 0)
    restore_mod.verify_backup_payloads = lambda *a, **k: []

    async def fake_restore(**kwargs):
        seen.append(kwargs)
        if len(seen) == 1:
            raise ConnectionTerminatedError("dropped at 0% — cooldown retry")

    async def fake_phase3(*a, **k):
        pass

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
            types.SimpleNamespace(files=[object()]), False, lock,
            lambda v: None, prepared_backup_root=prepared, inject_files=[]))
    finally:
        restore_mod.clean_backup_for_restore = real_clean
        restore_mod.verify_backup_payloads = real_verify
        restore_mod.perform_restore = real_restore
        restore_mod._restore_protective_backup = real_phase3
        restore_mod.skip_all_setup27 = real_skip
        asyncio.sleep = real_sleep

    check("two sparse attempts happened", len(seen) == 2, f"calls={len(seen)}")
    check("first attempt used the original lockdown client",
          seen[0].get("lockdown_client") is lock)
    check("retry opened a fresh client (lockdown_client=None)",
          seen[1].get("lockdown_client") is None)
    check("retry pinned to the snapshot UDID",
          seen[1].get("udid") == UDID, f"udid={seen[1].get('udid')!r}")
    check("first attempt also carried the snapshot UDID",
          seen[0].get("udid") == UDID)


def test_perform_restore_connects_by_udid():
    print("\nperform_restore: own client is created for the given UDID")
    created = []

    async def fake_create(*args, **kwargs):
        created.append(kwargs.get("serial"))
        return FakeLockdown(kwargs.get("serial") or "first-device")

    class FakeMB2:
        def __init__(self, lc):
            self.lc = lc

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def restore(self, *a, **k):
            return None

    class FakeBackup:
        def write_to_directory(self, path):
            pass

    real_create = restore_pkg.create_using_usbmux
    real_mb2 = restore_pkg.Mobilebackup2Service
    restore_pkg.create_using_usbmux = fake_create
    restore_pkg.Mobilebackup2Service = FakeMB2
    try:
        asyncio.run(restore_pkg.perform_restore(
            backup=FakeBackup(), reboot=False, lockdown_client=None,
            udid=UDID))
        asyncio.run(restore_pkg.perform_restore(
            backup=FakeBackup(), reboot=False, lockdown_client=None))
    finally:
        restore_pkg.create_using_usbmux = real_create
        restore_pkg.Mobilebackup2Service = real_mb2

    check("udid given -> create_using_usbmux(serial=UDID)",
          created[0] == UDID, f"created={created}")
    check("no udid -> legacy first-device behaviour", created[1] is None)


def test_picker_locked_during_apply():
    print("\ntoggle_thread_btns: device pickers lock for the whole apply")
    from src.gui.main_window_mixins import ApplyMixin

    win = object.__new__(ApplyMixin)
    win.apply_in_progress = True
    win.refresh_in_progress = False
    win._ios_page_objs = {}
    win._pending_apply_busy = None
    win.ui = types.SimpleNamespace(
        refreshBtn=QPushButton(), devicePicker=QComboBox())
    win.device_panel = types.SimpleNamespace(device_combo=QComboBox())
    win.ios_home = types.SimpleNamespace(device_combo=QComboBox())

    pickers = [win.ui.devicePicker, win.device_panel.device_combo,
               win.ios_home.device_combo]
    win.toggle_thread_btns(disabled=True)
    check("all device pickers disabled while applying",
          all(not p.isEnabled() for p in pickers))
    win.apply_in_progress = False
    win.toggle_thread_btns(disabled=False)
    check("all device pickers re-enabled after the apply",
          all(p.isEnabled() for p in pickers))


def main():
    test_retry_uses_snapshot_udid()
    test_perform_restore_connects_by_udid()
    test_picker_locked_during_apply()
    print(f"\nPASS {PASS} checks")


if __name__ == "__main__":
    main()
