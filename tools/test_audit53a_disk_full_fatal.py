#!/usr/bin/env python3
"""Audit 53a: disk-full is fatal — never retried, original error propagates.

Before the fix, ``is_transient_restore_error`` returned True for
NotEnoughDiskSpaceError ("retry after cleanup"), so the Phase 3 loop
(max_retries=18) retried a full disk eighteen times with no cleanup
ever happening, and ``_on_failure`` then wrapped the real cause.

Pinned here:
1. Neither classifier calls disk-full retryable/connection.
2. async_retry driven by the Phase 3 predicate makes exactly ONE
   attempt and re-raises the original NotEnoughDiskSpaceError.
3. The real Phase 3 entry point (stubbed mobilebackup2) also makes
   exactly one attempt and propagates the original error unwrapped.
4. A genuine transient (ConnectionTerminatedError) still retries.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit53a_disk_full_fatal.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication

_app = QCoreApplication.instance() or QCoreApplication([])

from pymobiledevice3.exceptions import (
    ConnectionTerminatedError, NotEnoughDiskSpaceError)

from src.exceptions import device_errors
from src.restore import restore as restore_mod
from src.utils.async_retry import async_retry

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def test_classifiers():
    print("\nAudit 53a: classifiers treat disk-full as fatal")
    err = NotEnoughDiskSpaceError()
    check("is_transient_restore_error(disk-full) is False",
          not device_errors.is_transient_restore_error(err))
    check("is_connection_error(disk-full) is False",
          not device_errors.is_connection_error(err))
    check("transient connection drop still transient",
          device_errors.is_transient_restore_error(
              ConnectionTerminatedError("dropped")))


def test_retry_loop_stops():
    print("\nAudit 53a: retry loop makes one attempt on disk-full")
    attempts = {"n": 0}
    original = NotEnoughDiskSpaceError()

    async def full_disk():
        attempts["n"] += 1
        raise original

    raised = None
    try:
        asyncio.run(async_retry(full_disk, 18, fixed_delay=0,
                                retry_if=device_errors.is_transient_restore_error))
    except NotEnoughDiskSpaceError as e:
        raised = e
    check("original error object propagates", raised is original)
    check("exactly one attempt", attempts["n"] == 1,
          f"attempts={attempts['n']}")

    attempts2 = {"n": 0}

    async def flaky():
        attempts2["n"] += 1
        if attempts2["n"] < 3:
            raise ConnectionTerminatedError("dropped")
        return "ok"

    out = asyncio.run(async_retry(
        flaky, 18, fixed_delay=0,
        retry_if=device_errors.is_transient_restore_error))
    check("transient error still retried to success",
          out == "ok" and attempts2["n"] == 3)


class FakeMB:
    def __init__(self, counter):
        self._counter = counter

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def restore(self, *a, **k):
        self._counter["n"] += 1
        raise NotEnoughDiskSpaceError()


def test_phase3_single_attempt():
    print("\nAudit 53a: Phase 3 does not retry disk-full (was 18x)")
    counter = {"n": 0}
    real = restore_mod._start_mobilebackup2
    restore_mod._start_mobilebackup2 = lambda lc: FakeMB(counter)
    # Stall watchdog inside _restore_once uses real time; the stubbed
    # restore raises instantly, so no stall can trigger.
    raised = None
    try:
        asyncio.run(restore_mod._restore_protective_backup(
            object(), tempfile.mkdtemp(prefix="gn_audit53a_"), "UDID53A",
            False, lambda v: None))
    except NotEnoughDiskSpaceError as e:
        raised = e
    finally:
        restore_mod._start_mobilebackup2 = real
    check("Phase 3 propagates NotEnoughDiskSpaceError unwrapped",
          raised is not None)
    check("Phase 3 attempted the restore exactly once",
          counter["n"] == 1, f"attempts={counter['n']}")


def test_retry_opens_fresh_session():
    print("\nAudit M12: retries open a fresh lockdown session")
    import src.devicemanagement.session as session_mod
    real_ls = session_mod.lockdown_session
    fresh_sessions = {"n": 0}

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *a):
            return False

    def fake_lockdown_session(udid):
        fresh_sessions["n"] += 1
        return FakeSession()

    counter = {"n": 0}

    class FakeMB2(FakeMB):
        async def restore(self, *a, **k):
            counter["n"] += 1
            if counter["n"] == 1:
                raise ConnectionTerminatedError("dropped")
            return None

    real_mb2 = restore_mod._start_mobilebackup2
    restore_mod._start_mobilebackup2 = lambda lc: FakeMB2(counter)
    session_mod.lockdown_session = fake_lockdown_session
    try:
        asyncio.run(restore_mod._restore_protective_backup(
            object(), tempfile.mkdtemp(prefix="gn_auditm12_"), "UDIDM12",
            False, lambda v: None))
    finally:
        restore_mod._start_mobilebackup2 = real_mb2
        session_mod.lockdown_session = real_ls
    check("restore succeeded after one transient failure",
          counter["n"] == 2, f"attempts={counter['n']}")
    check("exactly one fresh session opened (for the retry, not attempt 1)",
          fresh_sessions["n"] == 1, f"fresh={fresh_sessions['n']}")


def main():
    test_classifiers()
    test_retry_loop_stops()
    test_phase3_single_attempt()
    test_retry_opens_fresh_session()
    print(f"\nPASS {PASS} checks")


if __name__ == "__main__":
    main()
