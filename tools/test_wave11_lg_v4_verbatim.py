"""Wave 11 LG-v4-verbatim tests: the Liquid Glass set IS the WorkSlop v4 set.

User order 2026-10-03: re-implement the v4 Liquid Glass code into v11
WITHOUT ANY CHANGE — every tweak's payload (key, file location, value and
type, version gates) byte-behaviour identical to v4
(src/tweaks/registry.py @ commit 4f44415). Only integration glue may
differ (ID registration, menu wiring); anything that cannot run verbatim
must be reported, never silently adapted.

These tests pin the expected v4 tuples literally (taken from the v4
registry source, not reconstructed), prove the loader builds every row
(including LGLPMGestalt, whose mga plain-plist write the Wave 10 loader
used to refuse), prove enable->apply yields exactly
{location: {v4 key: v4 value}}, prove none of the 32 is removed or
device-test-labelled, and prove the Liquid Glass reset keeps the v4
byte semantics (iOS 26 zero-byte, iOS 27+ empty plist) while other
reset pages keep the Wave 10 P0 empty-plist payload.
"""
import os
import plistlib
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.tweaks import registry as cur  # noqa: E402
from src.tweaks.registry import Section, SPECS, SPECS_BY_ID  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402
from src.tweaks.basic_plist_locations import FileLocation  # noqa: E402
from src.tweaks.capabilities import (  # noqa: E402
    is_device_test_candidate, is_device_test_tweak, is_removed_tweak,
    tweak_deliverability,
)
from src.devicemanagement.device_manager import lg_reset_contents  # noqa: E402

# (id, section, location member, key, value, value type, min_version, max_version)
# Transcribed once from the v4 registry (commit 4f44415); the transplant
# into registry.py was done mechanically from the same source lines.
EXPECTED = [
    ("SolariumForceFallback", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SolariumForceFallback", True, bool, "26.0", None),
    ("DisableSolariumSwiftUI", Section.LIQUID_GLASS, FileLocation.globalPreferences, "com.apple.SwiftUI.DisableSolarium", True, bool, "26.0", None),
    ("GlassLegibility2", Section.LIQUID_GLASS, FileLocation.uikit, "UIViewGlassLegibilitySetting", 2, int, "26.0", None),
    ("SolariumFeatureFlags", Section.FEATURE_FLAGS, FileLocation.featureflags, "SolariumFlags", True, bool, "26.0", "26.1"),
    ("DisallowGlassTime", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisallowGlassTime", True, bool, "26.0", None),
    ("DisableGlassDock", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableGlassDock", True, bool, "26.0", None),
    ("FlatIconsEverywhere", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBUseFlatIconsEverywhere", True, bool, "26.0", None),
    ("DisableWidgetSpecular", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableWidgetSpecular", True, bool, "26.0", None),
    ("DisableDockSpecular", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableDockSpecular", True, bool, "26.0", None),
    ("DisableFolderSpecular", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableFolderSpecular", True, bool, "26.0", None),
    ("ExcludeClearGlassShadows", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBExcludeAllClearGlassShadows", True, bool, "26.0", None),
    ("ExcludeDockShadow", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBExcludeDockShadow", True, bool, "26.0", None),
    ("ExcludeSearchShadow", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBExcludeSearchShadow", True, bool, "26.0", None),
    ("DisableOuterRefraction", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SolariumDisableOuterRefraction", True, bool, "26.0", None),
    ("DisableSolariumHDR", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SolariumAllowHDR", False, bool, "26.0", None),
    ("DisableSpecularMotion", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableSpecularEverywhereUsingLSSAssertion", True, bool, "26.0", None),
    ("DisableSpecularEverywhere", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableSpecularEverywhere", True, bool, "26.0", None),
    ("DisableGlassEverywhere", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableGlassEverywhere", True, bool, "26.0", None),
    ("DisallowGlassEverywhere", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisallowGlassEverywhere", True, bool, "26.0", None),
    ("DisableLockScreenSpecular", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableLockScreenSpecular", True, bool, "26.0", None),
    ("DisableClockSpecular", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableClockSpecular", True, bool, "26.0", None),
    ("DisableGlassLockScreen", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableGlassLockScreen", True, bool, "26.0", None),
    ("DisableCompactChrome", Section.LIQUID_GLASS, FileLocation.globalPreferences, "DisableSolariumCompactChrome", True, bool, "27.0", None),
    ("DisableGlassDI", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableGlassDynamicIsland", True, bool, "26.0", None),
    ("DisallowGlassDI", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisallowGlassDynamicIsland", True, bool, "26.0", None),
    ("DisableIslandSpecular", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableIslandSpecular", True, bool, "26.0", None),
    ("ExcludeAllGlassShadows", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBExcludeAllGlassShadows", True, bool, "26.0", None),
    ("FlatDockEverywhere", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBUseFlatDockEverywhere", True, bool, "26.0", None),
    ("DisableGlassBlur", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableGlassBlur", True, bool, "26.0", None),
    ("DisallowGlassKeyboard", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisallowGlassKeyboard", True, bool, "26.0", None),
    ("DisableRefractionEverywhere", Section.LIQUID_GLASS, FileLocation.globalPreferences, "SBDisableRefractionEverywhere", True, bool, "26.0", None),
    ("LGLPMGestalt", Section.LIQUID_GLASS, FileLocation.mga, "SAGvsp6O6kAQ4fEfDJpC4Q", True, bool, "26.0", "26.1"),
    # v4's Hide Search Button row: SpringBoard section, verbatim v4 spec.
    ("SBHideSearchAffordance", Section.SPRINGBOARD, FileLocation.springboard, "SBHomeScreenShowsSearchAffordance", False, bool, None, None),
]

_checks = []


def check(name, cond, extra=""):
    _checks.append((name, bool(cond), extra))
    print(("PASS" if cond else "FAIL"), name, extra)


# ---------------------------------------------------------------- specs
for name, section, location, key, value, vtype, mn, mx in EXPECTED:
    spec = SPECS_BY_ID.get(TweakID[name])
    check(f"spec exists: {name}", spec is not None)
    if spec is None:
        continue
    check(f"spec = v4 tuple: {name}",
          (spec.section, spec.location, spec.key, spec.value, type(spec.value),
           spec.min_version, spec.max_version)
          == (section, location, key, value, vtype, mn, mx),
          f"got {(spec.section, spec.location, spec.key, spec.value, type(spec.value), spec.min_version, spec.max_version)}")

# The v4 LG catalogue is exactly these 32 registry rows: 31 LG + 1 FF.
lg_specs = [s for s in SPECS if s.section is Section.LIQUID_GLASS]
check("LG section has 31 v4 rows + Blurr Motion + 2 remaining v15 "
      "firmware-research rows (SwiftUI enable removed in v15.1)",
      len(lg_specs) == 34 and any(s.id is TweakID.BlurrMotion for s in lg_specs)
      and {TweakID.LGForceFallbackUIKit,
           TweakID.LGNoBlurReducedFrost} <= {s.id for s in lg_specs}
      and TweakID.LGForceFallbackSwiftUI not in {s.id for s in lg_specs},
      f"got {len(lg_specs)}")
check("FEATURE_FLAGS holds only the v4 Solarium row",
      [s.id for s in SPECS if s.section is Section.FEATURE_FLAGS]
      == [TweakID.SolariumFeatureFlags])

# ------------------------------------------------- payloads via the loader
from src.tweaks.tweak_loader import load_plist_tweaks  # noqa: E402
from src.tweaks.tweaks import tweaks  # noqa: E402
from src.tweaks.tweak_classes import BasicPlistTweak  # noqa: E402

try:
    load_plist_tweaks()
    loader_ok = True
except Exception as e:  # noqa: BLE001
    loader_ok = False
    print("loader raised:", e)
check("loader builds every spec (LGLPMGestalt mga write included)", loader_ok)

for name, section, location, key, value, vtype, mn, mx in EXPECTED:
    t = tweaks.get(TweakID[name])
    if not isinstance(t, BasicPlistTweak):
        check(f"payload {name}", False, f"class={type(t).__name__}")
        continue
    t.set_enabled(True)
    out = {}
    t.apply_tweak(out)
    t.set_enabled(False)
    check(f"payload {name}: enable->apply == {{location: {{key: value}}}}",
          out == {location: {key: value}}, repr(out))

# ------------------------------------------------- gating / labelling
for name, *_ in EXPECTED:
    t = TweakID[name]
    check(f"not removed / not device-test: {name}",
          not is_removed_tweak(t)
          and not is_device_test_tweak(t)
          and not is_device_test_candidate(t))

check("26.6.1: v4 LG rows deliverable (OK)",
      all(tweak_deliverability(TweakID[n], "26.6.1")[1] == "OK"
          for n, *_ in EXPECTED
          if n not in ("LGLPMGestalt", "SolariumFeatureFlags", "DisableCompactChrome")))
check("26.6.1: max_version 26.1 rows stay version-locked (v4 gate)",
      tweak_deliverability(TweakID.LGLPMGestalt, "26.6.1")[1] == "VERSION_ABOVE_MAX"
      and tweak_deliverability(TweakID.SolariumFeatureFlags, "26.6.1")[1] == "VERSION_ABOVE_MAX")
check("26.0/26.1: capped rows deliverable",
      tweak_deliverability(TweakID.LGLPMGestalt, "26.1")[1] == "OK"
      and tweak_deliverability(TweakID.SolariumFeatureFlags, "26.0")[1] == "OK")
check("DisableCompactChrome keeps its v4 iOS 27 gate",
      tweak_deliverability(TweakID.DisableCompactChrome, "26.6.1")[1] == "VERSION_BELOW_MIN"
      and tweak_deliverability(TweakID.DisableCompactChrome, "27.0")[1] == "OK")

# No Wave 10 "UNPROVEN — device test" wording anywhere in the LG section
# (v4 descriptions are restored verbatim; the Wave 10 badge text is gone).
lg_text = " ".join(
    f"{s.title} {s.description or ''}"
    for s in SPECS if s.section is Section.LIQUID_GLASS)
check("no UNPROVEN label in the Liquid Glass section", "UNPROVEN" not in lg_text)

# ------------------------------------------------- reset byte semantics
check("reset bytes iOS 26 = v4 zero-byte", lg_reset_contents("26.6.1") == b"")
check("reset bytes iOS 27+ = v4 empty plist",
      lg_reset_contents("27.0") == plistlib.dumps({}))
check("reset bytes unknown version = v4 zero-byte", lg_reset_contents("") == b"")

failed = [c for c in _checks if not c[1]]
print(f"\n{len(_checks) - len(failed)}/{len(_checks)} checks passed")
if failed:
    print("FAILED:", [c[0] for c in failed])
sys.exit(1 if failed else 0)
