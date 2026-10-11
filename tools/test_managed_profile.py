#!/usr/bin/env python3
"""Offscreen checks for the experimental FeatureFlags .mobileconfig generator.

Honesty-first: these tests pin (1) the verified binary payload structure,
(2) the input validation, (3) the plist round-trip, and (4) that every
user-facing string carries the experimental/untested/rejected warnings —
so the feature can never silently become a "works" claim.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    app = QApplication.instance() or QApplication([])

    from src.devicemanagement import managed_profile as mp

    # --- verified binary constants -------------------------------------
    check("PayloadType is the exact verified binary string",
          mp.FEATURE_FLAGS_PAYLOAD_TYPE == "com.apple.system.featureflags")
    check("gate name pinned", mp.GATE_NAME == "isAllowedToWriteFeatureFlags")

    feats = [{"Domain": "com.apple.UIKit", "FeatureName": "ExampleFlag", "Enabled": True}]

    # --- envelope --------------------------------------------------------
    profile = mp.build_feature_flags_profile("Test Profile", "TestOrg", feats)
    check("top-level PayloadType is Configuration",
          profile["PayloadType"] == "Configuration")
    check("PayloadVersion is 1", profile["PayloadVersion"] == 1)
    check("top-level UUID present", bool(profile.get("PayloadUUID")))
    check("PayloadContent is a one-item list",
          isinstance(profile.get("PayloadContent"), list)
          and len(profile["PayloadContent"]) == 1)
    check("organization passed through",
          profile.get("PayloadOrganization") == "TestOrg")

    inner = profile["PayloadContent"][0]
    check("inner PayloadType is the verified binary string",
          inner["PayloadType"] == "com.apple.system.featureflags")
    check("inner payload has its own UUID",
          bool(inner.get("PayloadUUID")) and inner["PayloadUUID"] != profile["PayloadUUID"])

    # --- inner key names: verified binary strings, semantics untested -----
    check("Features key present", "Features" in inner)
    check("Disclosures key present", "Disclosures" in inner)
    check("Subscriptions key present", "Subscriptions" in inner)
    f0 = inner["Features"][0]
    check("feature entry carries Domain", f0["Domain"] == "com.apple.UIKit")
    check("feature entry carries FeatureName", f0["FeatureName"] == "ExampleFlag")
    check("feature entry carries Enabled bool", f0["Enabled"] is True)
    check("no invented top-level keys inside payload",
          set(inner) <= {"PayloadType", "PayloadVersion", "PayloadIdentifier",
                         "PayloadUUID", "PayloadDisplayName", "PayloadDescription",
                         "Features", "Disclosures", "Subscriptions"})

    # --- validation ------------------------------------------------------
    check("empty features rejected",
          mp.validate_feature_entries([]) != [])
    check("missing Domain rejected",
          mp.validate_feature_entries([{"Domain": "", "FeatureName": "X", "Enabled": True}]) != [])
    check("missing FeatureName rejected",
          mp.validate_feature_entries([{"Domain": "d", "FeatureName": " ", "Enabled": True}]) != [])
    check("non-bool Enabled rejected",
          mp.validate_feature_entries([{"Domain": "d", "FeatureName": "n", "Enabled": "yes"}]) != [])
    check("valid entries pass", mp.validate_feature_entries(feats) == [])
    try:
        mp.build_feature_flags_profile("  ", "o", feats)
        raise SystemExit("should have raised")
    except ValueError:
        check("empty display name raises ValueError", True)

    # --- plist round-trip -------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "ff.mobileconfig")
        mp.write_mobileconfig(profile, path)
        check("file written", os.path.isfile(path))
        back = mp.read_mobileconfig(path)
        check("round-trip preserves PayloadType",
              back["PayloadContent"][0]["PayloadType"] == "com.apple.system.featureflags")
        check("round-trip preserves feature entry",
              back["PayloadContent"][0]["Features"][0]["FeatureName"] == "ExampleFlag")

    # --- honest labels: never become a "works" claim ----------------------
    # (user order 2026-10-11: the in-app dialog was removed; the honest
    # labels now live in the generator module itself, which is kept as
    # the source for the website's static generator)
    notice_src = open(os.path.join(
        os.path.dirname(__file__), "..", "src", "devicemanagement",
        "managed_profile.py")).read()
    for needle in ["UNTESTED", "NOT proven", "REJECTED",
                   "isAllowedToWriteFeatureFlags",
                   "value semantics", "untested"]:
        check(f"module carries honest phrase {needle!r}", needle in notice_src)
    lowered = notice_src.lower().replace("workslop", "")
    for claim in ["it works", "this works", "will work", "proven to work",
                  "guaranteed to work", "working method"]:
        check(f"module never claims {claim!r}", claim not in lowered)
    for needle in ["NOT proven", "likely be REJECTED", "isAllowedToWriteFeatureFlags",
                   "manual"]:
        check(f"instructions carry honest phrase {needle!r}", needle in mp.INSTALL_INSTRUCTIONS)

    print(f"\nALL {PASS} CHECKS PASSED")


main()
