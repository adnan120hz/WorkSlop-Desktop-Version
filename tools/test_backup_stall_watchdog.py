#!/usr/bin/env python3
"""Offline test for the mobilebackup2 stall watchdog (no device needed).

Proves, per backup/restore path, that a device which stops reporting
progress no longer hangs the operation forever ("stuck at 84%"): with a
small ``WORKSLOP_BACKUP_STALL_SECONDS`` the wrapped call aborts fast with
``ConnectionTerminatedError`` (which the existing retry machinery treats as
a retryable connection error), and a device that keeps reporting progress
completes normally.

Covered paths:
  1. the watchdog helper itself (incl. heartbeat re-emit + progress resets)
  2. perform_protective_backup        (src/restore/protective.py)
  3. backup_posterboard_database      (src/restore/posterboard_backup.py)
  4. targeted_posterboard_database_backup (same module)
  5. targeted_app_domain_backup       (src/restore/appdomain_backup.py)
  6. perform_restore                  (src/restore/__init__.py)

Run: python tools/test_backup_stall_watchdog.py
"""
import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pymobiledevice3.exceptions import ConnectionTerminatedError

import src.restore as restore_pkg
from src.restore import appdomain_backup, posterboard_backup, protective
from src.utils.async_retry import async_retry as _real_async_retry
from src.utils.stall_watchdog import resolve_stall_seconds, run_with_stall_watchdog

PASS = 0
TMP = tempfile.mkdtemp(prefix="workslop_stall_")
UDID = "00008101-STALLTEST"

# Small stall limit so a wedged fake aborts in ~0.2s instead of hanging;
# GOLDENNUGGET_BACKUP_DIR keeps every on-disk artifact inside TMP.
os.environ["WORKSLOP_BACKUP_STALL_SECONDS"] = "0.2"
os.environ["GOLDENNUGGET_BACKUP_DIR"] = TMP


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


# --- duck-typed device/service stubs ----------------------------------------

class FakeProvider:
    """Lockdown-client stand-in (only what the call sites touch)."""
    udid = UDID
    all_values = {"BuildVersion": "23G83"}


class FakeMB:
    """Mobilebackup2Service stand-in.

    ``mode == "stall"``    -> never reports progress, hangs forever
                              (until the watchdog cancels it).
    ``mode == "progress"`` -> reports 10/50/100 then optionally builds
                              on-disk artifacts via ``payload_builder``.
    """
    mode = "progress"
    calls = []
    payload_builder = None

    def __init__(self, lockdown=None, *args, **kwargs):
        self.lockdown = lockdown

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_will_encrypt(self):
        return False

    async def _behave(self, kind, kwargs):
        type(self).calls.append((kind, kwargs))
        cb = kwargs.get("progress_callback")
        if self.mode == "stall":
            await asyncio.Event().wait()  # wedged device: silence forever
            return
        if cb is not None:
            for pct in (10, 50, 100):
                cb(pct)
                await asyncio.sleep(0.01)
        builder = type(self).payload_builder
        if builder is not None:
            builder(kwargs.get("backup_directory"))

    async def backup(self, **kwargs):
        await self._behave("backup", kwargs)

    async def restore(self, *args, **kwargs):
        await self._behave("restore", kwargs)


@asynccontextmanager
async def _fake_lockdown_session(serial=None, **kwargs):
    yield FakeProvider()


async def _fake_check_disk(*args, **kwargs):
    return 0


async def _fast_retry(coro_factory, attempts, **kwargs):
    """async_retry with the production backoff flattened for the test."""
    kwargs["fixed_delay"] = 0
    return await _real_async_retry(coro_factory, attempts, **kwargs)


class StubBackup:
    """perform_restore's ``backup`` argument (write_to_directory duck type)."""

    def write_to_directory(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)
        (Path(path) / "Manifest.plist").write_bytes(b"stub")


def _reset_fake(mode, payload_builder=None):
    FakeMB.mode = mode
    FakeMB.calls = []
    FakeMB.payload_builder = payload_builder


def _make_sqlite_db(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()


_PB_REL = ("AppDomain-com.apple.PosterBoard/Library/PosterBoard/"
           "PRBPosterExtensionDataStore/62/"
           "PBFPosterExtensionDataStoreSQLiteDatabase.sqlite3")
_PB_FILE_ID = "a" * 40


def _write_pb_manifest(backup_directory):
    """Emulate a finished PosterBoard-carrying backup on disk."""
    device_dir = Path(backup_directory) / UDID
    device_dir.mkdir(parents=True, exist_ok=True)
    manifest = device_dir / "Manifest.db"
    conn = sqlite3.connect(str(manifest))
    conn.execute("CREATE TABLE Files (fileID TEXT, relativePath TEXT)")
    conn.execute("INSERT INTO Files VALUES (?, ?)", (_PB_FILE_ID, _PB_REL))
    conn.commit()
    conn.close()
    # pad past the 100-byte sqlite validity floor if needed
    if manifest.stat().st_size < 100:
        with open(manifest, "ab") as fh:
            fh.write(b"\0" * 128)
    _make_sqlite_db(device_dir / _PB_FILE_ID[:2] / _PB_FILE_ID)


async def _expect_stall(name, coro_factory, budget=5.0):
    """Run coro_factory(); assert it aborts fast with the watchdog error."""
    start = time.monotonic()
    err = None
    try:
        await coro_factory()
    except ConnectionTerminatedError as e:
        err = e
    elapsed = time.monotonic() - start
    check(f"{name}: stalls abort with ConnectionTerminatedError",
          err is not None, f"err={err!r}")
    check(f"{name}: message explains the stall",
          err is not None and "stopped reporting" in str(err)
          and "fresh connection" in str(err), str(err))
    check(f"{name}: aborts fast instead of hanging",
          elapsed < budget, f"{elapsed:.2f}s")


# --- 1. the helper itself ----------------------------------------------------

def test_helper():
    print("== stall watchdog helper ==")
    check("env stall limit is honoured", resolve_stall_seconds() == 0.2)
    check("explicit stall limit wins", resolve_stall_seconds(1.5) == 1.5)

    async def stall_run():
        seen = []

        async def wedged(cb):
            cb(7)  # one report, then silence
            await asyncio.Event().wait()

        start = time.monotonic()
        err = None
        try:
            await run_with_stall_watchdog(wedged, seen.append, operation="backup")
        except ConnectionTerminatedError as e:
            err = e
        elapsed = time.monotonic() - start
        check("helper: one-report-then-silent aborts", err is not None)
        check("helper: abort is fast", elapsed < 5.0, f"{elapsed:.2f}s")
        check("helper: heartbeat re-emitted the last progress",
              seen.count(7) >= 2, f"seen={seen}")

    asyncio.run(stall_run())

    async def progress_run():
        seen = []

        async def lively(cb):
            # Reports every 50ms for ~0.5s: longer than the 0.2s stall
            # limit, so it only survives if progress resets the timer.
            for pct in range(0, 101, 10):
                cb(pct)
                await asyncio.sleep(0.05)
            return "done"

        result = await run_with_stall_watchdog(lively, seen.append,
                                               operation="backup")
        check("helper: steady progress completes past the stall limit",
              result == "done")
        check("helper: progress forwarded verbatim",
              seen[0] == 0 and seen[-1] == 100, f"seen={seen[:3]}...{seen[-2:]}")

    asyncio.run(progress_run())


# --- 2. perform_protective_backup -------------------------------------------

def test_protective():
    print("== perform_protective_backup ==")
    real_svc = protective.ProtectiveBackupService
    protective.ProtectiveBackupService = FakeMB
    try:
        _reset_fake("stall")
        seen = []
        asyncio.run(_expect_stall(
            "protective",
            lambda: protective.perform_protective_backup(
                FakeProvider(), os.path.join(TMP, "prot_stall"),
                progress_callback=seen.append)))

        _reset_fake("progress")
        seen = []
        result = asyncio.run(protective.perform_protective_backup(
            FakeProvider(), os.path.join(TMP, "prot_ok"),
            progress_callback=seen.append))
        check("protective: progressing backup completes", result is False)
        check("protective: progress reached the caller", 100 in seen,
              f"seen={seen}")
    finally:
        protective.ProtectiveBackupService = real_svc


# --- 3+4. posterboard backups -------------------------------------------------

def _patch_posterboard():
    saved = (posterboard_backup.Mobilebackup2Service,
             posterboard_backup.lockdown_session,
             posterboard_backup.check_disk_space_for_backup,
             posterboard_backup.is_build_supported,
             posterboard_backup.async_retry)
    posterboard_backup.Mobilebackup2Service = FakeMB
    posterboard_backup.lockdown_session = _fake_lockdown_session
    posterboard_backup.check_disk_space_for_backup = _fake_check_disk
    posterboard_backup.is_build_supported = lambda build: True
    posterboard_backup.async_retry = _fast_retry
    return saved


def _restore_posterboard(saved):
    (posterboard_backup.Mobilebackup2Service,
     posterboard_backup.lockdown_session,
     posterboard_backup.check_disk_space_for_backup,
     posterboard_backup.is_build_supported,
     posterboard_backup.async_retry) = saved


def test_posterboard_legacy():
    print("== backup_posterboard_database ==")
    saved = _patch_posterboard()
    try:
        _reset_fake("stall")
        asyncio.run(_expect_stall(
            "posterboard legacy",
            lambda: posterboard_backup.backup_posterboard_database(
                UDID, update_label=lambda x: None,
                update_progress=lambda x: None)))

        _reset_fake("progress", _write_pb_manifest)
        result = asyncio.run(posterboard_backup.backup_posterboard_database(
            UDID, update_label=lambda x: None, update_progress=lambda x: None))
        check("posterboard legacy: progressing backup completes",
              bool(result) and os.path.exists(result), str(result))
    finally:
        _restore_posterboard(saved)


def test_posterboard_targeted():
    print("== targeted_posterboard_database_backup ==")
    saved = _patch_posterboard()
    try:
        _reset_fake("stall")
        asyncio.run(_expect_stall(
            "posterboard targeted",
            lambda: posterboard_backup.targeted_posterboard_database_backup(
                UDID, update_label=lambda x: None,
                update_progress=lambda x: None)))

        _reset_fake("progress", _write_pb_manifest)
        result, version = asyncio.run(
            posterboard_backup.targeted_posterboard_database_backup(
                UDID, update_label=lambda x: None,
                update_progress=lambda x: None))
        check("posterboard targeted: progressing backup completes",
              bool(result) and os.path.exists(result), str(result))
        check("posterboard targeted: structure version parsed",
              version == 62, str(version))
    finally:
        _restore_posterboard(saved)


# --- 5. targeted app-domain backup -------------------------------------------

def test_appdomain():
    print("== targeted_app_domain_backup ==")
    saved = (appdomain_backup.Mobilebackup2Service,
             appdomain_backup.lockdown_session,
             appdomain_backup.async_retry)
    appdomain_backup.Mobilebackup2Service = FakeMB
    appdomain_backup.lockdown_session = _fake_lockdown_session
    appdomain_backup.async_retry = _fast_retry
    try:
        _reset_fake("stall")
        asyncio.run(_expect_stall(
            "app domain",
            lambda: appdomain_backup.targeted_app_domain_backup(
                UDID, "com.example.app", update_label=lambda x: None,
                update_progress=lambda x: None)))

        _reset_fake("progress")
        result = asyncio.run(appdomain_backup.targeted_app_domain_backup(
            UDID, "com.example.app", update_label=lambda x: None,
            update_progress=lambda x: None))
        check("app domain: progressing backup completes",
              bool(result) and os.path.isdir(result), str(result))
        if result:
            shutil.rmtree(result, ignore_errors=True)
    finally:
        (appdomain_backup.Mobilebackup2Service,
         appdomain_backup.lockdown_session,
         appdomain_backup.async_retry) = saved


# --- 6. perform_restore -------------------------------------------------------

def test_perform_restore():
    print("== perform_restore ==")
    real_svc = restore_pkg.Mobilebackup2Service
    restore_pkg.Mobilebackup2Service = FakeMB
    try:
        _reset_fake("stall")
        seen = []
        asyncio.run(_expect_stall(
            "sparse restore",
            lambda: restore_pkg.perform_restore(
                StubBackup(), reboot=False, lockdown_client=FakeProvider(),
                progress_callback=seen.append)))

        _reset_fake("progress")
        seen = []
        asyncio.run(restore_pkg.perform_restore(
            StubBackup(), reboot=False, lockdown_client=FakeProvider(),
            progress_callback=seen.append))
        check("sparse restore: progressing restore completes", 100 in seen,
              f"seen={seen}")
    finally:
        restore_pkg.Mobilebackup2Service = real_svc


def main():
    test_helper()
    test_protective()
    test_posterboard_legacy()
    test_posterboard_targeted()
    test_appdomain()
    test_perform_restore()
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
