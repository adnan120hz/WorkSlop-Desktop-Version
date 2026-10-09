#!/usr/bin/env python3
"""Fix Audit 6: a reset that skips a file must say what + why.

The iOS 27 HomeDomain .GlobalPreferences reset (no pristine base on
record) and the MobileGestalt reset (no base file) used to skip with
only a log line while the UI still announced "Reset complete!".
Now every skip is collected into ``last_reset_skips``, named on the
journal entry, and appended to the result alert; the GUI only shows
"Reset complete!" when the list stays empty.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit6_reset_skips.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

import src.devicemanagement.device_manager as dm_mod  # noqa: E402
from src.devicemanagement import device_manager as _dm  # noqa: E402
from src.exceptions.nugget_exception import NuggetException  # noqa: E402
from src.tweaks.basic_plist_locations import FileLocation  # noqa: E402
from src.utils.alerts import ApplyAlertMessage  # noqa: E402
from src.utils.pages import Page  # noqa: E402

PASS = 0
UDID = "00008101-TESTUDID"


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}")


class FakeDeviceManager:
    """Stand-in for DeviceManager holding only what _reset_tweaks touches.

    Mirrors tools/test_reset_no_capture.py; ``start_restore`` returns a
    real ApplyAlertMessage so the skip-reporting mutation is exercised.
    """

    def __init__(self, version, gestalt_error=False):
        self.version = version
        self.gestalt_error = gestalt_error
        self.written: dict = {}
        self.restored = None
        self.labels: list = []
        self.last_reset_skips: list = ["stale-from-previous-run"]

    def _raise_if_unsupported(self):
        pass

    def get_current_device_udid(self):
        return UDID

    def get_current_device_version(self):
        return self.version

    def concat_file(self, contents, path, files_to_restore, owner=None, group=None):
        self.written[path] = contents
        files_to_restore.append(path)

    async def add_skip_setup(self, files_to_restore, restoring_domains):
        pass

    async def start_restore(self, files_to_restore, update_label, prompt_choice=None):
        self.restored = list(files_to_restore)
        return ApplyAlertMessage(txt="All done! fake restore",
                                 title="Success!")

    def _load_gestalt_plist(self, update_label=lambda x: None):
        if self.gestalt_error:
            raise NuggetException("No mobilegestalt file provided (fake).")
        raise AssertionError("unexpected gestalt load in this fake")

    def _record_label(self, text):
        self.labels.append(text)


def run_reset(version, pages, gestalt_error=False):
    fake = FakeDeviceManager(version, gestalt_error=gestalt_error)
    alerts: list = []
    import src.restore.lastapply as lastapply
    real_gp = lastapply.load_gp_base
    real_clear = lastapply.clear_lastapply
    real_clear_gp = lastapply.clear_gp_base
    lastapply.load_gp_base = lambda udid: None  # no pristine base on record
    lastapply.clear_lastapply = lambda udid: None
    lastapply.clear_gp_base = lambda udid: None
    try:
        asyncio.run(_dm.DeviceManager._reset_tweaks(
            fake, pages, None, fake._record_label, alerts.append))
    finally:
        lastapply.load_gp_base = real_gp
        lastapply.clear_lastapply = real_clear
        lastapply.clear_gp_base = real_clear_gp
    return fake, alerts


# --- iOS 27 InternalOptions: HomeDomain GP skip is reported -----------------
print("iOS 27 reset without a pristine GP base reports the skip")
fake, alerts = run_reset("27.0", [Page.InternalOptions])
check("reset still ran (other files restored)", bool(fake.restored))
check("skip recorded on last_reset_skips",
      len(fake.last_reset_skips) == 1, repr(fake.last_reset_skips))
check("skip names the file",
      FileLocation.globalPreferencesHomeDomain.value in fake.last_reset_skips[0],
      fake.last_reset_skips[0])
check("skip says why (no pristine base)",
      "no pristine base" in fake.last_reset_skips[0])
check("result alert is not a bare success",
      alerts and "skipped" in (alerts[-1].txt or ""), repr(alerts[-1:]))
check("result details list the skip",
      "SKIPPED:" in (alerts[-1].detailed_txt or ""))

# --- MobileGestalt reset without a base file reports the skip ---------------
print("MobileGestalt reset without a base file reports the skip")
fake, alerts = run_reset("26.6.1", [Page.Gestalt], gestalt_error=True)
check("gestalt skip recorded", len(fake.last_reset_skips) == 1,
      repr(fake.last_reset_skips))
check("gestalt skip carries the reason",
      "No mobilegestalt file provided" in fake.last_reset_skips[0])
check("alert reports the gestalt skip",
      alerts and "skipped" in (alerts[-1].txt or ""))

# --- a reset with no skips leaves the success untouched ---------------------
print("a skip-free reset keeps a clean success")
fake, alerts = run_reset("26.6.1", [Page.Springboard])
check("no skips recorded", fake.last_reset_skips == [],
      repr(fake.last_reset_skips))
check("alert text untouched (no skip block)",
      alerts and "skipped" not in (alerts[-1].txt or ""),
      repr((alerts[-1].txt if alerts else None)))
check("no SKIPPED details block",
      "SKIPPED:" not in ((alerts[-1].detailed_txt or "") if alerts else ""))

print(f"\nALL {PASS} CHECKS PASSED")
