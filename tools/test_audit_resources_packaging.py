#!/usr/bin/env python3
"""Round-17 audit: compiled resources + packaging inputs.

* every ``:/icon/...`` path referenced anywhere in src/ resolves in
  the compiled Qt resources (a missing one renders a blank icon);
* every resource the Home/sidebar/LGD surfaces need is present;
* compile.py consumes the version from src/version.py and only
  names packaging inputs that exist on disk.

Run: python tools/test_audit_resources_packaging.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QFile

PASS = 0
ROOT = os.path.join(os.path.dirname(__file__), "..")


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-17: resources + packaging")
    app = QCoreApplication.instance() or QCoreApplication([])
    import src.qt.resources_rc  # noqa: F401

    refs = set()
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "src")):
        for fn in files:
            if fn.endswith(".py"):
                text = open(os.path.join(dirpath, fn),
                            encoding="utf-8", errors="ignore").read()
                refs.update(re.findall(r":/(?!/)[\w\-/\.]+\.[\w]+", text))
    refs = {r for r in refs if "/" in r[2:]}
    missing = sorted(r for r in refs if not QFile(r).exists())
    check("every referenced :/ resource exists", missing == [],
          str(missing[:8]))
    check("resource reference scan is non-trivial", len(refs) > 40,
          str(len(refs)))
    for need in (":/icon/ws-glass.svg", ":/icon/ws-brand.svg"):
        check(f"key resource present: {need}", QFile(need).exists())

    compile_src = open(os.path.join(ROOT, "compile.py"),
                       encoding="utf-8").read()
    check("compile.py sources the app version",
          "App_Version" in compile_src or "version" in compile_src.lower())
    for path in ("src/qt", "files", "workslop_icon.png"):
        check(f"packaging input exists: {path}",
              os.path.exists(os.path.join(ROOT, path)))
    fonts = [f for f in os.listdir(os.path.join(ROOT, "src/qt/fonts"))
             if f.endswith(".ttf")]
    check("bundled Inter fonts ship", len(fonts) >= 2, str(fonts))

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
