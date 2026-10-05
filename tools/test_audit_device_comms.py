#!/usr/bin/env python3
"""Round-6 audit: device communication layer contracts.

* stall watchdog forwards progress, returns results, and converts a
  silent device into ConnectionTerminatedError (the retryable class);
* stall-limit resolution never accepts nonsense values;
* async_retry retries only matching errors, with bounded attempts;
* error classification keeps its documented classes.

Run: python tools/test_audit_device_comms.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pymobiledevice3.exceptions import ConnectionTerminatedError

from src.exceptions import device_errors
from src.utils.async_retry import async_retry
from src.utils.stall_watchdog import (
    resolve_stall_seconds, run_with_stall_watchdog)

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-6: device comms")
    check("stall default is 300s", resolve_stall_seconds() == 300.0)
    check("stall explicit wins", resolve_stall_seconds(42) == 42.0)
    check("stall nonsense falls back",
          resolve_stall_seconds(-5) == 300.0
          and resolve_stall_seconds("x") == 300.0)

    seen = []

    async def healthy(cb):
        cb(10.0)
        cb(55.0)
        return "done"

    out = asyncio.run(run_with_stall_watchdog(
        healthy, seen.append, operation="backup", stall_seconds=30))
    check("watchdog returns the wrapped result", out == "done")
    check("watchdog forwards progress verbatim", seen[:2] == [10.0, 55.0])

    async def silent(_cb):
        await asyncio.sleep(5)

    try:
        asyncio.run(run_with_stall_watchdog(
            silent, None, operation="backup", stall_seconds=0.2))
        raised = None
    except ConnectionTerminatedError as exc:
        raised = exc
    check("silent device becomes ConnectionTerminatedError",
          raised is not None)
    check("watchdog error is retry-classified",
          device_errors.is_connection_error(raised))

    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionTerminatedError("dropped")
        return "ok"

    out = asyncio.run(async_retry(flaky, 3, fixed_delay=0))
    check("async_retry recovers a flaky call", out == "ok"
          and attempts["n"] == 3)

    async def fatal():
        raise ValueError("nope")

    try:
        asyncio.run(async_retry(fatal, 3, fixed_delay=0,
                                retry_if=device_errors.is_connection_error))
        raised = None
    except ValueError as exc:
        raised = exc
    check("async_retry does not retry non-matching errors",
          isinstance(raised, ValueError))

    check("locked classification needs ErrorCode context",
          device_errors.is_device_locked_error(
              Exception("MBErrorDomain ErrorCode 208 device locked")))
    check("transient restore: connection drop",
          device_errors.is_transient_restore_error(
              ConnectionTerminatedError("x")))
    check("transient restore: unrelated error stays fatal",
          not device_errors.is_transient_restore_error(
              ValueError("unrelated")))

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
