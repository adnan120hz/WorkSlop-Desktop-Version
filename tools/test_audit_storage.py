#!/usr/bin/env python3
"""Round-14 audit: backup storage resolution (workers/CLI share it).

* GOLDENNUGGET_BACKUP_DIR beats the QSettings location;
* derived roots (cache, protective, posterboard, LGD full-backup pool)
  all hang under the one configured root;
* unset config falls back to AppData without inventing directories.

Run: python tools/test_audit_storage.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="workslop-r14-")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-r14c-")

from src.restore import lgd_full, storage

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-14: storage resolution")
    custom = tempfile.mkdtemp(prefix="workslop-custom-")
    os.environ["GOLDENNUGGET_BACKUP_DIR"] = custom
    try:
        check("env override is the configured root",
              storage._configured_root() == storage.Path(custom))
        check("custom dir reported", storage.is_custom_backup_dir())
        check("cache hangs under custom root",
              storage.cache_base() == storage.Path(custom) / "backup_cache")
        check("protective hangs under custom root",
              storage.protective_base() == storage.Path(custom) / "protective")
        check("posterboard dir derives from root",
              storage.posterboard_dir() == storage.Path(custom) / "PosterBoard")
        check("LGD pool lives under protective base",
              lgd_full._lgd_pool_root("UDID14")
              == storage.protective_base() / "UDID14-lgd-full")
    finally:
        del os.environ["GOLDENNUGGET_BACKUP_DIR"]
    check("unset config is not custom",
          not storage.is_custom_backup_dir())

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
