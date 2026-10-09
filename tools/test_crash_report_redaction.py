#!/usr/bin/env python3
"""Audit 64: crash-report redaction.

_build_issue_body is the single assembly point behind both outgoing
surfaces (clipboard via _full_report, GitHub via _build_issues_url).
A report built from input containing a raw device UDID and absolute
(username-bearing) paths must contain neither raw, while safe debug info
(app version, iOS version, traceback file/line structure) survives.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_crash_report_redaction.py
"""
import os
import sys
import traceback as tb_mod
from urllib.parse import unquote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


UDID_DASHED = "00008101-001A2B3C4D5E6F7A"
UDID_LEGACY = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
UDID_LABELLED = "deadbeefcafe1234"
UNIX_SECRET = "/home/budi/secret/proj"
WIN_SECRET = r"C:\Users\budi\secret"
IOS_VERSION = "iOS 26.6.1"

print("\ncrash report redaction (Audit 64)")
import src.exceptions.crash_handler as ch  # noqa: E402

# --- unit: the redactor itself ---
check("labelled UDID redacted",
      UDID_LABELLED not in ch._redact_sensitive(f"UDID: {UDID_LABELLED} failed")
      and "<UDID>" in ch._redact_sensitive(f"UDID: {UDID_LABELLED} failed"))
check("dashed UDID redacted", UDID_DASHED not in ch._redact_sensitive(f"dev {UDID_DASHED}"))
check("legacy 40-hex UDID redacted",
      UDID_LEGACY not in ch._redact_sensitive(f"dev {UDID_LEGACY}"))
check("unix path redacted, basename kept",
      ch._redact_sensitive(f'File "{UNIX_SECRET}/x.py", line 9') ==
      'File "<path>/x.py", line 9')
check("windows path redacted, basename kept",
      ch._redact_sensitive(rf"open {WIN_SECRET}\y.py") == r"open <path>/y.py")
check("safe text untouched",
      ch._redact_sensitive(f"WorkSlop Desktop on {IOS_VERSION} build 14")
      == f"WorkSlop Desktop on {IOS_VERSION} build 14")
check("URLs untouched",
      ch._redact_sensitive("see https://github.com/adnan120hz/desk/issues")
      == "see https://github.com/adnan120hz/desk/issues")

# --- integration: report assembled from hostile input ---
try:
    raise ValueError(f"restore failed for {UDID_LEGACY} at {UNIX_SECRET}/restore.py")
except ValueError:
    exc_type, exc_value, exc_tb = sys.exc_info()
summary, tb_text = ch._format_error(exc_type, exc_value, exc_tb)
tb_text += (
    f'\n  File "{UNIX_SECRET}/src/exceptions/crash_handler.py", line 145, in _handle_crash\n'
    f"    open(r'{WIN_SECRET}\\backup.zip')\n"
    f"Device {UDID_DASHED} running {IOS_VERSION}\n"
)
info = ch._classify(exc_type, exc_value)

fake_log = (
    f"2026-10-09 | DEBUG | device udid={UDID_DASHED} on {IOS_VERSION}\n"
    f"2026-10-09 | DEBUG | wrote {UNIX_SECRET}/out.plist and {WIN_SECRET}\\log.txt\n"
)
ch.get_log_tail = lambda max_chars=64 * 1024: fake_log
ch.get_log_path = lambda: f"{UNIX_SECRET}/Logs/workslop_2026-10-09.log"

body = ch._build_issue_body(info, summary, tb_text, include_log=True)
full = ch._full_report(info, summary, tb_text)
url_body = unquote(ch._build_issues_url(info, summary, tb_text).split("&body=", 1)[1])

for label, text in (("issue body", body), ("clipboard report", full),
                    ("github url body", url_body)):
    check(f"{label}: no raw dashed UDID", UDID_DASHED not in text)
    check(f"{label}: no raw legacy UDID", UDID_LEGACY not in text)
    check(f"{label}: no raw unix path", UNIX_SECRET not in text and "/home/budi" not in text)
    check(f"{label}: no raw windows path", WIN_SECRET not in text and r"C:\Users\budi" not in text)
    check(f"{label}: <UDID> placeholder present", "<UDID>" in text)
    check(f"{label}: <path> placeholder present", "<path>" in text)
    check(f"{label}: log path header redacted", "workslop_2026-10-09.log" in text
          and f"{UNIX_SECRET}/Logs" not in text)

check("header unchanged", body.startswith("## WorkSlop Desktop Error Report"))
check("iOS version survives", IOS_VERSION in body)
check("app version survives", "**App version:**" in body and "unknown" not in body.split("\n")[2])
check("traceback structure survives",
      "Traceback (most recent call last)" in body and "ValueError" in body
      and "crash_handler.py" in body and "line 145" in body)
check("severity/fault survive",
      f"**Severity:** {info['severity']}" in body and f"**Likely cause:** {info['fault']}" in body)

print(f"\nALL {PASS} CHECKS PASSED")
