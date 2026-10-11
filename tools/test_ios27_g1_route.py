#!/usr/bin/env python3
"""Offline tests for the iOS 27 G1 apply route (user order 2026-10-11).

Covers the device-free logic in src/restore/ios27_g1.py:

* eligibility: only iOS 27.0 Developer Beta 1-9, 27.0 RC, 27.0 official
  stable, and 27.0.1 are supported; anything else -> "Not supported";
* the pre-apply warning text (English, blunt: bootloop risk, owner
  Adnan.120hz not responsible, backup required);
* the stall watchdog (fires only when the route goes quiet — no
  progress for WATCHDOG_STALL_SECONDS; a healthy backup is never cut
  off);
* payload planning: FileToRestore list -> injection tuples + audit
  manifest, with per-file tweak attribution derived from the journal
  (never hardcoded), and merge-onto-backup semantics for plist dicts;
* failure paths (offline): merge fallback when the backup base cannot
  be read (M11a), the byte-identity verification gate (M11b),
  corrupt staged payloads (M11c), corrupt backup base plists (M11d),
  empty/None contents and _coerce_bytes edge cases (M11e);
* backup-pool pruning incl. corrupt Manifest.db and stat() failures (N48);
* stall-watchdog semantics at phase boundaries; deadline-based paths
  are moot and noted as comments (N94/N95);
* build-allowlist composition and DB9 version-gate coverage (N49/N50).

Run: python tools/test_ios27_g1_route.py
"""
import hashlib
import errno
import inspect
import os
import pathlib
import plistlib
import sqlite3
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.restore.ios27_g1 as g1mod
from src.restore.ios27_g1 import (
    G1Watchdog,
    G1WatchdogExpired,
    IOS27_G1_SUPPORTED_BUILDS,
    IOS27_WARNING_TEXT,
    IOS27_WARNING_TITLE,
    NOT_SUPPORTED_MESSAGE,
    WATCHDOG_STALL_SECONDS,
    _coerce_bytes,
    _verify_injected_files,
    attribute_payloads_to_tweaks,
    is_ios27_g1_supported,
    plan_g1_payloads,
    prune_ios27_g1_backups,
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
check("watchdog stall default is 10 minutes",
      WATCHDOG_STALL_SECONDS == 10 * 60)

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

# --- watchdog (stall-based: fires only when the route goes quiet) ------
wd = G1Watchdog(stall_seconds=60)
check("fresh watchdog not stalled", wd.stalled_for() < 1)
wd.check("test-phase")  # must not raise
wd.note_progress()
time.sleep(0.02)
wd.check("test-phase")  # activity resets the clock; must not raise

stalled = G1Watchdog(stall_seconds=0.05)
time.sleep(0.08)
raised = False
try:
    stalled.check("backup")
except G1WatchdogExpired as e:
    raised = True
    check("expiry message names the stall (no progress)",
          "no progress" in str(e))
check("stalled watchdog raises G1WatchdogExpired", raised)
check("G1WatchdogExpired is an Exception", issubclass(G1WatchdogExpired, Exception))

# A healthy backup that keeps ticking is never interrupted: simulate a
# 45-minute backup with regular progress ticks.
long_wd = G1Watchdog(stall_seconds=600)
long_wd.last_progress_at = time.monotonic() - 2700  # 45 min since start
long_wd.note_progress()  # a tick arrives now
long_wd.check("backup")  # must not raise: the device is moving

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
backup_root = os.path.join(tmp, "backup")  # nested: merge .bak stays inside tmp
device_dir = os.path.join(backup_root, udid)
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
pm, _, mm = plan_g1_payloads([staged], backup_root=backup_root, udid=udid)
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
pn, _, mn = plan_g1_payloads([staged_new], backup_root=backup_root, udid=udid)
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

# --- M11a: merge fallback when the backup base cannot be read ---------------
# _merge_staged_onto_backup_plist catches ANY extraction exception and
# falls back to the staged file as-is (merged=False), logging LOUDLY.
# A Manifest.db that is valid sqlite but has no Files table makes
# extract_backup_file raise -> staged as-is, no crash, and no .bak
# (the original is preserved only after a successful extract).
m11a_tmp = tempfile.mkdtemp(prefix="ios27_g1_m11a_")
m11a_udid = "M11AUDID"
m11a_backup = os.path.join(m11a_tmp, "backup")
m11a_dev = os.path.join(m11a_backup, m11a_udid)
os.makedirs(m11a_dev)
_m11a_conn = sqlite3.connect(os.path.join(m11a_dev, "Manifest.db"))
_m11a_conn.execute("CREATE TABLE Junk (x TEXT)")  # valid sqlite, no Files table
_m11a_conn.commit()
_m11a_conn.close()

m11a_staged = FileToRestore(
    contents=plistlib.dumps({"StagedOnly": True}, fmt=plistlib.FMT_BINARY),
    restore_path="mobile/com.apple.M11a.plist",
    contents_path="",
    domain="ManagedPreferencesDomain",
)
m11a_p, _, m11a_m = plan_g1_payloads([m11a_staged],
                                     backup_root=m11a_backup, udid=m11a_udid)
check("M11a: extract failure -> staged as-is, no crash",
      len(m11a_p) == 1 and plistlib.loads(m11a_p[0][2]) == {"StagedOnly": True})
check("M11a: fallback not flagged merged", m11a_m[0]["merged"] is False)
check("M11a: no .bak written when extraction failed",
      not os.path.exists(os.path.join(m11a_tmp, "g1-merge-fallback-bak")))

# --- M11d: backup base plist exists but is not a dict -----------------------
# The backup's original IS preserved as .bak first; then the merge is
# skipped with a LOUD warning and the staged file is kept as-is
# (it will REPLACE the backup's copy at inject time).
m11d_tmp = tempfile.mkdtemp(prefix="ios27_g1_m11d_")
m11d_udid = "M11DUDID"
m11d_backup = os.path.join(m11d_tmp, "backup")
m11d_dev = os.path.join(m11d_backup, m11d_udid)
os.makedirs(m11d_dev)
_m11d_domain = "ManagedPreferencesDomain"
_m11d_rel = "mobile/com.apple.M11d.plist"
_m11d_fid = hashlib.sha1(f"{_m11d_domain}-{_m11d_rel}".encode()).hexdigest()
_m11d_conn = sqlite3.connect(os.path.join(m11d_dev, "Manifest.db"))
_m11d_conn.execute(
    "CREATE TABLE Files (fileID TEXT, domain TEXT, relativePath TEXT)")
_m11d_conn.execute("INSERT INTO Files VALUES (?, ?, ?)",
                   (_m11d_fid, _m11d_domain, _m11d_rel))
_m11d_conn.commit()
_m11d_conn.close()
_m11d_sub = os.path.join(m11d_dev, _m11d_fid[:2])
os.makedirs(_m11d_sub)
with open(os.path.join(_m11d_sub, _m11d_fid), "wb") as fh:
    fh.write(b"\x00\x01\x02garbage-not-a-plist")

m11d_staged = FileToRestore(
    contents=plistlib.dumps({"K": 1}, fmt=plistlib.FMT_BINARY),
    restore_path=_m11d_rel, contents_path="", domain=_m11d_domain)
m11d_p, _, m11d_m = plan_g1_payloads([m11d_staged],
                                     backup_root=m11d_backup, udid=m11d_udid)
check("M11d: corrupt base plist -> staged as-is, no crash",
      len(m11d_p) == 1 and plistlib.loads(m11d_p[0][2]) == {"K": 1})
check("M11d: corrupt base not flagged merged", m11d_m[0]["merged"] is False)
_m11d_baks = list(pathlib.Path(m11d_tmp, "g1-merge-fallback-bak").glob("*.bak"))
check("M11d: backup original preserved as .bak before replace",
      len(_m11d_baks) == 1)

# base plist parses but is not a dict (a plist array): same loud path
with open(os.path.join(_m11d_sub, _m11d_fid), "wb") as fh:
    fh.write(plistlib.dumps(["not", "a", "dict"], fmt=plistlib.FMT_BINARY))
m11d_p2, _, m11d_m2 = plan_g1_payloads([m11d_staged],
                                       backup_root=m11d_backup, udid=m11d_udid)
check("M11d: non-dict base plist -> staged as-is, no crash",
      plistlib.loads(m11d_p2[0][2]) == {"K": 1}
      and m11d_m2[0]["merged"] is False)
# NOTE: the .bak filename has 1-second timestamp resolution, so two
# replaces within the same second share one file (overwritten). Pin
# that the LATEST base (the array plist) is what got preserved.
_m11d_baks2 = list(pathlib.Path(m11d_tmp, "g1-merge-fallback-bak").glob("*.bak"))
_m11d_array_bytes = plistlib.dumps(["not", "a", "dict"],
                                   fmt=plistlib.FMT_BINARY)
check("M11d: second replace preserved the latest base as .bak",
      len(_m11d_baks2) >= 1
      and any(b.read_bytes() == _m11d_array_bytes for b in _m11d_baks2))

# --- M11c: corrupt staged payload -------------------------------------------
# Garbage bytes / non-dict staged plists are injected as-is (binary);
# the merge path is not even attempted for them.
m11c_garbage = FileToRestore(contents=b"\xff\xfe\x00garbage",
                             restore_path="/var/mobile/garbage.dat",
                             contents_path="", domain="HomeDomain")
m11c_arr = FileToRestore(
    contents=plistlib.dumps([1, 2, 3], fmt=plistlib.FMT_BINARY),
    restore_path="mobile/com.apple.M11c.plist",
    contents_path="", domain="ManagedPreferencesDomain")
m11c_p, _, m11c_m = plan_g1_payloads([m11c_garbage, m11c_arr],
                                     backup_root=m11d_backup, udid=m11d_udid)
check("M11c: garbage staged bytes injected as-is",
      m11c_p[0][2] == b"\xff\xfe\x00garbage" and m11c_m[0]["merged"] is False)
check("M11c: garbage staged marked binary",
      m11c_m[0]["contents_kind"] == "binary")
check("M11c: non-dict staged plist injected as-is",
      plistlib.loads(m11c_p[1][2]) == [1, 2, 3]
      and m11c_m[1]["merged"] is False)

# --- M11b: _verify_injected_files (incl. Manifest.db rows = N47) -------------
# The gate checks, per payload: blob on disk, byte equality, AND the
# Manifest.db row (domain, relativePath, flags). Problems are non-empty
# on any mismatch.
m11b_tmp = tempfile.mkdtemp(prefix="ios27_g1_m11b_")
m11b_udid = "M11BUDID"
m11b_backup = os.path.join(m11b_tmp, "backup")
m11b_dev = os.path.join(m11b_backup, m11b_udid)
os.makedirs(m11b_dev)
_v_domain, _v_rel = "HomeDomain", "Library/Preferences/m11b.dat"
_v_data = b"payload-bytes-123"
_v_fid = hashlib.sha1(f"{_v_domain}-{_v_rel}".encode()).hexdigest()
_v_sub = os.path.join(m11b_dev, _v_fid[:2])
os.makedirs(_v_sub)

_m11b_manifest = os.path.join(m11b_dev, "Manifest.db")


def _m11b_write_blob(data):
    with open(os.path.join(_v_sub, _v_fid), "wb") as fh:
        fh.write(data)


def _m11b_write_manifest(rows):
    # rows: list of (fileID, domain, relativePath, flags)
    if os.path.exists(_m11b_manifest):
        os.remove(_m11b_manifest)
    conn = sqlite3.connect(_m11b_manifest)
    conn.execute("CREATE TABLE Files (fileID TEXT, domain TEXT, "
                 "relativePath TEXT, flags INTEGER)")
    conn.executemany("INSERT INTO Files VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


_m11b_payloads = [(_v_domain, _v_rel, _v_data, 0o100644, 501, 501)]

_m11b_write_blob(_v_data)
_m11b_write_manifest([(_v_fid, _v_domain, _v_rel, 1)])
check("M11b: correct injection (bytes + manifest row) passes the gate",
      _verify_injected_files(m11b_backup, m11b_udid, _m11b_payloads) == [])

_m11b_write_blob(b"tampered!")
_prob = _verify_injected_files(m11b_backup, m11b_udid, _m11b_payloads)
check("M11b: byte mismatch flagged",
      len(_prob) == 1 and "content mismatch" in _prob[0])

os.remove(os.path.join(_v_sub, _v_fid))
_prob2 = _verify_injected_files(m11b_backup, m11b_udid, _m11b_payloads)
check("M11b: missing file flagged",
      len(_prob2) == 1 and "not found in backup" in _prob2[0])

_m11b_write_blob(_v_data)
_m11b_write_manifest([])  # bytes right, but no manifest row
_prob3 = _verify_injected_files(m11b_backup, m11b_udid, _m11b_payloads)
check("M11b: missing Manifest.db row flagged",
      len(_prob3) == 1 and "no Manifest.db row" in _prob3[0])

_m11b_write_manifest([(_v_fid, "WrongDomain", _v_rel, 1)])
_prob4 = _verify_injected_files(m11b_backup, m11b_udid, _m11b_payloads)
check("M11b: Manifest.db row domain/path mismatch flagged",
      len(_prob4) == 1 and "row mismatch" in _prob4[0])

_m11b_write_manifest([(_v_fid, _v_domain, _v_rel, 2)])
_prob5 = _verify_injected_files(m11b_backup, m11b_udid, _m11b_payloads)
check("M11b: Manifest.db flags != 1 flagged",
      len(_prob5) == 1 and "flags=2" in _prob5[0])

os.remove(_m11b_manifest)
_prob6 = _verify_injected_files(m11b_backup, m11b_udid, _m11b_payloads)
check("M11b: missing Manifest.db flagged",
      len(_prob6) == 1 and "Manifest.db is missing" in _prob6[0])

# --- M11e: empty/None contents + _coerce_bytes -------------------------------
# Empty/None contents are SKIPPED with a warn (zero-byte payloads are
# never planned); int/bool contents raise TypeError LOUDLY (the old
# silent null-bytes footgun is gone).
m11e_none = FileToRestore(contents=None, restore_path="/var/mobile/empty1.dat",
                           contents_path="", domain="HomeDomain")
m11e_empty = FileToRestore(contents=b"", restore_path="/var/mobile/empty2.dat",
                            contents_path="", domain="HomeDomain")
m11e_p, m11e_s, _ = plan_g1_payloads([m11e_none, m11e_empty])
check("M11e: contents=None skipped (zero-byte never planned)",
      len(m11e_p) == 0 and len(m11e_s) == 2
      and "empty contents" in m11e_s[0]["reason"])
check("M11e: contents=b'' skipped",
      "empty contents" in m11e_s[1]["reason"])


def _raises_typeerror(fn):
    try:
        fn()
    except TypeError:
        return True
    except Exception:
        return False
    return False


check("M11e: _coerce_bytes(int) raises TypeError",
      _raises_typeerror(lambda: _coerce_bytes(5)))
check("M11e: _coerce_bytes(bool) raises TypeError",
      _raises_typeerror(lambda: _coerce_bytes(True)))
m11e_int = FileToRestore(contents=5, restore_path="/var/mobile/int.dat",
                          contents_path="", domain="HomeDomain")
check("M11e: plan_g1_payloads propagates the TypeError (fail loud)",
      _raises_typeerror(lambda: plan_g1_payloads([m11e_int])))

# --- N48: prune_ios27_g1_backups --------------------------------------------
# prune_ios27_g1_backups resolves its pool via ios27_g1_backup_base()
# (user data dir); redirect it at a scratch dir for offline testing.
_prune_orig_base = g1mod.ios27_g1_backup_base


def _use_prune_base(path):
    g1mod.ios27_g1_backup_base = lambda udid: pathlib.Path(path)


def _make_usable_manifest(manifest_path, domain="HomeDomain",
                          rel="Library/Preferences/n48.plist"):
    conn = sqlite3.connect(str(manifest_path))
    conn.execute("CREATE TABLE Files (fileID TEXT, domain TEXT, "
                 "relativePath TEXT, flags INTEGER)")
    fid = hashlib.sha1(f"{domain}-{rel}".encode()).hexdigest()
    conn.execute("INSERT INTO Files VALUES (?, ?, ?, ?)",
                 (fid, domain, rel, 1))
    conn.commit()
    conn.close()


def _make_run(base, name, udid, manifest="usable", age_secs=0):
    # manifest: "usable" (valid db + >=1 row), "corrupt" (garbage bytes),
    # or None (no Manifest.db at all).
    run = pathlib.Path(base) / name / "device_backup" / udid
    run.mkdir(parents=True, exist_ok=True)
    if manifest == "usable":
        _make_usable_manifest(run / "Manifest.db")
    elif manifest == "corrupt":
        (run / "Manifest.db").write_bytes(b"\x00\x01 not a database")
    if age_secs:
        old = time.time() - age_secs
        os.utime(str(pathlib.Path(base) / name), (old, old))
    return pathlib.Path(base) / name


try:
    # keep=1 keeps the single newest USABLE run
    n48_tmp = tempfile.mkdtemp(prefix="ios27_g1_n48_")
    _use_prune_base(n48_tmp)
    _n48_udid = "N48UDID"
    _make_run(n48_tmp, "run-old", _n48_udid, age_secs=200)
    _make_run(n48_tmp, "run-new", _n48_udid, age_secs=10)
    removed = prune_ios27_g1_backups(_n48_udid, keep=1)
    check("N48: prune keep=1 keeps the newest usable run",
          removed == 1
          and not (pathlib.Path(n48_tmp) / "run-old").exists()
          and (pathlib.Path(n48_tmp) / "run-new").exists())

    # a corrupt Manifest.db is NOT usable -> incomplete -> reclaimed as
    # stale once older than a week (fail-closed _is_usable_backup).
    n48b_tmp = tempfile.mkdtemp(prefix="ios27_g1_n48b_")
    _use_prune_base(n48b_tmp)
    _make_run(n48b_tmp, "run-corrupt", _n48_udid,
              manifest="corrupt", age_secs=8 * 24 * 3600)
    removed_b = prune_ios27_g1_backups(_n48_udid, keep=1)
    check("N48: corrupt Manifest.db is incomplete and gets pruned",
          removed_b == 1
          and not (pathlib.Path(n48b_tmp) / "run-corrupt").exists())

    # fresh dir without Manifest.db is kept; a recent failed run is not
    # reclaimed before the 7-day grace period
    n48c_tmp = tempfile.mkdtemp(prefix="ios27_g1_n48c_")
    _use_prune_base(n48c_tmp)
    _make_run(n48c_tmp, "run-fresh-nodb", _n48_udid,
              manifest=None, age_secs=60)
    (pathlib.Path(n48c_tmp) / "stray.txt").write_text("cruft")
    removed_c = prune_ios27_g1_backups(_n48_udid, keep=1)
    check("N48: fresh incomplete dir kept, stray pool file removed",
          removed_c == 1
          and (pathlib.Path(n48c_tmp) / "run-fresh-nodb").exists()
          and not (pathlib.Path(n48c_tmp) / "stray.txt").exists())

    # missing pool base -> 0, no crash
    _use_prune_base(os.path.join(n48c_tmp, "does-not-exist"))
    check("N48: missing pool base returns 0",
          prune_ios27_g1_backups(_n48_udid, keep=1) == 0)

    # stat() raising OSError must not crash the prune: the stale loop
    # catches it, logs loudly, and leaves the dir in place. Patched at
    # the public-method level on purpose — pathlib internals differ
    # between 3.12 and 3.14 (is_dir() no longer funnels through
    # Path.stat()), so the test must not rely on that call chain.
    n48d_tmp = tempfile.mkdtemp(prefix="ios27_g1_n48d_")
    _use_prune_base(n48d_tmp)
    _make_run(n48d_tmp, "badstat", _n48_udid, manifest=None)
    _orig_stat = pathlib.Path.stat
    _orig_is_dir = pathlib.Path.is_dir
    _stat_calls = {"n": 0}

    def _flaky_stat(self):
        # Always fail for the "badstat" dir itself (children like
        # Manifest.db keep working so _is_usable_backup behaves).
        if self.name == "badstat":
            _stat_calls["n"] += 1
            raise OSError(errno.EIO, "simulated stat failure")
        return _orig_stat(self)

    def _flaky_is_dir(self):
        # Force the dir past the is_dir() filter so the stale loop's
        # OSError branch is actually exercised on every Python version.
        if self.name == "badstat":
            return True
        return _orig_is_dir(self)

    pathlib.Path.stat = _flaky_stat
    pathlib.Path.is_dir = _flaky_is_dir
    try:
        r_d = prune_ios27_g1_backups(_n48_udid, keep=1)
        check("N48: stat() OSError path exercised and survived",
              isinstance(r_d, int) and _stat_calls["n"] >= 1
              # os.path bypasses the patched pathlib.stat above
              and os.path.isdir(os.path.join(n48d_tmp, "badstat")))
    finally:
        pathlib.Path.stat = _orig_stat
        pathlib.Path.is_dir = _orig_is_dir
finally:
    g1mod.ios27_g1_backup_base = _prune_orig_base

# --- N94/N95: watchdog semantics at phase boundaries -------------------------
# Deadline-based paths are moot under the stall watchdog (noted, not
# tested): there is no total-time deadline, no timed_out flag, and no
# post-expiry restore-overrun state — a quiet route is stopped BEFORE
# the point of no return, and a restore in flight is never interrupted.
# Device-edge paths (encrypted-backup refusals, mid-backup stall,
# pre-restore stall, boot verification) need a device and cannot run
# offline; what IS pinned is the offline contract:
_n94_ok = True
try:
    _w = G1Watchdog(stall_seconds=60)
    for _phase in ("payload injection", "payload verification", "restore"):
        _w.check(_phase)      # previous phase must not have stalled
        _w.note_progress()    # entering a new phase counts as activity
except G1WatchdogExpired:
    _n94_ok = False
check("N94: phase-boundary check()/note_progress() do not raise when healthy",
      _n94_ok)
check("N94: deadline API removed from G1Watchdog",
      not any(hasattr(_w, a) for a in
              ("deadline", "remaining", "expired_once", "total_seconds")))
check("N94: no WATCHDOG_SECONDS module constant",
      not hasattr(g1mod, "WATCHDOG_SECONDS"))
# deliver_ios27_payload returns (backup_root, boot_verified): boot_verified
# is True/False after a requested reboot, None when no reboot was asked.
_dsig = inspect.signature(g1mod.deliver_ios27_payload)
check("N94: deliver returns (backup_root, boot_verified) tuple",
      _dsig.return_annotation is tuple
      and "boot_verified" in (g1mod.deliver_ios27_payload.__doc__ or ""))
# M13: the dead wrapper run_ios27_g1_route was deleted.
check("M13: run_ios27_g1_route deleted (no dead wrapper)",
      not hasattr(g1mod, "run_ios27_g1_route"))
# M2: post-reboot reconnect is verified with a FRESH lockdown session
# (wait_for_ios27_device_online); device-only, pinned by presence.
check("M2: wait_for_ios27_device_online exists (fresh-session reconnect check)",
      callable(getattr(g1mod, "wait_for_ios27_device_online", None)))

# --- N49/N50: build allowlist composition + DB9 coverage ---------------------
# N49 doc nit: the module docstring says "Developer Beta 1-9" while the
# build allowlist holds 8 beta builds (DB1-8) + RC + stable; DB9 is
# covered by the "27.0" version gate (the allowlist comment says so).
# Pinned from this file (source text cannot be edited here).
_betas = {b for b in IOS27_G1_SUPPORTED_BUILDS if b.startswith("24A5")}
check("N49: allowlist = 8 dev-beta builds + RC + stable",
      len(_betas) == 8 and "24A435" in IOS27_G1_SUPPORTED_BUILDS
      and "24A437" in IOS27_G1_SUPPORTED_BUILDS
      and len(IOS27_G1_SUPPORTED_BUILDS) == 10)
# N50: DB9 (build number not in the allowlist) is covered via the
# version gate — every 27.0 variant reports ProductVersion "27.0".
check("N50: DB9 (unlisted 27.0 build) supported via version gate",
      is_ios27_g1_supported("27.0", "24A9999db9"))
check("N50: 27.0 with empty build still supported",
      is_ios27_g1_supported("27.0", ""))

print(f"\n{ PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
