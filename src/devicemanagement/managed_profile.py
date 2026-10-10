"""Experimental generator for a FeatureFlags configuration profile (.mobileconfig).

Binary evidence (iOS 26.6.1 / 23G82, verified by firmware research; see
``~/workspace/goals/workslop-desktop/hidden_files/ff-primitive-2026-10-10/``):

- ``MCFeatureFlagsPayload`` in ManagedConfiguration: PayloadType EXACT
  ``com.apple.system.featureflags`` (cstring cluster @ file offset 0x125186,
  23G82). Same string exists in 23B85.
- Payload content key names, clustered with the PayloadType literal in the
  23G82 ManagedConfiguration cstrings and mirrored in FeatureFlagsSupport:
  ``Features`` (array), per-feature ``Domain`` / ``FeatureName`` /
  ``TargetRelease`` / ``MinimumPhase``; ``Disclosures`` (array) with
  ``DisclosureName`` / ``Disclosed``; ``Subscriptions`` (array) with
  ``SubscriptionClass`` / ``SubscriptionContents``. FeatureFlagsSupport also
  carries the ``Enabled`` key string (1 hit, 23G82).
- ``-[MCFeatureFlagsPayload isAllowedToWriteFeatureFlags]`` (23G82
  @0x1a94a83a8) has an identical form in 23B85 — the gate is intact. Retail
  devices are therefore expected to REJECT this profile at install time.

Honesty contract for this module:
- Only the strings above are used inside the payload. NO other payload
  keys are invented.
- The value SEMANTICS of the inner keys (e.g. what ``Enabled``=true does to
  a given Domain/FeatureName) are NOT proven from the binary — they are
  named from the strings and must stay labelled UNTESTED everywhere.
- Effect on a retail iPhone: NOT PROVEN. Installation likely rejected.
"""

import plistlib
import uuid

#: Verified binary string (ManagedConfiguration, 23G82 + 23B85).
FEATURE_FLAGS_PAYLOAD_TYPE = "com.apple.system.featureflags"

#: Payload content key names verified as binary strings (see module docstring).
#: Value semantics are untested — these are the names, not proven behavior.
FEATURE_KEYS = ("Domain", "FeatureName", "Enabled")
DISCLOSURE_KEYS = ("DisclosureName", "Disclosed")
SUBSCRIPTION_KEYS = ("SubscriptionClass", "SubscriptionContents")

GATE_NAME = "isAllowedToWriteFeatureFlags"

INSTALL_INSTRUCTIONS = """How to use this profile (manual install — nothing is installed silently):

1. Transfer the .mobileconfig file to your iPhone (AirDrop, email to yourself, or Files).
2. On the iPhone, open Settings. A "Profile Downloaded" entry appears near the top — tap it, then Install, and confirm the prompts.
3. Reboot the iPhone. Feature flags are read when processes launch, so a reboot is required to judge any effect.
4. Check whether the feature state changed.

IMPORTANT — read before installing:
- EXPERIMENTAL / UNTESTED. The effect of this profile on a retail iPhone is NOT proven.
- Firmware research shows the isAllowedToWriteFeatureFlags gate exists and is intact on iOS 26.6.1, so installation will likely be REJECTED on an ordinary (non-supervised, non-MDM) device. A rejection is the expected outcome there — it is not a bug in this generator.
- There is no API for any app to install a configuration profile silently on a retail iPhone. Installation is always manual, in Settings, by you.
- The FeatureFlags key names inside the payload come from firmware binary strings (iOS 26.6.1). Their exact value semantics on a device are untested.
"""


def _new_uuid() -> str:
    return str(uuid.uuid4()).upper()


def build_feature_flags_profile(
    display_name: str,
    organization: str,
    features: list,
    profile_identifier: str = "com.workslop.featureflags.experimental",
) -> dict:
    """Build the full .mobileconfig plist dict.

    ``features``: list of ``{"Domain": str, "FeatureName": str, "Enabled": bool}``.
    Raises ValueError on invalid input.
    """
    errors = validate_feature_entries(features)
    if errors:
        raise ValueError("; ".join(errors))
    if not display_name or not display_name.strip():
        raise ValueError("Profile display name must not be empty.")

    feature_dicts = [
        {
            "Domain": f["Domain"],
            "FeatureName": f["FeatureName"],
            "Enabled": bool(f["Enabled"]),
        }
        for f in features
    ]

    payload = {
        "PayloadType": FEATURE_FLAGS_PAYLOAD_TYPE,
        "PayloadVersion": 1,
        "PayloadIdentifier": f"{profile_identifier}.payload",
        "PayloadUUID": _new_uuid(),
        "PayloadDisplayName": "FeatureFlags (experimental)",
        "PayloadDescription": (
            "Experimental FeatureFlags payload. UNTESTED on retail devices; "
            f"the {GATE_NAME} gate is intact on iOS 26.6.1, so installation "
            "will likely be rejected on ordinary devices."
        ),
        # Key names below are verified binary strings (see module docstring).
        # Value semantics are untested.
        "Features": feature_dicts,
        "Disclosures": [],
        "Subscriptions": [],
    }

    profile = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": profile_identifier,
        "PayloadUUID": _new_uuid(),
        "PayloadDisplayName": display_name.strip(),
        "PayloadDescription": (
            "Experimental WorkSlop-generated configuration profile carrying a "
            "FeatureFlags payload. UNTESTED — effect on a retail iPhone is NOT "
            "proven; installation is likely rejected on ordinary devices."
        ),
        "PayloadContent": [payload],
    }
    if organization and organization.strip():
        profile["PayloadOrganization"] = organization.strip()
    return profile


def validate_feature_entries(features: list) -> list:
    """Return a list of human-readable problems; empty list means valid."""
    errors = []
    if not isinstance(features, list) or not features:
        errors.append("Add at least one feature entry (Domain + FeatureName).")
        return errors
    for i, f in enumerate(features):
        tag = f"Feature #{i + 1}"
        if not isinstance(f, dict):
            errors.append(f"{tag}: entry must be a dict.")
            continue
        domain = f.get("Domain", "")
        name = f.get("FeatureName", "")
        if not isinstance(domain, str) or not domain.strip():
            errors.append(f"{tag}: Domain must be a non-empty string.")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{tag}: FeatureName must be a non-empty string.")
        if "Enabled" in f and not isinstance(f["Enabled"], bool):
            errors.append(f"{tag}: Enabled must be true/false.")
    return errors


def write_mobileconfig(profile: dict, path: str) -> None:
    """Write the profile dict to ``path`` as an XML .mobileconfig plist."""
    with open(path, "wb") as fh:
        plistlib.dump(profile, fh, fmt=plistlib.FMT_XML, sort_keys=False)


def read_mobileconfig(path: str) -> dict:
    """Read a .mobileconfig back (used by tests / verification)."""
    with open(path, "rb") as fh:
        return plistlib.load(fh)
