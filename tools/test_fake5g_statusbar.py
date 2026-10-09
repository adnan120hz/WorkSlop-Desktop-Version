#!/usr/bin/env python3
"""Fake-5G labeled data network types + Audit 26 load-back.

Covers (fake-5G research 2026-10-09 + Audit 26):

* the raw dataNetworkType values keep their struct meaning — 11="5G",
  12="5G+", 13="5GUW", 14="5GUC" (Cowabunga Lite / Nugget mapping) —
  and land at the same bytes in the 3944-byte override file;
* choosing a type also enables the cellular data network item (index
  9) in the struct, or the glyph would silently never render;
* the iOS page's network row shows the label, not the raw number;
* the Full Nugget page loads back master/date/item-radio state
  (Audit 26: active overrides used to look OFF).

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_fake5g_statusbar.py
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


from PySide6.QtWidgets import QApplication, QLabel, QMainWindow  # noqa: E402

app = QApplication.instance() or QApplication([])

import src.qt.resources_rc  # noqa: E402,F401
from src.tweaks.tweaks import tweaks, TweakID  # noqa: E402
from src.tweaks.status_bar.status_setter import StatusBarItem  # noqa: E402
from src.tweaks.status_bar.status_bar_tweak import (  # noqa: E402
    DATA_NETWORK_TYPE_LABELS, data_network_type_label)

st = tweaks[TweakID.StatusBar]


def reset_state():
    st.unset_data_network_type()
    st.unset_secondary_data_network_type()
    st.unset_date()
    st.unset_item_override(StatusBarItem.CellularDataNetworkStatusBarItem)
    st.unset_item_override(StatusBarItem.BluetoothStatusBarItem)
    st.unset_item_override(StatusBarItem.AlarmStatusBarItem)
    st.set_enabled(False)


print("\nlabels (Cowabunga/Nugget mapping)")
check("11 is 5G", data_network_type_label(11) == "5G")
check("12 is 5G+", data_network_type_label(12) == "5G+")
check("13 is 5GUW", data_network_type_label(13) == "5GUW")
check("14 is 5GUC", data_network_type_label(14) == "5GUC")
check("4 is LTE", data_network_type_label(4) == "LTE")
check("0 is GPRS", data_network_type_label(0) == "GPRS")
check("unnamed stays neutral", data_network_type_label(20) == "Type 20")
check("table covers 0-14", sorted(DATA_NETWORK_TYPE_LABELS) == list(range(15)))

print("\nstruct bytes (same values, same offsets)")
reset_state()
st.set_data_network_type(11)
data = st.setter.get_data()
check("payload is 3944 bytes", len(data) == 3944, str(len(data)))
check("overrideDataNetworkType flag (byte 47 bit 7)", data[47] & 0x80)
check("dataNetworkType=11 at bytes 2160..2163",
      int.from_bytes(data[2160:2164], "little") == 11)
check("overrideItemIsEnabled[9] byte set", data[9] == 1)
check("values.itemIsEnabled[9] byte set", data[73] == 1)
check("item 9 override enabled",
      st.is_item_overridden(StatusBarItem.CellularDataNetworkStatusBarItem))
check("item 9 shown",
      bool(st.get_item_override(StatusBarItem.CellularDataNetworkStatusBarItem)))
st.set_data_network_type(12)
check("12 round-trips", st.get_data_network_type_override() == 12)
st.set_data_network_type(13)
check("13 round-trips", st.get_data_network_type_override() == 13)
st.set_data_network_type(14)
check("14 round-trips", st.get_data_network_type_override() == 14)

print("\nitem hidden first, type chosen after -> item enabled")
reset_state()
st.set_item_override(StatusBarItem.CellularDataNetworkStatusBarItem, False)
check("item hidden", not st.get_item_override(
    StatusBarItem.CellularDataNetworkStatusBarItem))
st.set_data_network_type(11)
check("choosing 5G re-enables the item", bool(st.get_item_override(
    StatusBarItem.CellularDataNetworkStatusBarItem)))

print("\nsecondary type keeps its own bytes")
reset_state()
st.set_secondary_data_network_type(13)
data = st.setter.get_data()
check("secondaryDataNetworkType=13 at bytes 2164..2167",
      int.from_bytes(data[2164:2168], "little") == 13)

print("\niOS page row shows the label, not the number")
from src.gui.ios.statusbar import IOSStatusBarPage  # noqa: E402


class _DM:
    def get_current_device_version(self):
        return "26.6.1"

    def get_current_device_build(self):
        return "23G83"


class _Window:
    device_manager = _DM()


reset_state()
st.set_data_network_type(11)
page = IOSStatusBarPage(_Window())
page.show()
app.processEvents()
check("network switch on", page.network_type_row.isChecked())
check("'5G' label on the page",
      any(lbl.text() == "5G" for lbl in page.findChildren(QLabel)))
st.unset_data_network_type()
page2 = IOSStatusBarPage(_Window())
page2.show()
app.processEvents()
check("network switch off when unset",
      not page2.network_type_row.isChecked())

print("\nFull Nugget page loads back live state (Audit 26)")
from src.qt.nugget741_ui import Ui_Nugget741  # noqa: E402
from src.gui.nugget_pages.status_bar import NuggetStatusBarPage  # noqa: E402

reset_state()
st.set_enabled(True)
st.set_date("Fri, Oct 9")
st.set_item_override(StatusBarItem.BluetoothStatusBarItem, False)
st.set_item_override(StatusBarItem.AlarmStatusBarItem, True)
host = QMainWindow()
ui = Ui_Nugget741()
ui.setupUi(host)
nugget_page = NuggetStatusBarPage(ui)
nugget_page.load_page()
check("master switch loaded", ui.statusBarEnabledChk.isChecked())
check("content enabled with master", ui.statusBarPageContent.isEnabled())
check("date checkbox loaded", ui.dateChk.isChecked())
check("date text loaded", ui.dateTxt.text() == "Fri, Oct 9",
      repr(ui.dateTxt.text()))
check("bluetooth radio shows Force Hide", ui.bluetoothHideRdo.isChecked())
check("alarm radio shows Force Show", ui.alarmShowRdo.isChecked())
check("untouched item stays Default", ui.dndDefaultRdo.isChecked())

reset_state()
print(f"\nALL {PASS} CHECKS PASSED")
