#!/usr/bin/env python3
"""Audit 53b: retry predicates only retry real connection/transient errors.

Before the fix:
* the InstallationProxy query in restore.py called async_retry with NO
  retry_if, so every exception (local file errors, disk-full, logic
  errors) burned all attempts;
* is_connection_error treated bare OSError as a connection error, so a
  local FileNotFoundError/PermissionError on this computer was
  classified (and retried) as if the device had dropped.

Pinned here:
1. is_connection_error: local OSErrors are False; genuine channel
   failures (ConnectionTerminatedError, ConnectionError subclasses,
   timeouts, network-errno OSError, TLS drops) are True.
2. async_retry with retry_if=is_connection_error retries a transient
   failure but makes exactly one attempt on a local error.
3. The InstallationProxy call site in restore.py passes
   retry_if=is_connection_error (source pin — the call needs a device).

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit53b_connection_narrow.py
"""
import asyncio
import errno
import os
import ssl
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pymobiledevice3.exceptions import (
    ConnectionTerminatedError, NotEnoughDiskSpaceError)

from src.exceptions import device_errors
from src.exceptions.device_errors import is_connection_error
from src.utils.async_retry import async_retry

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def test_classifier():
    print("\nAudit 53b: is_connection_error is narrowed")
    check("pm3 ConnectionTerminatedError is a connection error",
          is_connection_error(ConnectionTerminatedError("dropped")))
    for exc in (ConnectionResetError("reset by peer"),
                ConnectionRefusedError("refused"),
                ConnectionAbortedError("aborted"),
                BrokenPipeError("broken pipe"),
                TimeoutError("timed out"),
                asyncio.TimeoutError()):
        check(f"{type(exc).__name__} is a connection error",
              is_connection_error(exc))
    net = OSError(errno.ECONNRESET, "connection reset by socket layer")
    check("bare OSError with network errno is a connection error",
          is_connection_error(net))
    check("TLS drop is a connection error",
          is_connection_error(ssl.SSLError("EOF occurred in violation "
                                             "of protocol")))

    for exc in (FileNotFoundError("pairing file missing"),
                PermissionError("cannot write backup dir"),
                IsADirectoryError("expected a file"),
                NotADirectoryError("bad local path"),
                OSError(errno.ENOSPC, "no space left on device"),
                OSError(errno.ENOENT, "local file gone"),
                NotEnoughDiskSpaceError(),
                ValueError("logic error"),
                KeyError("bundle missing")):
        check(f"{type(exc).__name__} is NOT a connection error",
              not is_connection_error(exc), f"exc={exc!r}")


def test_retry_predicate():
    print("\nAudit 53b: async_retry + is_connection_error predicate")
    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionTerminatedError("dropped")
        return "ok"

    out = asyncio.run(async_retry(flaky, 3, fixed_delay=0,
                                  retry_if=is_connection_error))
    check("transient failure retried to success",
          out == "ok" and attempts["n"] == 3)

    attempts2 = {"n": 0}

    async def local_missing():
        attempts2["n"] += 1
        raise FileNotFoundError("pairing record gone")

    raised = None
    try:
        asyncio.run(async_retry(local_missing, 3, fixed_delay=0,
                                retry_if=is_connection_error))
    except FileNotFoundError as e:
        raised = e
    check("local error propagates on first attempt",
          raised is not None and attempts2["n"] == 1,
          f"attempts={attempts2['n']}")


def test_installation_proxy_call_site():
    print("\nAudit 53b: InstallationProxy call site carries retry_if")
    path = os.path.join(os.path.dirname(__file__), "..",
                        "src", "restore", "restore.py")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    idx = src.find("InstallationProxyService(lockdown=lockdown_client)")
    check("InstallationProxy query present", idx >= 0)
    window = src[idx:idx + 1200]
    check("its async_retry passes retry_if=is_connection_error",
          "retry_if=is_connection_error" in window)


def main():
    test_classifier()
    test_retry_predicate()
    test_installation_proxy_call_site()
    # device_errors module still exposes the classifier used above.
    assert device_errors.is_connection_error is is_connection_error
    print(f"\nPASS {PASS} checks")


if __name__ == "__main__":
    main()
