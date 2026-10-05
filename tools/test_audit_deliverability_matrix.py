#!/usr/bin/env python3
"""Round-15 audit: deliverability matrix for EVERY spec on 26.6.1.

For each active registry spec, tweak_deliverability on the audit
target (iOS 26.6.1 / 23G83, iPhone) must match the spec's own
declared constraints exactly:

* requires_gestalt specs -> blocked (decision locked there);
* version-capped specs -> blocked with the version reason;
* everything else -> deliverable. An unexpected block is the user's
  "cannot activate it, cannot test it" failure; an unexpected open
  is a gate that silently stopped working.

Run: python tools/test_audit_deliverability_matrix.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from packaging.version import Version

from src.tweaks import tweak_loader
from src.tweaks.capabilities import requires_gestalt, tweak_deliverability
from src.tweaks.registry import SPECS

PASS = 0
VER, BUILD = "26.6.1", "23G83"


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-15: deliverability matrix @ 26.6.1/23G83")
    active = [s for s in SPECS if not s.disabled]
    mismatches = []
    blocked_expected = 0
    for spec in active:
        tw = tweak_loader._build_spec(spec)
        ok, reason, _msg = tweak_deliverability(
            spec.id, VER, BUILD, True, tweak=tw)
        expect_block = None
        if spec.max_version and Version(VER) > Version(spec.max_version):
            expect_block = "VERSION_ABOVE_MAX"
        elif spec.min_version and Version(VER) < Version(spec.min_version):
            expect_block = "VERSION_BELOW_MIN"
        elif requires_gestalt(spec.id, tw):
            expect_block = "GESTALT"
        if expect_block:
            blocked_expected += 1
            if ok:
                mismatches.append((spec.id.name, "open", expect_block))
            elif expect_block != "GESTALT" and reason != expect_block:
                mismatches.append((spec.id.name, reason, expect_block))
        elif not ok:
            mismatches.append((spec.id.name, reason, "deliverable"))
    check("matrix matches declared constraints for every spec",
          mismatches == [], str(mismatches))
    check("gestalt/version gates actually engage on 26.6.1",
          blocked_expected > 0, f"{blocked_expected} blocked of {len(active)}")

    # No device evidence: ordinary tweaks open, gestalt stays closed.
    wrong = []
    for spec in active:
        tw = tweak_loader._build_spec(spec)
        ok, _r, _m = tweak_deliverability(spec.id, "", "", True, tweak=tw)
        if requires_gestalt(spec.id, tw) and ok:
            wrong.append(spec.id.name)
    check("unknown device never opens gestalt tweaks", wrong == [],
          str(wrong))

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
