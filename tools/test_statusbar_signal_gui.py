#!/usr/bin/env python3
"""Offscreen GUI checks for the "Full Signal Bars (No SIM Visual)" row.

Skips cleanly when PySide6 is unavailable. Verifies:

* iOS 26.x (non-audit-target): row enabled; toggling it flips the backend
  predicate and refreshes the conflicting Disable Cellular Service icon
  switch off; turning that switch on dissolves the feature visibly.
* iOS 26.6.1 / 23G83: the feature is a normal active tweak (Wave 11 —
  the research-only containment was removed by user order), so the row
  is enabled and no containment note is shown.
* iOS 27: the row is hidden with the other classic controls.
* Unknown version: row disabled (never treated as compatible).

Run: QT_QPA_PLATFORM=offscreen python tools/test_statusbar_signal_gui.py
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


try:
    from PySide6.QtWidgets import QApplication
except Exception as e:
    print(f"skipped: {type(e).__name__}: {e}")
    raise SystemExit(0)

app = QApplication([])

from src.tweaks.tweaks import tweaks, TweakID
from src.tweaks.status_bar.status_setter import StatusBarItem
from src.gui.ios.statusbar import IOSStatusBarPage


class _DM:
    def __init__(self, version, build=""):
        self._version, self._build = version, build

    def get_current_device_version(self):
        return self._version

    def get_current_device_build(self):
        return self._build


class _Window:
    def __init__(self, version, build=""):
        self.device_manager = _DM(version, build)


def fresh_page(version, build=""):
    # The StatusBar tweak is a shared singleton; reset its recipe state.
    st = tweaks[TweakID.StatusBar]
    st.unset_full_signal_bars_no_sim()
    st.set_enabled(False)
    st.unset_item_override(StatusBarItem.CellularServiceStatusBarItem)
    page = IOSStatusBarPage(_Window(version, build))
    page.show()
    app.processEvents()
    return page, st


print("\niOS 26.x (non-target): toggle + conflict sync")
page, st = fresh_page("26.0")
st.set_enabled(True)
page._refresh_full_signal_gate()
check("row enabled", page.full_signal_switch.isEnabled())
page.full_signal_switch.setChecked(True)
app.processEvents()
check("predicate on after toggle", st.is_full_signal_bars_no_sim_enabled())
conflict = page._item_switches[StatusBarItem.CellularServiceStatusBarItem]
check("disable-service switch refreshed off", not conflict.isChecked())
conflict.setChecked(True)
app.processEvents()
check("predicate off after conflict", not st.is_full_signal_bars_no_sim_enabled())
check("feature switch synced off", not page.full_signal_switch.isChecked())

print("\niOS 26.6.1 / 23G83: normal active tweak (Wave 11)")
page, st = fresh_page("26.6.1", "23G83")
st.set_enabled(True)
page._refresh_full_signal_gate()
check("row enabled on 26.6.1 target", page.full_signal_switch.isEnabled())
check("no containment note on 26.6.1",
      not page._signal_note.text() and not page._signal_note.isVisible(),
      repr(page._signal_note.text()))

print("\niOS 27: hidden")
page, st = fresh_page("27.0", "24A435")
check("row hidden on iOS 27", not page.full_signal_switch.isVisible())

print("\nunknown version: disabled")
page, st = fresh_page("")
st.set_enabled(True)
page._refresh_full_signal_gate()
check("row disabled when unknown", not page.full_signal_switch.isEnabled())

print(f"\nALL {PASS} CHECKS PASSED")
