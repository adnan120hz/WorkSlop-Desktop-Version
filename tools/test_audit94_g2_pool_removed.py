#!/usr/bin/env python3
"""Audit 94: the write-only G2 rollback pool is gone; live routes survive.

The pool's only writer was ``save_g2_original_if_absent`` on the
full-route apply path; its only reader (``load_g2_original``) had zero
callers anywhere in src/+tools/. Both are now removed. This pins:

* the three pool symbols no longer exist on ``lg_disable``;
* the full-route module no longer references them (no orphan write);
* the surviving Squair/Latest rollback planners still build payloads
  from fresh captures, removing exactly their own keys.

Run: python tools/test_audit94_g2_pool_removed.py
"""
import os
import plistlib
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "LGD_STORE_DIR", tempfile.mkdtemp(prefix="lgd_audit94_store_"))

FAILURES = []


def check(label, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + label + (f" {extra}" if extra else ""))
    if not cond:
        FAILURES.append(label)


def main():
    from src.tweaks import lg_disable

    for name in ("save_g2_original_if_absent", "load_g2_original",
                 "g2_original_plist_path"):
        check(f"lg_disable.{name} removed", not hasattr(lg_disable, name))

    src = os.path.join(os.path.dirname(__file__), "..",
                       "src", "restore", "lgd_full.py")
    with open(src, encoding="utf-8") as fh:
        body = fh.read()
    check("lgd_full has no G2 pool write",
          "save_g2_original_if_absent" not in body)
    check("lgd_full rebase merge intact",
          "g2_device_base" in body and "merged.update" in body)

    # No pool file is produced by merely exercising the module/store.
    check("no .g2-original.plist in the store",
          not any(n.endswith(".g2-original.plist")
                  for n in os.listdir(lg_disable._store_dir())))

    from src.tweaks import lg_latest, lg_squair

    gp = {"keep": 1, **dict.fromkeys(lg_squair.GP_KEYS, True)}
    payloads, _note = lg_squair.plan_squair_rollback_payloads(gp)
    check("squair rollback still plans one payload", len(payloads) == 1)
    parsed = plistlib.loads(payloads[0][2])
    check("squair rollback removes only its keys",
          parsed == {"keep": 1}, str(parsed))

    gp = {"keep": 1, **dict.fromkeys(lg_latest.GP_KEYS, True)}
    swiftui = {"keep": 2, lg_latest.SWIFTUI_KEY: True}
    payloads, _note = lg_latest.plan_latest_rollback_payloads(gp, swiftui)
    by_path = {p[1]: plistlib.loads(p[2]) for p in payloads}
    check("latest rollback still covers both files", len(by_path) == 2)
    check("latest rollback removes only its GP keys",
          by_path[lg_latest.G1_REL_PATH] == {"keep": 1})
    check("latest rollback removes only its SwiftUI key",
          by_path[lg_latest.SWIFTUI_REL_PATH] == {"keep": 2})

    print(f"\n{11 - len(FAILURES)}/11 checks passed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
