#!/usr/bin/env python3
"""Audit 99/56: Full Nugget SpringBoard radio for a disabled spec.

The registry spec for ``UseFloatingTabBar`` is ``disabled=True`` (dead
key on iPadOS 26.4+), so ``load_plist_tweaks()`` never registers it in
``tweaks``. The Full Nugget SpringBoard page used to wire
Default/Enabled/Disabled radios to it anyway, so clicking a radio in
the device-connected (content-enabled) state raised
``KeyError: <TweakID.UseFloatingTabBar: 19>`` from
``src/gui/pages/page.py``.

Fix (same tombstone pattern as the auto-lock row in the same file):
the ``floatingTabBarContent`` row is hidden and no radios are created
for the disabled spec. The registry spec itself is untouched.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit99_56_springboard_radio.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from PySide6.QtWidgets import QApplication, QMainWindow, QRadioButton  # noqa: E402

app = QApplication.instance() or QApplication([])

import src.qt.resources_rc  # noqa: E402,F401
from src.gui.nugget_pages.springboard import NuggetSpringboardPage  # noqa: E402
from src.qt.nugget741_ui import Ui_Nugget741  # noqa: E402
from src.tweaks.registry import SPECS  # noqa: E402
from src.tweaks.tweaks import tweaks, TweakID  # noqa: E402

print("\nregistry precondition (untouched by the fix)")
spec = next(s for s in SPECS if s.id is TweakID.UseFloatingTabBar)
check("UseFloatingTabBar spec still present", spec is not None)
check("UseFloatingTabBar spec still disabled=True", spec.disabled is True)

print("\nFull Nugget SpringBoard page builds offscreen")
host = QMainWindow()
ui = Ui_Nugget741()
ui.setupUi(host)
ui.pages.setCurrentWidget(ui.springboardOptionsPage)
host.show()
# Device-connected state: the upstream form enables the scroll content;
# this is the state in which the old radio could be clicked.
ui.springboardOptionsPageContent.setEnabled(True)
page = NuggetSpringboardPage(ui)
page.load()  # must not raise
app.processEvents()
check("page.load() completed", page.loaded is True)
check("disabled spec never registered in tweaks",
      TweakID.UseFloatingTabBar not in tweaks)

print("\nfloating tab bar row hidden, no clickable radio")
check("floatingTabBarContent exists on the vendored form",
      getattr(ui, "floatingTabBarContent", None) is not None)
check("floatingTabBarContent is not visible",
      not ui.floatingTabBarContent.isVisible())
radios = ui.floatingTabBarContent.findChildren(QRadioButton)
check("no radio buttons under floatingTabBarContent", radios == [],
      str([r.text() for r in radios]))
check("floatingTabBarBtns layout is empty",
      ui.floatingTabBarBtns.count() == 0,
      str(ui.floatingTabBarBtns.count()))
# Even force-showing the row cannot resurrect a clickable radio: there
# is simply nothing to click, so the old KeyError path is unreachable.
ui.floatingTabBarContent.show()
app.processEvents()
radios_after_show = ui.floatingTabBarContent.findChildren(QRadioButton)
check("force-showing the row still yields no radio",
      radios_after_show == [])
for radio in radios_after_show:  # pragma: no cover - empty by assertion
    radio.click()
app.processEvents()
check("no KeyError path remains for UseFloatingTabBar", True)
ui.floatingTabBarContent.hide()

print("\nother SpringBoard rows unchanged and clickable")
check("sibling row (authEngUIContent) still visible",
      ui.authEngUIContent.isVisible())
airdrop_radios = [
    ui.airdropTimeLimitBtns.itemAt(i).widget()
    for i in range(ui.airdropTimeLimitBtns.count())
    if ui.airdropTimeLimitBtns.itemAt(i).widget() is not None
]
check("AirDrop row still builds 3 radios", len(airdrop_radios) == 3,
      str(len(airdrop_radios)))
check("AirDrop tweak registered", TweakID.AirDropDisableTimeLimit in tweaks)
airdrop_radios[1].click()  # Enabled
app.processEvents()
check("clicking a live row does not raise and checks the radio",
      airdrop_radios[1].isChecked())
airdrop_radios[0].click()  # back to Default
app.processEvents()
check("live row returns to Default cleanly", airdrop_radios[0].isChecked())

print(f"\nALL {PASS} CHECKS PASSED")
