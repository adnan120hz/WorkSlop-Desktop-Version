#!/usr/bin/env python3
"""Audit 69+80: AGPL-3.0 LICENSE bundled in builds + shown in About.

* the repo LICENSE is the full AGPL-3.0 text;
* compile.py (the single bundling decision point used by every CI
  workflow) bundles LICENSE into the build artifact, and the CI
  workflows upload the whole dist tree so the file ships;
* the About dialog carries the AGPL-3.0 license summary, points to
  the bundled LICENSE file for the full text, and keeps the credit
  order: Adnan.120hz first -> GoldenNugget -> Nugget/leminlimez
  ("UI reference: Nugget UI") -> catwithabaloon icon pack.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_license_bundled_about.py
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-license-")

ROOT = os.path.join(os.path.dirname(__file__), "..")
PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def main():
    print("\n audit 69+80: LICENSE bundled + About license")

    # --- the license itself -------------------------------------------------
    license_path = os.path.join(ROOT, "LICENSE")
    check("repo LICENSE exists", os.path.isfile(license_path))
    license_text = read("LICENSE")
    check("LICENSE is the full AGPL-3.0 text",
          "GNU AFFERO GENERAL PUBLIC LICENSE" in license_text
          and "Version 3, 19 November 2007" in license_text
          and "Free Software Foundation" in license_text)
    check("LICENSE is the complete text, not a stub", len(license_text) > 30000,
          f"{len(license_text)} bytes")

    # --- bundling ------------------------------------------------------------
    compile_src = read("compile.py")
    check("compile.py bundles LICENSE via --add-data",
          re.search(r"--add-data=LICENSE\b", compile_src) is not None)
    check("LICENSE lands at the bundle root",
          re.search(r"--add-data=LICENSE.+[:;]\.", compile_src) is not None)
    for wf in (".github/workflows/build.yml", ".github/workflows/build-windows.yml"):
        wf_src = read(wf)
        check(f"{wf} builds via compile.py and uploads the dist tree",
              "compile.py" in wf_src and "dist/WorkSlopDesktop" in wf_src)

    # --- About dialog ----------------------------------------------------------
    from PySide6.QtWidgets import QApplication, QLabel, QToolButton
    try:
        import src.qt.resources_rc  # noqa: F401
    except Exception:
        pass
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("WorkSlop Desktop")

    from src.gui.dialogs.dialogs import AboutProgramDialog
    about = AboutProgramDialog()
    label_texts = [w.text() for w in about.findChildren(QLabel)]
    button_texts = [w.text() for w in about.findChildren(QToolButton)]
    all_texts = label_texts + button_texts

    check("About names the AGPL-3.0 license",
          any("AGPL-3.0" in t and "Affero General Public License" in t
              for t in label_texts))
    check("About points to the bundled LICENSE file for the full text",
          any("LICENSE file" in t and "bundled" in t for t in label_texts))
    check("About gives the canonical full-text URL",
          any("gnu.org/licenses/agpl-3.0" in t for t in label_texts))
    check("About keeps the Nugget UI reference",
          any("UI reference: Nugget UI" in t for t in label_texts))

    # Credit order (creation order of the credit rows): the WorkSlop
    # developer first, then the fork lineage, icon pack last.
    def idx(name):
        return button_texts.index(name) if name in button_texts else -1
    order = ["Adnan.120hz", "GoldenNugget", "Nugget by leminlimez",
             "catwithabaloon"]
    positions = [idx(n) for n in order]
    check("all mandated credits present", all(p >= 0 for p in positions),
          str(list(zip(order, positions))))
    check("credit order: Adnan.120hz -> GoldenNugget -> Nugget/leminlimez -> catwithabaloon",
          positions == sorted(positions) and positions[0] == 0,
          str(positions))
    about.close()

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
