#!/usr/bin/env python3
"""Offscreen checks: fast detection diagnostics + working Refresh.

Covers the 2026-10-03 user reports:
* device appears only after a long wait / "No Device" with no reason
  (detection now reads identity first, publishes immediately, logs
  timings, and leaves an honest cable/Trust/driver note);
* Refresh sometimes did nothing (stale in-progress flag wedged it) and
  gave no feedback (now: searching state + partial device publish +
  watchdog release);
* pre-device Support/MobileGestalt/Status Bar statuses on Home
  (rows must not exist at all until a device is really detected).

Run: QT_QPA_PLATFORM=offscreen ~/wsui-venv/bin/python \
    tools/test_wave10_detection_refresh.py
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

import src.qt.resources_rc  # noqa: E402,F401
import src.devicemanagement.device_manager as dm_mod  # noqa: E402
from src.devicemanagement.device_manager import DeviceManager  # noqa: E402
from pymobiledevice3.exceptions import PasswordRequiredError  # noqa: E402


class _Settings:
    def __init__(self):
        self.store = {}

    def value(self, key, default=None, type=None):  # noqa: A002
        return self.store.get(key, default if default is not None else "")

    def setValue(self, key, val):
        self.store[key] = val


class _USBDevice:
    serial = "SERIAL-1"
    is_usb = True


class _FakeLD:
    all_values = {
        "ProductType": "iPhone14,5", "HardwareModel": "D17AP",
        "HardwarePlatform": "t8110", "DeviceName": "Test iPhone",
        "ProductVersion": "26.6.1", "BuildVersion": "23G83",
    }

    async def get_locale(self):
        return "en_US"


def _make_manager():
    manager = DeviceManager.__new__(DeviceManager)
    # Minimal __init__ surface used by _get_devices.
    import src.devicemanagement.data_singleton as _ds
    manager.devices = []
    manager.detection_notes = []
    manager.data_singleton = _ds.DataSingleton()
    manager.current_device_index = 0
    manager.pref_manager = SimpleNamespace(use_encrypted_backup=True)
    manager._test_mode = False
    return manager


async def _run_detection(manager, settings, **patches):
    """Run _get_devices with usbmux/lockdown fakes installed."""
    orig_list = dm_mod.usbmux.list_devices
    orig_session = dm_mod.lockdown_session
    try:
        dm_mod.usbmux.list_devices = patches["list_devices"]
        dm_mod.lockdown_session = patches["lockdown_session"]
        found = []
        await manager._get_devices(
            settings, lambda msg: None,
            on_device_found=lambda dev: found.append(dev))
        return found
    finally:
        dm_mod.usbmux.list_devices = orig_list
        dm_mod.lockdown_session = orig_session


print("\ndetection: identity-first, published immediately")
settings = _Settings()
manager = _make_manager()


@asynccontextmanager
async def _good_session(serial, **kw):
    yield _FakeLD()


async def _one_device():
    return [_USBDevice()]


found = asyncio.run(_run_detection(
    manager, settings, list_devices=_one_device,
    lockdown_session=_good_session))
check("one device detected", len(manager.devices) == 1)
check("on_device_found fired during enumeration", len(found) == 1)
dev = manager.devices[0]
check("basic identity populated",
      dev.name == "Test iPhone" and dev.version == "26.6.1"
      and dev.build == "23G83" and dev.model == "iPhone14,5")
check("locale filled in after publish", dev.locale == "en_US")
check("no diagnostics notes on success", manager.detection_notes == [])

print("\ndetection: empty enumeration explains itself")
manager = _make_manager()


async def _no_devices():
    return []


found = asyncio.run(_run_detection(
    manager, settings, list_devices=_no_devices,
    lockdown_session=_good_session))
check("still no devices", manager.devices == [] and found == [])
check("honest guidance note recorded",
      any("Trust" in note and "cable" in note.lower()
          for note in manager.detection_notes),
      str(manager.detection_notes))

print("\ndetection: locked/untrusted device is explained, not silent")
manager = _make_manager()


@asynccontextmanager
async def _locked_session(serial, **kw):
    raise PasswordRequiredError("locked")
    yield  # pragma: no cover


found = asyncio.run(_run_detection(
    manager, settings, list_devices=_one_device,
    lockdown_session=_locked_session))
check("locked device not listed", manager.devices == [])
check("trust guidance recorded",
      any("Trust" in note for note in manager.detection_notes),
      str(manager.detection_notes))

# ---------------------------------------------------------------------------
print("\nrefresh: stale flag self-heals, feedback shows, device flips UI")
from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QWidget  # noqa: E402
from src.gui.ios.device_panel import WorkSlopDevicePanel  # noqa: E402
from src.gui.ios.home import IOSHomePage  # noqa: E402
from src.gui.main_window_mixins import DeviceBarMixin  # noqa: E402


class _FakeDevice:
    def __init__(self):
        self.name = "Stub iPhone"
        self.connected_via_usb = True
        self.version = "26.6.1"
        self.build = "23G83"
        self.model = "iPhone14,5"
        self.udid = "STUB-UDID"


class _FakeManager:
    """Manager whose get_devices 'finds' a device only after refresh 2."""

    def __init__(self):
        self.devices = []
        self.detection_notes = ["No device reported by usbmux. Check the "
                                "USB cable, tap Trust on the iPhone."]
        self.current_device_index = 0
        self.scans = 0
        self.data_singleton = SimpleNamespace(current_device=None)

    def get_devices(self, settings, show_alert=lambda x: None,
                    on_device_found=None):
        self.scans += 1
        if self.scans >= 2:
            dev = _FakeDevice()
            self.devices = [dev]
            self.detection_notes = []
            if on_device_found is not None:
                on_device_found(dev)

    def get_current_device_udid(self):
        return self.devices[0].udid if self.devices else None

    def get_current_device_name(self):
        return self.devices[0].name if self.devices else "No Device"

    def get_current_device_version(self):
        return self.devices[0].version if self.devices else ""

    def get_current_device_build(self):
        return self.devices[0].build if self.devices else ""

    def get_current_device_model(self):
        return self.devices[0].model if self.devices else ""

    def get_current_device_is_supported_by_fork(self):
        return bool(self.devices)

    def get_current_device_partially_supported(self):
        return False


class _StubUI:
    def __init__(self):
        self.refreshBtn = QPushButton()
        self.devicePicker = QComboBox()
        for name in ("sidebarDiv1", "sidebarDiv2", "gestaltPageBtn",
                     "statusBarPageBtn", "springboardOptionsPageBtn",
                     "internalOptionsPageBtn", "liquidGlassPageBtn",
                     "daemonsPageBtn", "iconThemesPageBtn", "passcodePageBtn",
                     "posterboardPageBtn", "applyPageBtn", "jjtechBtn",
                     "duyBtn"):
            setattr(self, name, QLabel())


class _Host(DeviceBarMixin, QWidget):
    def __init__(self, manager):
        QWidget.__init__(self)
        self.device_manager = manager
        self.settings = _Settings()
        self.ui = _StubUI()
        self.refresh_in_progress = False
        self.refresh_worker_thread = None
        self.noneText = "No Device"
        self.footer_status_lbl = QLabel()
        self.ios_home = IOSHomePage(self)
        self.device_panel = WorkSlopDevicePanel(self)
        self.alerts = []

    # mixin collaborators
    def alert_message(self, msg, log_to_console=True):
        self.alerts.append(msg)

    def toggle_thread_btns(self, disabled=False):
        pass

    def show_home(self):
        pass

    def _apply_hidden_feature_gating(self):
        pass


import time as _time


def _pump_until(predicate, timeout=10.0):
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        _time.sleep(0.01)
    app.processEvents()
    return predicate()


manager = _FakeManager()
host = _Host(manager)
app.processEvents()
check("panel starts at No Device",
      "No device" in host.device_panel.device_combo.currentText(),
      host.device_panel.device_combo.currentText())
check("home title starts at No device",
      host.ios_home._device_title.text() in ("No device connected", "No Device"),
      host.ios_home._device_title.text())

# Pre-device statuses must not exist at all (user report).
host.ios_home.update_device_info()
host.ios_home.update_status()
app.processEvents()
for key in ("gestalt", "statusbar", "support"):
    row = host.ios_home._info_rows[key]
    check(f"no-device: {key} row hidden", not row.isVisible() or
          host.ios_home._info_values[key].text() == "",
          host.ios_home._info_values[key].text())

# Wedge the flag like the old bug, then Refresh must recover by itself.
host.refresh_in_progress = True
host.refresh_worker_thread = None
host.refresh_devices()
_pump_until(lambda: manager.scans >= 1 and not host.refresh_in_progress)
check("refresh #1 ran despite stale flag", manager.scans == 1,
      str(manager.scans))
host.refresh_devices()
# let the worker threads finish
_pump_until(lambda: manager.scans >= 2 and not host.refresh_in_progress)
check("refresh #2 ran", manager.scans == 2, str(manager.scans))
check("device flipped into the panel",
      "Stub iPhone" in host.device_panel.device_combo.currentText(),
      host.device_panel.device_combo.currentText())
check("home title flipped to the device",
      host.ios_home._device_title.text() == "Stub iPhone",
      host.ios_home._device_title.text())
check("footer reports the device",
      "1 device" in host.footer_status_lbl.text(),
      host.footer_status_lbl.text())
check("gestalt row now exists with the shared verdict (Locked 23G83)",
      host.ios_home._info_values["gestalt"].text() == "Locked",
      host.ios_home._info_values["gestalt"].text())

print(f"\nALL {PASS} CHECKS PASSED")
