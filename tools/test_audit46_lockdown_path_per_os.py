#!/usr/bin/env python3
"""Fix Audit 46: the Apple Lockdown folder was hardcoded to Windows.

``pairing.py`` and ``livecontainer.py`` each carried their own
``C:\\ProgramData\\Apple\\Lockdown`` literal, so on macOS/Linux both
looked for usbmux pairing records in a folder that can never exist
there. Both now resolve through the single shared helper
``ipaside_engine.paths.apple_lockdown_dir``:

* Windows keeps ``C:\\ProgramData\\Apple\\Lockdown`` byte-identical;
* macOS resolves to ``~/Library/Lockdown``;
* Linux resolves to ``Path.home()`` (no standard libimobiledevice
  lockdown folder exists there — the home dir is the documented
  fallback, not an invented standard path).

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit46_lockdown_path_per_os.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from src.sideload.ipaside_engine import paths  # noqa: E402
from src.sideload.ipaside_engine import pairing  # noqa: E402

# NOTE: livecontainer is verified by source inspection below, not by
# import — its module chain (provision -> gsa -> ``srp``) needs the
# optional ``srp`` package, which this venv does not carry. That gap
# predates this fix and is unrelated to the lockdown path.

print("\nper-OS resolution through the one shared helper")
check("windows keeps C:\\ProgramData\\Apple\\Lockdown",
      paths.apple_lockdown_dir("win32") == Path(r"C:\ProgramData\Apple\Lockdown"),
      str(paths.apple_lockdown_dir("win32")))
check("macOS resolves to ~/Library/Lockdown",
      paths.apple_lockdown_dir("darwin") == Path.home() / "Library" / "Lockdown",
      str(paths.apple_lockdown_dir("darwin")))
check("linux resolves to Path.home() (no invented standard folder)",
      paths.apple_lockdown_dir("linux") == Path.home(),
      str(paths.apple_lockdown_dir("linux")))
check("default branch follows sys.platform",
      paths.apple_lockdown_dir() == paths.apple_lockdown_dir(sys.platform))

print("\nboth former hardcoded sites now share the helper result")
check("pairing._APPLE_LOCKDOWN_DIR comes from the helper",
      pairing._APPLE_LOCKDOWN_DIR == paths.apple_lockdown_dir())
check("pairing._LOCKDOWN_DIR is the same folder",
      pairing._LOCKDOWN_DIR == pairing._APPLE_LOCKDOWN_DIR)
check("pairing._uses_apple_lockdown still recognises the real folder",
      pairing._uses_apple_lockdown(None) is True)
check("pairing._uses_apple_lockdown rejects a test-double folder",
      pairing._uses_apple_lockdown(Path("/tmp/not-the-lockdown-dir")) is False)

print("\nlivecontainer resolves through the same helper (source-level)")
import inspect  # noqa: E402

lc_source = Path(pairing.__file__).with_name("livecontainer.py").read_text(
    encoding="utf-8")
check("livecontainer._LOCKDOWN_DIR comes from paths.apple_lockdown_dir()",
      "_LOCKDOWN_DIR = paths.apple_lockdown_dir()" in lc_source)
check("pairing._APPLE_LOCKDOWN_DIR comes from paths.apple_lockdown_dir()",
      "_APPLE_LOCKDOWN_DIR = paths.apple_lockdown_dir()"
      in inspect.getsource(pairing))

print("\nno Windows literal survives outside the helper")
for mod, label in ((pairing, "pairing"),):
    src = inspect.getsource(mod)
    check(f"{label}.py carries no C:\\\\ProgramData literal",
          r"C:\ProgramData" not in src)
check("livecontainer.py carries no C:\\ProgramData literal",
      r"C:\ProgramData" not in lc_source)

print(f"\nALL {PASS} CHECKS PASSED")
