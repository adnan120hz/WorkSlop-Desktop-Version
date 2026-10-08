#!/usr/bin/env python3
"""Pins the show_apply_error mapping for the "Find My" alert.

Root cause pinned here (2026-10-09): a user with Find My actually ON
saw "Find My must be disabled" and reported it as a false positive.
It is not one. The mapping's first branch matches "Find My" in
``str(e)``, and app-authored guidance can never reach that check:

* ``NuggetException.__str__`` returns the message only — the Find My
  hint lives in ``detailed_text`` (src/restore/restore.py guidance),
  so str() stays clean;
* exception chaining (``raise ... from e``) never folds the cause or
  its detailed_text into str();
* wrappers that embed ``str(underlying)`` (the ``%1`` pattern in
  device_manager) therefore stay clean too.

The Find My alert can only fire on the RAW device error text (a
PyMobileDevice3Exception carrying the device's own refusal), which is
the behaviour to keep. To make that verifiable by the user, the
alert's Show Details now quotes the raw device error verbatim.

Run: python tools/test_apply_error_mapping.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from pymobiledevice3.exceptions import (  # noqa: E402
    ConnectionTerminatedError, PyMobileDevice3Exception)

from src.devicemanagement.device_manager import show_apply_error  # noqa: E402
from src.exceptions.nugget_exception import NuggetException  # noqa: E402

PASS = 0


def check(name, cond, extra=""):
    global PASS
    if not cond:
        raise AssertionError(f"FAIL: {name} {extra}")
    PASS += 1
    print(f"  ok: {name}")


# Verbatim shape of the guidance built in src/restore/restore.py —
# Find My appears ONLY in the detailed_text, never in the message.
FINDMY_HINT = (
    "The device dropped the connection during the data restore.\n\n"
    "Your data is not lost — the protective backup taken before "
    "the restore is kept on this computer.\n\n"
    "A common cause is Find My still being on: iOS refuses to "
    "restore a backup while Find My (iCloud ▸ Find My iPhone) is "
    "enabled. Turn Find My off (Settings ▸ [your name] ▸ Find My), "
    "keep the iPhone unlocked with the screen on, and apply again "
    "so the restore can complete.\n\n"
    "Do not erase the phone or set it up as new — the protective "
    "backup on this computer is the only copy of your data."
)
FINDMY_ALERT = "Find My must be disabled in order to use this tool."
DEVICE_REFUSAL = (
    "Device link error: {'ErrorCode': -27, 'ErrorDescription': "
    "'Restore failed: Find My iPhone must be turned off before "
    "this iPhone can be restored.'}"
)


def raise_restore_nugget():
    """The restore.py failure shape: friendly NuggetException chained
    `from` a raw device drop, Find My only in detailed_text."""
    try:
        raise ConnectionTerminatedError("device dropped mid-restore")
    except ConnectionTerminatedError as raw:
        raise NuggetException(
            "The protective backup could not be restored to the iPhone.",
            detailed_text=FINDMY_HINT) from raw


def map_error(make):
    """Raise the candidate inside an except block (exactly like the
    apply call sites) and return the mapped alert."""
    try:
        made = make()
        if isinstance(made, BaseException):
            raise made
    except Exception as e:  # noqa: BLE001 — mirrors the call sites
        return show_apply_error(e), type(e).__name__, str(e)
    raise AssertionError("candidate did not raise")


def test_app_authored_hint_never_maps_to_findmy():
    print("app-authored Find My hint (detailed_text) cannot trip the alert")
    try:
        raise_restore_nugget()
    except NuggetException as e:
        check("str(NuggetException) carries no Find My",
              "Find My" not in str(e), f"str={str(e)!r}")
    alert, etype, _ = map_error(raise_restore_nugget)
    check("maps to the NuggetException branch, verbatim",
          alert.txt == "The protective backup could not be restored "
          "to the iPhone.", f"txt={alert.txt!r}")
    check("detailed_text survives whole (guidance, not the label)",
          alert.detailed_txt == FINDMY_HINT)
    check("is NOT the Find My alert", alert.txt != FINDMY_ALERT)


def test_chained_and_wrapped_stay_clean():
    print("chaining / str()-embedding cannot absorb the hint either")

    def chained():
        try:
            raise_restore_nugget()
        except NuggetException as inner:
            raise RuntimeError("apply pass aborted") from inner

    alert, _, _ = map_error(chained)
    check("exception raised `from` the hint exception is not Find My",
          alert.txt != FINDMY_ALERT, f"txt={alert.txt!r}")

    def wrapped():
        try:
            raise_restore_nugget()
        except NuggetException as inner:
            return NuggetException(
                "Lock Screen Keys (Test): the .GlobalPreferences.plist "
                "read from the device could not be parsed (%1). "
                "Nothing was written.".replace("%1", str(inner)))

    alert, _, _ = map_error(wrapped)
    check("%1-embedded wrapper stays a NuggetException, not Find My",
          alert.txt.startswith("Lock Screen Keys (Test):")
          and alert.txt != FINDMY_ALERT, f"txt={alert.txt!r}")


def test_raw_device_findmy_maps_to_alert_with_raw_details():
    print("raw device refusal still maps to the Find My alert")
    alert, etype, _ = map_error(
        lambda: PyMobileDevice3Exception(DEVICE_REFUSAL))
    check("alert text is the Find My alert", alert.txt == FINDMY_ALERT)
    check("Show Details quotes the raw device error verbatim",
          DEVICE_REFUSAL in (alert.detailed_txt or ""),
          f"details={alert.detailed_txt!r}")
    check("Show Details keeps the how-to-disable guidance",
          "Disable Find My from Settings" in (alert.detailed_txt or ""))


def test_other_errors_never_become_findmy():
    print("unrelated failures never become the Find My alert")
    alert, _, _ = map_error(
        lambda: ValueError("disk full while staging payload"))
    check("generic error keeps its own identity",
          alert.txt.startswith("ValueError:") and alert.txt != FINDMY_ALERT)
    alert, _, _ = map_error(lambda: PyMobileDevice3Exception(
        "Device link error: {'ErrorCode': 205, 'ErrorDescription': "
        "'MBErrorDomain error 205'}"))
    check("device error without Find My text is not relabelled",
          alert.txt != FINDMY_ALERT, f"txt={alert.txt!r}")


def main():
    test_app_authored_hint_never_maps_to_findmy()
    test_chained_and_wrapped_stay_clean()
    test_raw_device_findmy_maps_to_alert_with_raw_details()
    test_other_errors_never_become_findmy()
    print(f"\n{PASS} checks passed")


if __name__ == "__main__":
    main()
