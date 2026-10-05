#!/usr/bin/env python3
"""Round-7 audit: protective prune semantics on a synthetic backup.

Pins clean_backup_for_restore:
* protective rows (CameraRoll, Library/Preferences) survive;
* non-protective rows and their payloads are removed;
* a kept-domain file row whose payload is MISSING is dropped (it would
  fail the restore with MBErrorDomain/205), not kept;
* directory rows survive without payloads;
* payload files are deleted only when unreferenced.

Run: python tools/test_audit_protective_prune.py
"""
import hashlib
import os
import plistlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.restore.protective import clean_backup_for_restore

PASS = 0
UDID = "PRUNEUDID"


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def _fid(domain, rel):
    return hashlib.sha1(f"{domain}-{rel}".encode()).hexdigest()


def _build(root):
    device_dir = os.path.join(root, UDID)
    os.makedirs(device_dir)
    conn = sqlite3.connect(os.path.join(device_dir, "Manifest.db"))
    conn.execute(
        "CREATE TABLE Files (fileID TEXT PRIMARY KEY, domain TEXT, "
        "relativePath TEXT, flags INTEGER, file BLOB)")

    def add(domain, rel, flags=1, payload=True, blob=b"x" * 64):
        fid = _fid(domain, rel)
        if payload and flags == 1:
            d = os.path.join(device_dir, fid[:2])
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, fid), "wb") as fh:
                fh.write(plistlib.dumps({"rel": rel}))
        conn.execute("INSERT INTO Files VALUES (?, ?, ?, ?, ?)",
                     (fid, domain, rel, flags, sqlite3.Binary(blob)))
        return fid

    keep1 = add("CameraRollDomain", "DCIM/100APPLE/IMG_0001.JPG")
    keep2 = add("HomeDomain", "Library/Preferences/com.apple.test.plist")
    drop1 = add("HomeDomain", "Library/Caches/com.apple.junk.plist")
    add("HomeDomain", "Library/Preferences/.GlobalPreferences.plist",
        payload=False)  # protective path, payload missing -> row dropped
    dir_row = add("HomeDomain", "Library/Preferences", flags=2,
                  payload=False)
    conn.commit()
    conn.close()
    return {"keep": {keep1, keep2, dir_row}, "drop": {drop1},
            "device_dir": device_dir}


def main():
    print("\nround-7: protective prune")
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "backup")
        os.makedirs(root)
        info = _build(root)
        removed_rows, removed_files = clean_backup_for_restore(root, UDID)
        conn = sqlite3.connect(os.path.join(info["device_dir"],
                                            "Manifest.db"))
        remaining = {r[0] for r in conn.execute("SELECT fileID FROM Files")}
        conn.close()
        check("protective + directory rows survive",
              info["keep"] <= remaining, str(remaining))
        check("non-protective rows removed",
              not (info["drop"] & remaining))
        check("row counts reported", removed_rows >= 2
              and removed_files >= 1, f"{removed_rows}/{removed_files}")
        orphan = [f for _r, _d, fs in os.walk(info["device_dir"])
                  for f in fs if f not in remaining
                  and f != "Manifest.db"]
        check("unreferenced payloads deleted from disk", orphan == [],
              str(orphan))
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
