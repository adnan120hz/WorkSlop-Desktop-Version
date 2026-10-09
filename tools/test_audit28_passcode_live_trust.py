#!/usr/bin/env python3
"""Fix Audit 28: Passcode page trust label read a stale cache.

The "Write to device" device line claimed "This computer is trusted by
it" straight from the enumeration-time ``current_device`` cache — stale
in both directions (trusted-since-scan still showed as untrusted,
revoked trust still showed as trusted). The page now probes the device
live on every show (``lockdown_session(autopair=False)`` + the same
``paired`` check the write thread uses); the cache only identifies the
device and, when the device cannot be reached, the label explicitly
says the status is a cached fallback.

Offline: ``lockdown_session`` is faked per case; no device is touched.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit28_passcode_live_trust.py
"""
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-a28-")
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="workslop-a28-")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import src.gui.ios.passcode_theme as pc_mod  # noqa: E402
from src.gui.ios.passcode_theme import IOSPasscodeThemePage  # noqa: E402


class _Settings:
    def __init__(self):
        self.store = {}

    def value(self, key, default=None, type=None):  # noqa: A002
        return self.store.get(key, default if default is not None else "")

    def setValue(self, key, val):
        self.store[key] = val

    def sync(self):
        pass


class _Window:
    def __init__(self, manager):
        self.device_manager = manager
        self.settings = _Settings()

    def _sync_settings(self):
        pass


def make_manager():
    device = SimpleNamespace(
        name="Stub iPhone", model="iPhone14,5", version="26.6.1",
        build="23G83", locale="")
    return SimpleNamespace(
        data_singleton=SimpleNamespace(
            current_device=device, device_available=True),
        get_current_device_udid=lambda: "STUB-UDID-28",
        last_apply_journal_path=None)


def wait_probe(page):
    probe = page._trust_probe
    if probe is not None:
        assert probe.wait(10000), "trust probe thread did not finish"
    app.processEvents()


def build_page():
    window = _Window(make_manager())
    page = IOSPasscodeThemePage(window)
    page.show()
    app.processEvents()
    return page


print("\n(a) device trusted NOW (cache says nothing about trust either way)")
@asynccontextmanager
async def fake_trusted(serial=None, **kw):
    yield SimpleNamespace(paired=True)

pc_mod.lockdown_session = fake_trusted
page = build_page()
wait_probe(page)
text = page._device_lbl.text()
check("label claims trust from the LIVE probe", "checked live" in text, text)
check("label does not present cached status as fact",
      "cached" not in text.lower(), text)
page.close()

print("\n(b) trust revoked since enumeration — cache must not win")
@asynccontextmanager
async def fake_untrusted(serial=None, **kw):
    yield SimpleNamespace(paired=False)

pc_mod.lockdown_session = fake_untrusted
page = build_page()
wait_probe(page)
text = page._device_lbl.text()
check("label reports NOT trusted from the LIVE probe",
      "NOT trusted" in text and "checked live" in text, text)
page.close()

print("\n(c) device unreachable — cache shown only as labelled fallback")
@asynccontextmanager
async def fake_unreachable(serial=None, **kw):
    raise RuntimeError("usbmux: no such device")
    yield  # pragma: no cover - makes this an async generator

pc_mod.lockdown_session = fake_unreachable
page = build_page()
wait_probe(page)
text = page._device_lbl.text()
check("fallback label explicitly says cached", "cached" in text.lower(), text)
check("fallback never claims live trust",
      "trusted by it (checked live" not in text, text)
page.close()

print("\n(d) no device cached — no probe, honest no-device line")
@asynccontextmanager
async def fake_must_not_run(serial=None, **kw):
    raise AssertionError("probe ran without a cached device")
    yield

pc_mod.lockdown_session = fake_must_not_run
manager = make_manager()
manager.data_singleton.current_device = None
page = IOSPasscodeThemePage(_Window(manager))
page.show()
app.processEvents()
check("no-device line shown", "No trusted iPhone connected" in page._device_lbl.text(),
      page._device_lbl.text())
check("no probe was started", page._trust_probe is None)
page.close()

print(f"\nALL {PASS} CHECKS PASSED")
