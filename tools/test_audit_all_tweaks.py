#!/usr/bin/env python3
"""Round-5 audit: EVERY registry tweak, structurally.

For every non-disabled spec in src/tweaks/registry.py:

* it builds through the loader's real ``_build_spec``;
* plist tweaks stage (enabled) into a dict that plistlib can serialize;
* its FileLocation maps to a real backup domain (known exceptions only);
* version range parses and is not inverted;
* spec ids are unique, and every TweakID is covered by a spec, the
  hard-coded tweaks dict, or the removed/tombstone list;
* same-location+key value conflicts without mutual exclusion are
  reported (a pair that can fight over one key in one apply).

Run: python tools/test_audit_all_tweaks.py
"""
import os
import plistlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from packaging.version import Version

from src.restore.path_mapping import split_path_into_domain
from src.tweaks import tweak_loader
from src.tweaks.registry import SPECS, SPECS_BY_ID
from src.tweaks.tweak_classes import AdvancedPlistTweak, BasicPlistTweak
from src.tweaks.tweak_names import TweakID
from src.tweaks.tweaks import tweaks as base_tweaks

PASS = 0

# FileLocations that intentionally do not map to a backup domain.
NO_DOMAIN_OK = set()


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-5: all registry tweaks")
    active = [s for s in SPECS if not s.disabled]
    check("registry has specs", len(active) >= 76, f"{len(active)} active")
    check("spec ids unique among active specs",
          len({s.id for s in active}) == len(active))

    built = {}
    for spec in active:
        tw = tweak_loader._build_spec(spec)
        built[spec.id] = tw
    check("every active spec builds via _build_spec", len(built) == len(active))

    staged_locations = {}
    no_domain = []
    for spec in active:
        tw = built[spec.id]
        if not isinstance(tw, (BasicPlistTweak, AdvancedPlistTweak)):
            continue
        domain, _rel = split_path_into_domain(spec.location.value)
        if domain is None and spec.location not in NO_DOMAIN_OK:
            no_domain.append((spec.id.name, spec.location.value))
        try:
            tw.set_enabled(True)
        except Exception:
            pass
        result = tw.apply_tweak({})
        assert isinstance(result, dict), spec.id
        for loc, payload in result.items():
            assert isinstance(payload, dict), (spec.id, loc)
            plistlib.dumps(payload, fmt=plistlib.FMT_BINARY)
            staged_locations.setdefault(loc, payload)
    check("every plist tweak stages a plist-serializable dict", True)
    check("every plist FileLocation maps to a backup domain",
          no_domain == [], str(no_domain))

    bad_ranges = []
    for spec in active:
        try:
            lo = Version(spec.min_version) if spec.min_version else None
            hi = Version(spec.max_version) if spec.max_version else None
        except Exception:
            bad_ranges.append((spec.id.name, "unparsable"))
            continue
        if lo and hi and lo > hi:
            bad_ranges.append((spec.id.name, f"{lo}>{hi}"))
    check("no inverted/unparsable version ranges", bad_ranges == [],
          str(bad_ranges))

    # TweakID coverage: spec, hard-coded dict, one of the loader
    # factories, or removed tombstone. The loaders populate the shared
    # tweaks dict at runtime; run the offline-safe ones for real.
    from src.tweaks.capabilities import is_removed_tweak
    tweak_loader.load_plist_tweaks()
    try:
        tweak_loader.load_daemons()
    except Exception:
        pass
    covered = set(SPECS_BY_ID) | set(base_tweaks)
    covered |= set(tweak_loader.get_mobilegestalt_tweaks())
    tweak_loader.load_risky()
    covered |= set(base_tweaks)
    from src.tweaks.nugget_lg import _nugget_lg_definitions
    covered |= set(_nugget_lg_definitions())
    # Registered only through device-bound loaders (load_rdar_fix,
    # load_eligibility, load_mobilegestalt's spoof set): these need a
    # real device/decision object, so they are covered by construction
    # in tweak_loader.py rather than instantiated here.
    covered |= {
        TweakID.UseFloatingTabBar, TweakID.RdarFix, TweakID.EUEnabler,
        TweakID.AIEligibility, TweakID.SpoofModel, TweakID.SpoofHardware,
        TweakID.SpoofCPU, TweakID.SuppressDICompletely,
    }
    # Retired duplicate names resolve to one canonical writer.
    from src.tweaks.capabilities import DEPRECATED_TWEAK_ALIASES
    covered |= set(DEPRECATED_TWEAK_ALIASES)
    uncovered = []
    for tid in TweakID:
        if tid in covered:
            continue
        try:
            if is_removed_tweak(tid):
                continue
        except Exception:
            pass
        uncovered.append(tid.name)
    check("every TweakID is covered or tombstoned", uncovered == [],
          str(uncovered))

    # Same location+key conflicts without mutual exclusion.
    by_key = {}
    for spec in active:
        by_key.setdefault((spec.location, spec.key), []).append(spec)
    conflicts = []
    for (loc, key), specs in by_key.items():
        if len(specs) < 2:
            continue
        values = {repr(s.value) for s in specs}
        if len(values) < 2:
            continue
        ids = {s.id for s in specs}
        excluded = any(
            set(s.excludes or ()) & ids for s in specs)
        if not excluded:
            conflicts.append((loc.name, key, [s.id.name for s in specs]))
    check("no un-excluded same-key value conflicts", conflicts == [],
          str(conflicts))

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
