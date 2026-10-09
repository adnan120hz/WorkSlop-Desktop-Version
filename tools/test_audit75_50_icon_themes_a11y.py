#!/usr/bin/env python3
"""Audit 75 + 50 (frozen icon_themes.py, UI-text-only changes):

* every "Target on device" cell carries its full path as a tooltip
  (Audit 75: the dual-table column is narrow and elides the path);
* the theme card's icon-only delete button has a tooltip and an
  accessible name (Audit 50);
* a row Add button disabled because the pack lacks that variant
  (Dark Shortcuts) explains why in a tooltip and stays out of the
  tab chain (Audit 50).

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit75_50_icon_themes_a11y.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton  # noqa: E402

app = QApplication.instance() or QApplication([])

from src.tweaks.tweaks import tweaks, TweakID  # noqa: E402
from src.tweaks.icon_themes.icon_theme import IconTheme  # noqa: E402
from src.gui.ios.icon_themes import (  # noqa: E402
    IOSIconThemesPage, IOS18_ICONS, icon_asset_path)

tweak = tweaks[TweakID.IconThemes]
tweak.themes = []
page = IOSIconThemesPage(None)
page.show()
app.processEvents()

print("\nAudit 75: target-path tooltips")
for dark_i, table in enumerate(page._ios18_tables):
    bad = [r for r in range(table.rowCount())
           if not table.item(r, 2).toolTip()
           or table.item(r, 2).toolTip() != table.item(r, 2).text()]
    check(f"table {dark_i} all rows toolTipped", not bad, str(bad[:3]))

print("\nAudit 50: disabled Add explains itself")
dark_table = page._ios18_tables[1]
row = next(i for i, (_n, b, _s) in enumerate(IOS18_ICONS)
           if b == "com.apple.shortcuts")
btn = dark_table.cellWidget(row, 3).findChild(QPushButton)
check("shortcuts dark has no asset",
      not os.path.isfile(icon_asset_path("shortcuts", True)))
check("add button disabled", not btn.isEnabled())
check("add button tooltip explains", "Dark" in btn.toolTip(),
      repr(btn.toolTip()))
check("add button out of tab chain",
      btn.focusPolicy() == Qt.FocusPolicy.NoFocus)

print("\nAudit 50: theme-card delete button")
theme = IconTheme(bundle_id="com.example.audit75",
                  display_name="Audit75", icon_path="")
tweak.add_theme(theme)
page.refresh_themes()
del_btns = [b for b in page.findChildren(QToolButton)
            if "com.example.audit75" in b.toolTip()]
check("delete button rendered with tooltip", len(del_btns) == 1,
      str(len(del_btns)))
if del_btns:
    check("delete has accessible name",
          del_btns[0].accessibleName() == del_btns[0].toolTip())
tweak.themes = []
page.refresh_themes()

print(f"\nALL {PASS} CHECKS PASSED")
