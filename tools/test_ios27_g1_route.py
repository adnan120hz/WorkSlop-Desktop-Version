#!/usr/bin/env python3
"""Offline tests for the iOS 27 G1 apply route (user order 2026-10-11).

Covers the device-free logic in src/restore/ios27_g1.py:

* eligibility: only iOS 27.0 Developer Beta 1-9, 27.0 RC, 27.0 official
  stable, and 27.0.1 are supported; anything else -> "Not supported";
* the pre-apply warning text (English, blunt: bootloop risk, owner
  Adnan.120hz not responsible, backup required);
* the 12-minute watchdog (expiry raises G1WatchdogExpired);
* payload planning: FileToRestore list -> injection tuples + audit
  manifest, with per-file tweak attribution derived from the journal
  (never hardcoded), and merge-onto-backup semantics for plist dicts.

Run: python tools/test_ios27_g1_route.py
"""
import hashlib
import os
import plistlib
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.restore.ios27_g1 import (
    G1Watchdog,
    G1WatchdogExpired,
    IOS27_WARNING_TEXT,
    IOS27_WARNING_TITLE,
    NOT_SUPPORTED_MESSAGE,
    WATCHDOG_SECONDS,
    attribute_payloads_to_tweaks,
    is_ios27_g1_supported,
    plan_g1_payloads,
)
from src.utils.file_to_restore import FileToRestore

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {name}")


# --- eligibility ------------------------------------------------------------
check("watchdog is 12 minutes", WATCHDOG_SECONDS == 12 * 60)

check("27.0 (any build) supported", is_ios27_g1_supported("27.0", "24A0000x"))
check("27.0.1 supported", is_ios27_g1_supported("27.0.1", "whatever"))
check("27.0 beta build 24A5355q supported", is_ios27_g1_supported("26.9", "24A5355q"))
check("27.0 RC build 24A435 supported", is_ios27_g1_supported("26.9", "24A435"))
check("27.0 stable build 24A437 supported", is_ios27_g1_supported("", "24A437"))
check("27.1 rejected", not is_ios27_g1_supported("27.1", "25A0000x"))
check("27.2 rejected", not is_ios27_g1_supported("27.2", "24B5084k"))
check("27.2 beta build rejected", not is_ios27_g1_supported("27.2", "24B5089g"))
check("26.6.1 rejected", not is_ios27_g1_supported("26.6.1", "23G82"))
check("18.x rejected", not is_ios27_g1_supported("18.7", "22H123"))
check("empty version/build rejected", not is_ios27_g1_supported("", ""))
check("garbage rejected", not is_ios27_g1_supported("banana", "apple"))

check("'Not supported' message text",
      NOT_SUPPORTED_MESSAGE.startswith("Not supported"))

# --- warning text -----------------------------------------------------------
check("warning title mentions iOS 27", "iOS 27" in IOS27_WARNING_TITLE)
check("warning mentions bootloop", "BOOTLOOP" in IOS27_WARNING_TEXT)
check("warning names the owner", "Adnan.120hz" in IOS27_WARNING_TEXT)
check("warning disclaims responsibility",
      "NOT responsible" in IOS27_WARNING_TEXT)
check("warning requires a backup", "backup" in IOS27_WARNING_TEXT.lower())
check("warning mentions unencrypted backup",
      "Encrypt local backup" in IOS27_WARNING_TEXT)
check("warning names Abort/Resume", "Abort" in IOS27_WARNING_TEXT
      and "Resume" in IOS27_WARNING_TEXT)

# --- watchdog ----------------------------------------------------------------
wd = G1Watchdog(total_seconds=60)
check("watchdog not expired at start", wd.remaining() > 0)
wd.check("test-phase")  # must not raise

expired = G1Watchdog(total_seconds=0.05)
time.sleep(0.08)
raised = False
try:
    expired.check("backup")
except G1WatchdogExpired as e:
    raised = True
    check("expiry message names the 12-minute limit (or custom)",
          "safety limit" in str(e) or "minute" in str(e))
check("expired watchdog raises G1WatchdogExpired", raised)
check("G1WatchdogExpired is an Exception", issubclass(G1WatchdogExpired, Exception))

# --- payload planning ---------------------------------------------------------
f1 = FileToRestore(
    contents=plistlib.dumps({"StagedKey": True}, fmt=plistlib.FMT_BINARY),
    restore_path="mobile/com.apple.Test.plist",
    contents_path="",
    domain="ManagedPreferencesDomain",
    owner=501, group=501,
)
f2 = FileToRestore(
    contents=b"\x00\x01binary",
    restore_path="/var/mobile/Library/Preferences/blob.dat",
    contents_path="",
    domain="HomeDomain",
    owner=501, group=501,
)
f3 = FileToRestore(  # empty domain -> skipped
    contents=b"x",
    restore_path="/var/mobile/x",
    contents_path="",
    domain="",
)
f4 = FileToRestore(  # directory record -> skipped
    contents=None,
    restore_path="/var/mobile/dir",
    contents_path="",
    domain="HomeDomain",
    is_dir=True,
)
payloads, skipped, manifest = plan_g1_payloads([f1, f2, f3, f4])

check("two payloads planned", len(payloads) == 2)
check("two skipped", len(skipped) == 2)
check("payload 1 domain/rel",
      payloads[0][0] == "ManagedPreferencesDomain"
      and payloads[0][1] == "mobile/com.apple.Test.plist")
check("payload 1 contents round-trip",
      plistlib.loads(payloads[0][2]) == {"StagedKey": True})
check("payload 1 mode is regular-file 0644", payloads[0][3] == 0o100644)
check("payload 2 binary contents intact", payloads[1][2] == b"\x00\x01binary")
check("manifest aligned with payloads",
      len(manifest) == 2 and manifest[0]["rel_path"] == payloads[0][1])
check("manifest has merged flag", manifest[0]["merged"] is False)
check("manifest records size", manifest[0]["size"] == len(payloads[0][2]))
check("skipped records carry reasons",
      all("reason" in s for s in skipped))

# string contents are coerced to bytes
fs = FileToRestore(contents="plain", restore_path="/var/mobile/a",
                   contents_path="", domain="HomeDomain")
p, _, _ = plan_g1_payloads([fs])
check("str contents coerced to bytes", p[0][2] == b"plain")

# --- merge onto the backup's own copy -----------------------------------------
tmp = tempfile.mkdtemp(prefix="ios27_g1_test_")
udid = "TESTUDID"
device_dir = os.path.join(tmp, udid)
os.makedirs(device_dir)
domain = "ManagedPreferencesDomain"
rel = "mobile/com.apple.Merge.plist"
file_id = hashlib.sha1(f"{domain}-{rel}".encode("utf-8")).hexdigest()
conn = sqlite3.connect(os.path.join(device_dir, "Manifest.db"))
conn.execute("CREATE TABLE Files (fileID TEXT, domain TEXT, relativePath TEXT)")
conn.execute("INSERT INTO Files VALUES (?, ?, ?)", (file_id, domain, rel))
conn.commit()
conn.close()
sub = os.path.join(device_dir, file_id[:2])
os.makedirs(sub)
existing = {"ExistingKey": "keep-me", "Shared": "old"}
with open(os.path.join(sub, file_id), "wb") as fh:
    fh.write(plistlib.dumps(existing, fmt=plistlib.FMT_BINARY))

staged = FileToRestore(
    contents=plistlib.dumps({"Staged": 1, "Shared": "new"},
                            fmt=plistlib.FMT_BINARY),
    restore_path=rel,  # staged restore_path is already the rel path
    contents_path="",
    domain=domain,
)
pm, _, mm = plan_g1_payloads([staged], backup_root=tmp, udid=udid)
check("merge produced one payload", len(pm) == 1)
merged_dict = plistlib.loads(pm[0][2])
check("merge keeps existing keys", merged_dict.get("ExistingKey") == "keep-me")
check("merge keeps staged keys", merged_dict.get("Staged") == 1)
check("staged wins on conflict", merged_dict.get("Shared") == "new")
check("manifest flags merged", mm[0]["merged"] is True)

# file absent from the backup -> injected new, staged as-is
staged_new = FileToRestore(
    contents=plistlib.dumps({"Only": "staged"}, fmt=plistlib.FMT_BINARY),
    restore_path="/var/Managed Preferences/mobile/com.apple.Absent.plist",
    contents_path="",
    domain=domain,
)
pn, _, mn = plan_g1_payloads([staged_new], backup_root=tmp, udid=udid)
check("absent file injected as-is",
      plistlib.loads(pn[0][2]) == {"Only": "staged"})
check("absent file not flagged merged", mn[0]["merged"] is False)

# --- tweak -> file attribution -------------------------------------------------
journal_entries = [
    {"tweak_id": "DisableGlass", "operation": {
        "location": "/var/Managed Preferences/mobile/com.apple.Test.plist"}},
    {"tweak_id": "AnimSpeed", "operation": {
        "location": "/var/Managed Preferences/mobile/com.apple.Test.plist"}},
    {"tweak_id": "Other", "operation": {
        "location": "/var/mobile/Library/Preferences/other.plist"}},
]
attributed = attribute_payloads_to_tweaks(payloads, journal_entries)
check("attribution covers every payload", len(attributed) == len(payloads))
check("shared plist attributed to both tweaks",
      set(attributed[0]["tweaks"]) == {"DisableGlass", "AnimSpeed"})
check("unattributed payload falls back to <staging>",
      attributed[1]["tweaks"] == ["<staging>"])
check("attribution order follows payload order",
      attributed[0]["rel_path"] == payloads[0][1])

print(f"\n{ PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
