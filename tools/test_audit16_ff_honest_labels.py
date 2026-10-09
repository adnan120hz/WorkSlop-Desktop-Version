#!/usr/bin/env python3
"""Audit 16 — honest labels for the 8 Nugget FeatureFlag tweaks.

The eight ``FeatureFlagTweak`` objects in ``src/tweaks/nugget_lg.py``
(upstream Nugget ``load_featureflags()``) stage ``{'Enabled': False}``
records into FeatureFlags/Global.plist via partial restore on every
iOS version, but their UI labels used to promise the effect
("Disable Solarium (Liquid Glass) (Feature Flag Method)",
"Disable Liquid Glass in Documents Camera",
"Disable Liquid Glass in Share Sheet").

This test proves the Audit 16 fix:
  (a) every one of the 8 tweaks carries the new honest label —
      its per-tweak title in ``NUGGET_LG_TITLES`` and the label of
      the UI group switch that toggles it both start with
      "Write FeatureFlags:" and promise no on-device effect, and no
      old "Disable…" label survives in the FF display metadata;
  (b) the payload is byte-identical to before the relabel: same
      categories, flag names, inverted/list semantics per tweak, same
      staged dict, and the same binary-plist SHA-256 captured from
      the pre-change code (golden compare).

Run: QT_QPA_PLATFORM=offscreen python tools/test_audit16_ff_honest_labels.py
"""
import hashlib
import os
import plistlib
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.tweaks.nugget_lg import (  # noqa: E402
    NUGGET_LG_FF_GROUPS, NUGGET_LG_TITLES, _nugget_lg_definitions,
)
from src.tweaks.tweak_classes import FeatureFlagTweak  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402

_checks = []


def check(name, cond, extra=""):
    _checks.append((name, bool(cond)))
    print(("PASS" if cond else "FAIL"), name, extra)


# ---------------------------------------------------------------- golden
# Captured 2026-10-09 from the pre-relabel code: enabling all eight
# FeatureFlagTweaks and staging into one dict, serialized as a sorted
# binary plist. The relabel must not move a single byte of this.
GOLDEN_STAGED = {
    "SwiftUI": {"Solarium": {"Enabled": False}},
    "SpringBoard": {"SolariumElasticHUD": {"Enabled": False}},
    "IconServices": {"EnhancedGlass": {"Enabled": False},
                     "SolariumCornerRadius": {"Enabled": False}},
    "DocumentCamera": {"CaptureLiquidGlass": {"Enabled": False}},
    "Photos": {"SolariumGridMagicPocket": {"Enabled": False}},
    "AppleMediaServices": {"Solarium": {"Enabled": False}},
    "Sharing": {"ShareSheetSolarium": {"Enabled": False}},
    "Mail": {"SolariumSearch": {"Enabled": False}},
}
GOLDEN_SHA256 = "40a0a29b185c817791b441eefd1b4117f1f37bbcbc6a379a3762f7dc8adfb559"

# id -> (flag_category, flag_names, expected new per-tweak title)
EXPECTED = [
    (TweakID.NuggetSolariumFFSwiftUI, "SwiftUI", ["Solarium"],
     "Write FeatureFlags: SwiftUI/Solarium = off"),
    (TweakID.NuggetSolariumFFSpringBoard, "SpringBoard", ["SolariumElasticHUD"],
     "Write FeatureFlags: SpringBoard/SolariumElasticHUD = off"),
    (TweakID.NuggetSolariumFFIconServices, "IconServices",
     ["EnhancedGlass", "SolariumCornerRadius"],
     "Write FeatureFlags: IconServices/EnhancedGlass + SolariumCornerRadius = off"),
    (TweakID.NuggetSolariumFFDocumentCamera, "DocumentCamera",
     ["CaptureLiquidGlass"],
     "Write FeatureFlags: DocumentCamera/CaptureLiquidGlass = off"),
    (TweakID.NuggetSolariumFFPhotos, "Photos", ["SolariumGridMagicPocket"],
     "Write FeatureFlags: Photos/SolariumGridMagicPocket = off"),
    (TweakID.NuggetSolariumFFAppleMediaServices, "AppleMediaServices",
     ["Solarium"],
     "Write FeatureFlags: AppleMediaServices/Solarium = off"),
    (TweakID.NuggetSolariumFFSharing, "Sharing", ["ShareSheetSolarium"],
     "Write FeatureFlags: Sharing/ShareSheetSolarium = off"),
    (TweakID.NuggetSolariumFFMail, "Mail", ["SolariumSearch"],
     "Write FeatureFlags: Mail/SolariumSearch = off"),
]

OLD_GROUP_LABELS = [
    "Disable Solarium (Liquid Glass) (Feature Flag Method)",
    "Disable Liquid Glass in Documents Camera",
    "Disable Liquid Glass in Share Sheet",
]

defs = _nugget_lg_definitions()
ff_defs = {tid: tw for tid, tw in defs.items()
           if isinstance(tw, FeatureFlagTweak)}

# ------------------------------------------------------------- (a) labels
check("exactly the 8 Nugget FeatureFlag tweaks exist",
      set(ff_defs) == {tid for tid, *_ in EXPECTED},
      f"got {sorted(t.name for t in ff_defs)}")

for tid, category, flags, new_title in EXPECTED:
    title = NUGGET_LG_TITLES.get(tid)
    check(f"{tid.name}: per-tweak title is the honest Write label",
          title == new_title, repr(title))
    check(f"{tid.name}: title names its own category/flags",
          title is not None and category in title
          and all(f in title for f in flags))

group_of = {}
for label, ids in NUGGET_LG_FF_GROUPS:
    for tid in ids:
        group_of.setdefault(tid, []).append(label)

for tid, *_ in EXPECTED:
    labels = group_of.get(tid, [])
    check(f"{tid.name}: toggled by exactly one UI group switch",
          len(labels) == 1, repr(labels))
    if labels:
        check(f"{tid.name}: group label is honest Write wording",
              labels[0].startswith("Write FeatureFlags:")
              and "no device effect promised" in labels[0],
              repr(labels[0]))

all_ff_labels = [label for label, _ in NUGGET_LG_FF_GROUPS] \
    + list(NUGGET_LG_TITLES.values())
check("no FF display label starts with 'Disable'",
      not any(lbl.startswith("Disable") for lbl in all_ff_labels),
      repr([lbl for lbl in all_ff_labels if lbl.startswith("Disable")]))
check("no old 'Disable…' group label survives",
      not any(lbl in OLD_GROUP_LABELS for lbl in all_ff_labels))
check("every FF display label uses the Write verb",
      all(lbl.startswith("Write FeatureFlags:") for lbl in all_ff_labels))

# ------------------------------------------------------------ (b) payload
for tid, category, flags, _title in EXPECTED:
    tw = ff_defs[tid]
    check(f"{tid.name}: payload definition unchanged "
          f"({category}/{flags}, inverted, list)",
          tw.flag_category == category and tw.flag_names == flags
          and tw.inverted is True and tw.is_list is True)

staged = {}
for tid, *_ in EXPECTED:
    tw = ff_defs[tid]
    tw.set_enabled(True)
    staged = tw.apply_tweak(staged)
check("staged dict equals the pre-change golden dict",
      staged == GOLDEN_STAGED, repr(staged))

blob = plistlib.dumps(staged, fmt=plistlib.FMT_BINARY, sort_keys=True)
check("staged binary plist is byte-identical to the pre-change golden",
      hashlib.sha256(blob).hexdigest() == GOLDEN_SHA256,
      f"sha256={hashlib.sha256(blob).hexdigest()} len={len(blob)}")

for tid, *_ in EXPECTED:
    tw = ff_defs[tid]
    tw.set_enabled(False)
    check(f"{tid.name}: disabled stages nothing (payload gate intact)",
          tw.apply_tweak({}) == {})

failed = [c for c in _checks if not c[1]]
print(f"\n{len(_checks) - len(failed)}/{len(_checks)} checks passed")
if failed:
    print("FAILED:", [c[0] for c in failed])
sys.exit(1 if failed else 0)
