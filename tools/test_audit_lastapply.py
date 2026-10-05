#!/usr/bin/env python3
"""Round-18 audit: last-apply record + sparse signature.

* sparse_signature is order-independent and content-sensitive;
* PosterBoard AppDomain files and iOS 27 scaffolding never count;
* the per-device record writes, loads, and clears through the real
  store (an unchanged apply can skip Phase 2; a reset clears it).

Run: python tools/test_audit_lastapply.py
"""
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = tempfile.mkdtemp(prefix="workslop-r18-")
os.environ["XDG_DATA_HOME"] = _tmp

from PySide6.QtCore import QCoreApplication

from src.restore import lastapply

PASS = 0
PB = "AppDomain-com.apple.PosterBoard"


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def _f(domain, path, contents):
    return types.SimpleNamespace(domain=domain, restore_path=path,
                                 contents=contents)


def main():
    print("\nround-18: lastapply")
    app = QCoreApplication.instance() or QCoreApplication([])
    app.setApplicationName("WorkSlop Desktop")

    files = [
        _f("HomeDomain", "Library/Preferences/a.plist", b"one"),
        _f(PB, "Library/x.sqlite3", b"wallpaper"),
        _f("HomeDomain", "Library/Preferences/.GlobalPreferences.plist",
           b"gp-copy"),
        _f("SysSharedContainerDomain-systemgroup.com.apple.configurationprofiles",
           "Library/ConfigurationProfiles/CloudConfigurationDetails.plist",
           b"cc"),
    ]
    sig = lastapply.sparse_signature(files)
    check("only real tweak files are signed",
          list(sig) == ["HomeDomain/Library/Preferences/a.plist"], str(sig))
    sig2 = lastapply.sparse_signature(list(reversed(files)))
    check("signature is order-independent", sig == sig2)
    changed = [_f("HomeDomain", "Library/Preferences/a.plist", b"two")]
    check("content change changes the signature",
          lastapply.sparse_signature(changed) != sig)

    lastapply.write_lastapply("UDID18", sig)
    check("record round-trips", lastapply.load_lastapply("UDID18") == sig)
    check("unknown device has empty record",
          lastapply.load_lastapply("NOPE") == {})
    lastapply.clear_lastapply("UDID18")
    check("clear removes the record", lastapply.load_lastapply("UDID18") == {})

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
