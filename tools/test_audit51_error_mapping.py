#!/usr/bin/env python3
"""Fix Audit 51: show_apply_error must map real pymobiledevice3 10.7.1
exceptions, not dead str(e) text.

Pinned facts (verified against the installed pm3):
* ``PasswordRequiredError()`` stringifies to "" — the old
  ``"PasswordRequiredError" in str(e)`` branch could never fire.
* ``StartServiceError`` keeps its context on ``.service_name`` /
  ``.message``; ``str(e)`` is "" — the generic fallback printed an
  empty label.
* Nothing in this repo or in pymobiledevice3 raises an
  "Encrypted Backup MDM" text — that branch was dead and is removed.
* A ConnectionTerminatedError is a disconnect/stall, never evidence
  that "the file list is possibly corrupted".

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit51_error_mapping.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from pymobiledevice3.exceptions import (  # noqa: E402
    ConnectionTerminatedError, DeviceNotFoundError,
    PasscodeRequiredError, PasswordRequiredError, StartServiceError)

from src.devicemanagement.device_manager import show_apply_error  # noqa: E402
from src.restore.restore import FileToRestore  # noqa: E402

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}")


def map_error(exc, files_list=None):
    try:
        raise exc
    except Exception as e:  # noqa: BLE001 — mirrors the apply call sites
        return show_apply_error(e, files_list=files_list)


# --- (a) PasswordRequiredError via isinstance, not str(e) ------------------
print("PasswordRequiredError maps via isinstance (str(e) is empty)")
check("precondition: bare PasswordRequiredError has empty str",
      str(PasswordRequiredError()) == "")
alert = map_error(PasswordRequiredError())
check("bare PasswordRequiredError -> trust message",
      "password protected" in alert.txt, alert.txt)
check("bare PasswordRequiredError is not the generic empty label",
      not alert.txt.startswith("PasswordRequiredError:"), alert.txt)
alert = map_error(PasswordRequiredError("PasswordProtected"))
check("PasswordRequiredError with payload -> trust message",
      "password protected" in alert.txt, alert.txt)
alert = map_error(PasscodeRequiredError("PasscodeRequired", None, "27.0"))
check("PasscodeRequiredError -> trust message (device_errors parity)",
      "password protected" in alert.txt, alert.txt)

# --- (b) ConnectionTerminatedError: disconnect/stall, never "corrupted" ----
print("ConnectionTerminatedError reports a disconnect/stall with context")
files = [FileToRestore(contents=b"x", restore_path="a.plist",
                       domain="HomeDomain")]
alert = map_error(ConnectionTerminatedError("device dropped at 42%"),
                  files_list=files)
check("message says the connection was terminated",
      "connection" in alert.txt.lower() and "terminated" in alert.txt.lower(),
      alert.txt)
check("message names the phase (1 file being sent)",
      "1 file" in alert.txt, alert.txt)
check("message never blames a corrupted file list",
      "corrupted" not in (alert.txt + (alert.detailed_txt or "")).lower())
check("details keep the raw device error",
      "device dropped at 42%" in (alert.detailed_txt or ""))
check("details keep the staged file list",
      "a.plist" in (alert.detailed_txt or ""))

# --- StartServiceError / DeviceNotFoundError carry their context -----------
print("StartServiceError / DeviceNotFoundError name service / device")
alert = map_error(StartServiceError("com.apple.mobilebackup2",
                                    "service start refused"))
check("StartServiceError names the service",
      "com.apple.mobilebackup2" in alert.txt, alert.txt)
check("StartServiceError details keep the service message",
      "service start refused" in (alert.detailed_txt or ""))
alert = map_error(DeviceNotFoundError("00008101-TESTUDID"))
check("DeviceNotFoundError names the device",
      "00008101-TESTUDID" in alert.txt, alert.txt)

# --- dead "Encrypted Backup MDM" branch is gone ----------------------------
print("the dead Encrypted Backup MDM branch no longer relabels errors")
alert = map_error(ValueError("Encrypted Backup MDM is on"))
check("MDM text falls through to the generic identity",
      alert.txt.startswith("ValueError:"), alert.txt)
check("old Nugget/MDM label is not produced",
      "managed and MDM" not in alert.txt, alert.txt)

# --- regression: generic errors keep their identity ------------------------
print("unrelated errors keep their identity")
alert = map_error(ValueError("disk full while staging payload"))
check("generic error keeps type + message",
      alert.txt.startswith("ValueError:"), alert.txt)

print(f"\nALL {PASS} CHECKS PASSED")
