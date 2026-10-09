#!/usr/bin/env python3
"""Audit 57: Settings device status froze at the first visit.

The Settings page built its "This device" rows (and its preset list)
once at construction. The only rebuild was ``refresh()``, and nothing
re-ran it when the device state changed underneath an already-open
page: the device-enumeration/selection flows refreshed Home, the
device panel and the footer, but never a built Settings page, and
``refresh()`` itself never re-read the preset list — so opening
Settings via Home's gear (home.py open_settings, a bare
``setCurrentIndex(4)``) or via the presets section showed whatever
state was current at the first build, forever.

Fix contract proven here, offscreen, with a stub device:
* a built Settings page shown again after the stub device appears
  displays the new device (show refresh);
* a device change landing while the page stays open updates its rows
  through the same hook the device flows call;
* ``refresh()`` (the call the navigation / presets paths route
  through) also picks up presets written since the page was built.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit57_settings_live_refresh.py
"""
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Isolate every QSettings / AppData store: the page and its helpers
# (PresetManager, HotLoad, update channel) read and write there.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-a57-")
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="workslop-a57-")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

app = QApplication([])

import src.qt.resources_rc  # noqa: E402,F401
from src.gui.ios.settings import IOSSettingsPage  # noqa: E402
from src.gui.ios.theme_manager import ThemeManager  # noqa: E402
from src.gui.main_window_mixins import DeviceBarMixin  # noqa: E402


class _Settings:
    def __init__(self):
        self.store = {}

    def value(self, key, default=None, type=None):  # noqa: A002
        return self.store.get(key, default if default is not None else "")

    def setValue(self, key, val):
        self.store[key] = val

    def sync(self):
        pass


class _Device:
    def __init__(self, model, version, build):
        self.name = "Stub iPhone"
        self.model = model
        self.version = version
        self.build = build


def _device_texts(page):
    """All label texts in the 'This device' section, row by row."""
    texts = []
    lay = page._device_section_lay
    for i in range(lay.count()):
        row = lay.itemAt(i).widget()
        if row is None:
            continue
        for lbl in row.findChildren(QLabel):
            texts.append(lbl.text())
    return texts


class _Window:
    def __init__(self, manager):
        self.device_manager = manager
        self.settings = _Settings()
        self.theme_manager = SimpleNamespace(current_theme=ThemeManager.IOS)

    def _sync_settings(self):
        pass

    def apply_theme(self, _theme):
        pass


pref = SimpleNamespace(
    auto_reboot=True, disable_tendies_limit=False,
    auto_refresh_posterboard=True, use_backup_cache=False,
    use_encrypted_backup=False, use_afc_media=False,
    skip_setup=False, supervised=False, organization_name="",
    tweak_autosave=True)
manager = SimpleNamespace(
    devices=[], pref_manager=pref,
    data_singleton=SimpleNamespace(current_device=None))
window = _Window(manager)

print("\nAudit 57: Settings device rows live-refresh")
page = IOSSettingsPage(window)
page.show()
app.processEvents()
texts = _device_texts(page)
check("first visit with no device says No device",
      any("No device" in t for t in texts), str(texts))

# --- show path: device appears while the user is elsewhere, then the
# page is displayed again (Home gear / presets section / shell return
# all end with this page being shown). -------------------------------
page.hide()
app.processEvents()
manager.data_singleton.current_device = _Device("iPhone14,5", "26.6.1", "23G83")
page.show()
app.processEvents()
texts = _device_texts(page)
check("re-shown page picks up the connected device model",
      any("iPhone14,5" in t for t in texts), str(texts))
check("re-shown page picks up the connected device iOS + build",
      any("26.6.1" in t for t in texts) and any("23G83" in t for t in texts),
      str(texts))
check("stale 'No device' row is gone",
      not any("No device" in t for t in texts), str(texts))

# --- device-change path: the page stays open while the device state
# changes (enumeration finished / another device selected). The
# device flows call this hook; an unbuilt page must stay unbuilt. ----
class _DeviceHost(DeviceBarMixin, QWidget):
    pass


host = _DeviceHost()
host._ios_page_objs = {}
host._refresh_ios_settings_if_built()  # must not build or crash
check("device hook leaves an unbuilt Settings page unbuilt",
      host._ios_page_objs == {})
host._ios_page_objs = {"ios_settings": page}
manager.data_singleton.current_device = _Device("iPhone17,1", "27.0", "24A100")
host._refresh_ios_settings_if_built()
app.processEvents()
texts = _device_texts(page)
check("open page updates when the device changes underneath it",
      any("iPhone17,1" in t for t in texts)
      and any("24A100" in t for t in texts), str(texts))
check("previous device no longer shown",
      not any("iPhone14,5" in t for t in texts), str(texts))

# --- presets path: refresh() is what navigation / open_presets_section
# route through; a preset written after the page was built must show. -
before = [page.preset_list.item(i).text()
          for i in range(page.preset_list.count())]
check("new preset not listed yet",
      not any("Audit57Preset" in t for t in before), str(before))
preset_file = os.path.join(
    page.preset_manager.presets_dir, "Audit57Preset.json")
with open(preset_file, "w", encoding="utf-8") as f:
    json.dump({"metadata": {
        "description": "audit 57", "device_model": "iPhone17,1",
        "ios_version": "27.0", "created_at": 1, "updated_at": 1,
        "tags": [], "version": 2}}, f)
page.refresh()
app.processEvents()
after = [page.preset_list.item(i).text()
         for i in range(page.preset_list.count())]
check("refresh() picks up presets written since first visit",
      any("Audit57Preset" in t for t in after), str(after))

page.close()
print(f"\nALL {PASS} CHECKS PASSED")
