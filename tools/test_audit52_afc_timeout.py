#!/usr/bin/env python3
"""Audit 52: AFC per-file transfers must not hang an apply forever.

Before the fix, every AFC request on the apply/restore path
(``_pull_one``/``_push_one`` in afc_media.py, plus the list/stat calls
around them) was awaited with no timeout at all — pymobiledevice3's AFC
receive loop only exits when the device speaks, so a wedged device hung
the apply forever on one file.

Pinned here (with the timeout shrunk to 0.2s):
1. A hanging streamed pull (fread never answers) fails with
   ``NuggetException`` instead of hanging, and leaves no ``.part`` behind.
2. A hanging small-file pull (get_file_contents) fails the same way.
3. A hanging push (set_file_contents) fails the same way.
4. A healthy device still transfers fine (control).

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit52_afc_timeout.py
"""
import asyncio
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pymobiledevice3.services.afc import MAXIMUM_READ_SIZE

from src.exceptions.nugget_exception import NuggetException
from src.restore import afc_media
from src.restore.afc_media import _pull_one, _push_one

PASS = 0
TMP = tempfile.mkdtemp(prefix="gn_audit52_")


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


class HangAfc:
    """AFC stand-in whose data requests never answer (wedged device)."""

    def __init__(self, hang_on):
        self.hang_on = hang_on
        self._pos = {}

    async def _maybe_hang(self, op):
        if op == self.hang_on:
            await asyncio.sleep(3600)

    async def get_file_contents(self, path):
        await self._maybe_hang("get_file_contents")
        return b"data"

    async def fopen(self, path, mode="r"):
        self._pos[path] = 0
        return path

    async def fread(self, handle, size):
        await self._maybe_hang("fread")
        return b"x" * size

    async def fwrite(self, handle, chunk):
        await self._maybe_hang("fwrite")

    async def fclose(self, handle):
        pass

    async def set_file_contents(self, path, data):
        await self._maybe_hang("set_file_contents")

    async def stat(self, path):
        return {"st_size": 4, "st_ifmt": "S_IFREG"}


class GoodAfc:
    def __init__(self, files):
        self.files = dict(files)
        self.written = {}
        self._pos = {}

    async def get_file_contents(self, path):
        return self.files[path]

    async def fopen(self, path, mode="r"):
        self._pos[path] = 0
        return path

    async def fread(self, handle, size):
        start = self._pos.get(handle, 0)
        chunk = self.files[handle][start:start + size]
        self._pos[handle] = start + len(chunk)
        return chunk

    async def fwrite(self, handle, chunk):
        self.written[handle] = self.written.get(handle, b"") + chunk

    async def fclose(self, handle):
        pass

    async def set_file_contents(self, path, data):
        self.written[path] = data

    async def stat(self, path):
        if path in self.written:
            return {"st_size": len(self.written[path]), "st_ifmt": "S_IFREG"}
        return {"st_size": len(self.files[path]), "st_ifmt": "S_IFREG"}


def expect_timeout(name, coro_factory, budget=5.0):
    started = time.monotonic()
    raised = None
    try:
        asyncio.run(coro_factory())
    except NuggetException as e:
        raised = e
    elapsed = time.monotonic() - started
    check(f"{name}: NuggetException instead of hanging forever",
          raised is not None and "no response" in str(raised),
          f"elapsed={elapsed:.1f}s")
    check(f"{name}: failed fast", elapsed < budget, f"elapsed={elapsed:.1f}s")
    return raised


def main():
    real_timeout = afc_media._AFC_FILE_TIMEOUT_SECONDS
    afc_media._AFC_FILE_TIMEOUT_SECONDS = 0.2
    try:
        print("\nhanging AFC requests are bounded per file")

        dst = os.path.join(TMP, "big.MOV")
        big_stat = {"st_size": MAXIMUM_READ_SIZE + 100, "st_ifmt": "S_IFREG"}
        expect_timeout(
            "streamed pull (fread hangs)",
            lambda: _pull_one(HangAfc("fread"), "/DCIM/big.MOV", dst, big_stat))
        check("streamed pull left no .part behind",
              not os.path.exists(dst + ".part"))

        small_stat = {"st_size": 4, "st_ifmt": "S_IFREG"}
        expect_timeout(
            "small pull (get_file_contents hangs)",
            lambda: _pull_one(HangAfc("get_file_contents"),
                              "/DCIM/small.JPG",
                              os.path.join(TMP, "small.JPG"), small_stat))

        src = os.path.join(TMP, "push.JPG")
        with open(src, "wb") as f:
            f.write(b"jpeg")
        expect_timeout(
            "small push (set_file_contents hangs)",
            lambda: _push_one(HangAfc("set_file_contents"), src, "/DCIM/push.JPG"))
    finally:
        afc_media._AFC_FILE_TIMEOUT_SECONDS = real_timeout

    print("\nhealthy AFC transfers still work (control)")
    payload = b"hello-photos"
    dst = os.path.join(TMP, "ok.JPG")
    n = asyncio.run(_pull_one(GoodAfc({"/DCIM/ok.JPG": payload}),
                              "/DCIM/ok.JPG", dst,
                              {"st_size": len(payload), "st_ifmt": "S_IFREG"}))
    with open(dst, "rb") as f:
        landed = f.read()
    check("pull returned and wrote the bytes", n == len(payload) and landed == payload)

    print(f"\nPASS {PASS} checks")


if __name__ == "__main__":
    main()
