#!/usr/bin/env python3
"""Round-16 audit: settings persistence + translator fallback.

* Settings values round-trip through the real store;
* the Translator loads the bundled Indonesian catalog (or degrades
  to source strings, never crashes) for an unknown locale;
* no f-string translation ghosts exist in the source (they can
  never match at runtime — repo house rule).

Run: python tools/test_audit_i18n_settings.py
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-r16-")

from PySide6.QtWidgets import QApplication

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-16: i18n + settings")
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("WorkSlop Desktop")

    from src.controllers.settings import Settings
    s = Settings("settings")
    s.setValue("audit_round16", "halo")
    check("settings round-trip", s.value("audit_round16") == "halo")
    s.setValue("audit_round16_num", 12)
    check("settings typed round-trip",
          s.value("audit_round16_num", 0, type=int) == 12)

    from src.controllers.translator import Translator
    tr = Translator(app, s)
    tr.load_translations()
    from PySide6.QtCore import QCoreApplication
    out = QCoreApplication.translate("Nugget", "Apply Tweaks")
    check("translator returns text for known/unknown strings",
          isinstance(out, str) and bool(out))
    out2 = QCoreApplication.translate(
        "Nugget", "ZZZ_STRING_THAT_CANNOT_EXIST_9F3K")
    check("unknown string falls back to itself",
          out2 == "ZZZ_STRING_THAT_CANNOT_EXIST_9F3K")

    ghosts = []
    root = os.path.join(os.path.dirname(__file__), "..", "src")
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn.endswith(".py"):
                text = open(os.path.join(dirpath, fn),
                            encoding="utf-8", errors="ignore").read()
                if re.search(r"""\btr\(\s*f["']""", text) or \
                        re.search(r"""translate\([^)]*f["']""", text):
                    ghosts.append(fn)
    check("no f-string translation ghosts", ghosts == [], str(ghosts))

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
