#!/usr/bin/env python3
"""Round-12 audit: FeatureFlags staging semantics (Nugget LG set).

* every Nugget FeatureFlagTweak, when enabled, writes
  {category: {flag: {'Enabled': bool}}} with the inverted semantics
  the upstream definitions declare;
* a disabled FeatureFlagTweak writes nothing (B6 fix);
* the staged structure is plist-serializable.

Eligibility/MobileGestalt gating itself is pinned by rounds 10/15.

Run: python tools/test_audit_featureflags.py
"""
import os
import plistlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.tweaks.nugget_lg import _nugget_lg_definitions
from src.tweaks.tweak_classes import FeatureFlagTweak

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-12: FeatureFlags")
    defs = _nugget_lg_definitions()
    ff = {tid: tw for tid, tw in defs.items()
          if isinstance(tw, FeatureFlagTweak)}
    check("Nugget set has FeatureFlag tweaks", len(ff) >= 8, str(len(ff)))

    staged = {}
    for tid, tw in ff.items():
        tw.set_enabled(True)
        staged = tw.apply_tweak(staged)
    ok = True
    for tid, tw in ff.items():
        cat = staged.get(tw.flag_category)
        if not isinstance(cat, dict):
            ok = False
            break
        for flag in tw.flag_names:
            entry = cat.get(flag)
            if tw.is_list:
                if not isinstance(entry, dict) or \
                        entry.get("Enabled") is not (not tw.inverted):
                    ok = False
            elif entry is not (not tw.inverted):
                ok = False
    check("enabled FF tweaks stage inverted Enabled values", ok)
    plistlib.dumps(staged, fmt=plistlib.FMT_BINARY)
    check("staged FeatureFlags plist-serializes", True)

    tw = next(iter(ff.values()))
    tw.set_enabled(False)
    check("disabled FF tweak writes nothing", tw.apply_tweak({}) == {})

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
