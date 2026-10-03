#!/usr/bin/env python3
"""Final v11 build checks (user orders 2026-10-03 12:09-12:27).

Covers, against a real offscreen MainWindow:

* UI-3 (Full Nugget) dark palette on the three pages that were still
  WorkSlop-light (Daemons, Posterboard, Settings — classic + iOS-stack
  Daemons included), restored to the themed look in UI-1 / UI-2.
* Renamed, vertically stacked interface picker (Settings + first
  launch): "WorkSlop (Main)" / "WorkSlop 2" / "Nugget", fluid rounded
  boxes, active box clearly marked, old labels gone.
* OS title bar follows the interface (dark state requested only in
  Full Nugget; applied via DWM on Windows, verified here as window
  state because offscreen renders have no native chrome to capture).
* Classic sidebar (UI-2 & UI-3) has a Backup entry above Apply opening
  the same Backup & Apply page as the main UI (iOS page 13).
* The Beta tester team block (plain names, no links) rides with the
  Home credit area in all three interfaces.

Run: QT_QPA_PLATFORM=offscreen python tools/test_final_ui_v11.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Isolate every QSettings store: never touch the real WorkSlop config.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-final-ui-")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


try:
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication, QLabel
except Exception as e:
    print(f"skipped: {type(e).__name__}: {e}")
    raise SystemExit(0)

app = QApplication([])
app.setApplicationName("WorkSlop Desktop")

# With no usbmuxd in this environment, device refresh ends in a modal
# "failed to get device list" dialog; a human would click it away, so
# the test auto-dismisses modal widgets instead of blocking forever.
_modal_killer = QTimer()
_modal_killer.timeout.connect(
    lambda: (QApplication.activeModalWidget().close()
             if QApplication.activeModalWidget() is not None else None))
_modal_killer.start(50)

import src.qt.resources_rc  # noqa: F401,E402
from src.controllers.settings import Settings  # noqa: E402
from src.controllers.translator import Translator  # noqa: E402
from src.devicemanagement.device_manager import DeviceManager  # noqa: E402
from src.gui.brand_credits import beta_testers_html  # noqa: E402
from src.gui.interface_picker import InterfacePickerDialog  # noqa: E402
from src.gui.ios.components import IOSCard, IOSSectionHeader  # noqa: E402
from src.gui.ios.theme_manager import ThemeManager  # noqa: E402
from src.gui.main_window import (  # noqa: E402
    _CLASSIC_ORIGINAL_ICONS, _HIDDEN_THEMED_ICONS, MainWindow,
)
from src.gui.pages.pages_list import Page  # noqa: E402
from src.gui.titlebar import apply_os_titlebar_dark, titlebar_dark_for_theme  # noqa: E402

qs = QSettings("WorkSlop", "WorkSlop")
qs.setValue("ui/theme", "ios")
qs.sync()
win = MainWindow(device_manager=DeviceManager(),
                 translator=Translator(app, Settings()))
app.processEvents()

print("\nFull Nugget dark pages (UI-3)")
win.apply_theme(ThemeManager.FULL_NUGGET)
app.processEvents()
check("Settings page flags Full Nugget", win.ios_settings._full_nugget)
check("Settings scroll backdrop is Nugget #1e1e1e",
      "#1e1e1e" in win.ios_settings._scroll.styleSheet(),
      win.ios_settings._scroll.styleSheet())
_cards = win.ios_settings.findChildren(IOSCard)
check("Settings cards are Nugget #3b3b3b",
      _cards and all("#3b3b3b" in c.styleSheet() for c in _cards),
      _cards[0].styleSheet() if _cards else "no cards")
_headers = win.ios_settings.findChildren(IOSSectionHeader)
check("Settings section headers are white",
      _headers and all("#FFFFFF" in h.styleSheet() for h in _headers),
      _headers[0].styleSheet() if _headers else "no headers")
check("Posterboard flags Full Nugget", win.ios_posterboard._full_nugget)
check("Posterboard backdrop is Nugget #1e1e1e",
      "#1e1e1e" in win.ios_posterboard._tendies_scroll.styleSheet())
check("Daemons (iOS stack) flags Full Nugget",
      win.ios_daemons.content._full_nugget)
check("Daemons master label is white",
      "#FFFFFF" in win.ios_daemons.content._master_label.styleSheet())
check("classic Daemons page flags Full Nugget",
      win.pages[Page.Daemons]._full_nugget)
check("classic Daemons backdrop is Nugget #1e1e1e",
      "#1e1e1e" in win.ui.daemonsScrollArea.styleSheet())
win.pages[Page.Daemons].load()
app.processEvents()
check("classic Daemons content is dark",
      win.pages[Page.Daemons]._content._full_nugget)

print("\nlight again in UI-2 / UI-1")
win.apply_theme(ThemeManager.CLASSIC)
app.processEvents()
check("Settings light again in WorkSlop 2",
      not win.ios_settings._full_nugget
      and "#1e1e1e" not in win.ios_settings._scroll.styleSheet())
check("Settings cards themed again in WorkSlop 2",
      all("#3b3b3b" not in c.styleSheet()
          for c in win.ios_settings.findChildren(IOSCard)))
check("Posterboard light again in WorkSlop 2",
      not win.ios_posterboard._full_nugget
      and "#1e1e1e" not in win.ios_posterboard._tendies_scroll.styleSheet())
check("classic Daemons light again in WorkSlop 2",
      not win.pages[Page.Daemons]._full_nugget
      and "#1e1e1e" not in win.ui.daemonsScrollArea.styleSheet())
win.apply_theme(ThemeManager.IOS)
check("Settings light in WorkSlop (Main)",
      not win.ios_settings._full_nugget)

print("\ninterface picker (Settings)")
btns = win.ios_settings.interface_buttons
check("picker has all three interfaces",
      set(btns) == {ThemeManager.IOS, ThemeManager.CLASSIC,
                    ThemeManager.FULL_NUGGET})
texts = {t: b.text() for t, b in btns.items()}
check("top box is WorkSlop (Main)",
      texts[ThemeManager.IOS].startswith("✓  WorkSlop (Main)")
      or texts[ThemeManager.IOS].startswith("WorkSlop (Main)"),
      texts[ThemeManager.IOS])
check("second box is WorkSlop 2",
      "WorkSlop 2" in texts[ThemeManager.CLASSIC],
      texts[ThemeManager.CLASSIC])
check("third box is Nugget",
      "Nugget" in texts[ThemeManager.FULL_NUGGET],
      texts[ThemeManager.FULL_NUGGET])
check("no old labels remain in the picker",
      all("Full Nugget" not in t for t in texts.values()), str(texts))
check("boxes have fluid rounded corners",
      all("border-radius: 16px" in b.styleSheet() for b in btns.values()))
check("active box (WorkSlop Main) is check-marked",
      texts[ThemeManager.IOS].startswith("✓"), texts[ThemeManager.IOS])
win.show()
win.on_settingsPageBtn_clicked()
app.processEvents()
ys = {t: b.geometry().y() for t, b in btns.items()}
check("boxes stack vertically in order",
      ys[ThemeManager.IOS] < ys[ThemeManager.CLASSIC]
      < ys[ThemeManager.FULL_NUGGET], str(ys))
btns[ThemeManager.CLASSIC].click()
app.processEvents()
check("clicking WorkSlop 2 switches the interface",
      win.theme_manager.current_theme == ThemeManager.CLASSIC)
check("WorkSlop 2 box becomes the marked one",
      btns[ThemeManager.CLASSIC].text().startswith("✓")
      and not btns[ThemeManager.IOS].text().startswith("✓"))
btns[ThemeManager.FULL_NUGGET].click()
app.processEvents()
check("clicking Nugget switches to Full Nugget",
      win.theme_manager.current_theme == ThemeManager.FULL_NUGGET)
check("Settings stays reachable and dark from Nugget UI",
      win.ios_settings._full_nugget
      and win.ios_pages.currentIndex() == 4)
btns[ThemeManager.IOS].click()
app.processEvents()
check("clicking WorkSlop (Main) switches back",
      win.theme_manager.current_theme == ThemeManager.IOS
      and not win.ios_settings._full_nugget)

print("\nfirst-launch picker")
picker = InterfacePickerDialog()
picker_text = " ".join(w.text() for w in picker.findChildren(QLabel))
check("first-launch names match the Settings picker",
      "WorkSlop (Main)" in picker_text and "WorkSlop 2" in picker_text
      and "Full Nugget" not in picker_text, picker_text)
picker.close()

print("\nOS title bar follows the interface")
check("title bar dark only in Full Nugget",
      titlebar_dark_for_theme(ThemeManager.FULL_NUGGET)
      and not titlebar_dark_for_theme(ThemeManager.CLASSIC)
      and not titlebar_dark_for_theme(ThemeManager.IOS))
check("window state requests light title bar in WorkSlop (Main)",
      win._titlebar_dark is False)
win.apply_theme(ThemeManager.FULL_NUGGET)
check("window state requests dark title bar in Nugget UI",
      win._titlebar_dark is True)
if sys.platform != "win32":
    check("DWM application is a safe no-op off Windows",
          apply_os_titlebar_dark(win, True) is False)
win.apply_theme(ThemeManager.IOS)

print("\nclassic sidebar Backup entry")
check("Backup button exists in the classic sidebar",
      win.ui.backupPageBtn.objectName() == "backupPageBtn")
check("Backup button is labelled Backup",
      win.ui.backupPageBtn.text() == "Backup")
lay = win.ui.verticalLayout
check("Backup sits directly above Apply",
      lay.indexOf(win.ui.backupPageBtn) + 1
      == lay.indexOf(win.ui.applyPageBtn))
check("Backup icon follows the WorkSlop set in UI-2",
      _HIDDEN_THEMED_ICONS.get("backupPageBtn") == ":/icon/ws-backup.svg")
check("Backup icon is an original Nugget icon in UI-3",
      _CLASSIC_ORIGINAL_ICONS.get("backupPageBtn")
      == ":/icon/shippingbox.svg")
win.apply_theme(ThemeManager.FULL_NUGGET)
win.ui.backupPageBtn.show()
win.on_backupPageBtn_clicked()
app.processEvents()
check("Backup opens the Backup & Apply page (iOS 13)",
      win.content_stack.currentIndex() == 1
      and win.ios_pages.currentIndex() == 13)
check("Backup entry is the checked sidebar item",
      win.ui.backupPageBtn.isChecked())

print("\nbeta tester block on Home")
html = beta_testers_html("#000000")
check("beta block lists the team",
      "Beta tester team" in html and "Charlie" in html
      and "rfrz1d_" in html and "Davy (@Davydavpn)" in html, html)
check("beta block carries no links at all",
      "<a " not in html and "tiktok" not in html and "t.me" not in html,
      html)
classic_beta = win.pages[Page.Home].preset_widget._beta_lbl
check("classic Home shows the beta block",
      "Beta tester team" in classic_beta.text())
ios_beta = win.ios_home.preset_widget._beta_lbl
check("WorkSlop Home shows the beta block",
      "Beta tester team" in ios_beta.text())

print(f"\nALL {PASS} CHECKS PASSED")
