"""Generator for a WebClip bookmark configuration profile (.mobileconfig).

This is the SECOND managed profile alongside the experimental FeatureFlags
generator (``managed_profile.py``). Unlike the FeatureFlags profile, a WebClip
payload installs normally on a retail iPhone: after install, a "WorkSlop"
bookmark icon appears on the home screen and opens the WorkSlop website when
tapped.

Collision safety with the FeatureFlags profile:
- This profile uses PayloadIdentifier ``com.workslop.webclip.bookmark``
  (inner payload: ``com.workslop.webclip.bookmark.payload``); the FeatureFlags
  profile uses ``com.workslop.featureflags.experimental``. Different
  identifiers, so both profiles can be installed side by side on one iPhone.
- PayloadDisplayName differs: "WorkSlop Bookmark" vs the FeatureFlags name.

Payload keys used are the standard Apple WebClip payload keys only
(PayloadType ``com.apple.webClip.managed``):
- ``Label``: text shown under the home-screen icon.
- ``URL``: the website opened when the icon is tapped.
- ``IsRemovable``: lets the user delete the bookmark like a normal app icon.
- ``Precomposed``: true so iOS does not add its own gloss to the icon.
- ``Icon`` (optional): PNG bytes for the home-screen icon artwork.
No other payload keys are used.
"""

import os
import plistlib
import uuid

#: Standard Apple WebClip payload type (public, documented).
WEBCLIP_PAYLOAD_TYPE = "com.apple.webClip.managed"

#: PayloadIdentifier namespace for this profile — distinct from the
#: FeatureFlags profile's "com.workslop.featureflags.experimental".
WEBCLIP_PROFILE_IDENTIFIER = "com.workslop.webclip.bookmark"

#: Website opened when the bookmark icon is tapped.
WORKSLP_WEBSITE_URL = "https://workslop-nu.vercel.app"

#: Home-screen label under the icon.
WEBCLIP_LABEL = "WorkSlop"

#: Icon artwork bundled in the repo (512x512 RGBA PNG). The WorkSlop app icon
#: itself is never changed; this file is only embedded as the WebClip icon.
WORKSLP_ICON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "assets", "workslop-icon.png",
)

WEBCLIP_INSTALL_INSTRUCTIONS = """How to use this profile (manual install — nothing is installed silently):

1. Transfer the .mobileconfig file to your iPhone (AirDrop, email to yourself, or Files).
2. On the iPhone, open Settings. A "Profile Downloaded" entry appears near the top — tap it, then Install, and confirm the prompts.
3. A "WorkSlop" bookmark icon appears on your home screen. Tap it to open the WorkSlop website.
4. The bookmark is removable: long-press it and delete it like a normal app icon. To remove the profile, go to Settings → General → VPN & Device Management and remove the profile.

This is a normal WebClip profile — it installs on retail iPhones and does NOT change any system setting. There is no API for any app to install a configuration profile silently on a retail iPhone. Installation is always manual, in Settings, by you.
"""


def _new_uuid() -> str:
    return str(uuid.uuid4()).upper()


def _read_icon_bytes(icon_path: str = None) -> bytes:
    path = icon_path or WORKSLP_ICON_PATH
    with open(path, "rb") as fh:
        return fh.read()


def build_webclip_profile(
    display_name: str = "WorkSlop Bookmark",
    organization: str = "",
    label: str = WEBCLIP_LABEL,
    url: str = WORKSLP_WEBSITE_URL,
    icon_path: str = None,
    include_icon: bool = True,
) -> dict:
    """Build the full .mobileconfig plist dict for the WorkSlop WebClip.

    Raises ValueError on invalid input, FileNotFoundError if the icon is
    requested but missing.
    """
    if not display_name or not display_name.strip():
        raise ValueError("Profile display name must not be empty.")
    if not label or not label.strip():
        raise ValueError("Bookmark label must not be empty.")
    if not url or not url.strip().lower().startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://.")

    payload = {
        "PayloadType": WEBCLIP_PAYLOAD_TYPE,
        "PayloadVersion": 1,
        "PayloadIdentifier": f"{WEBCLIP_PROFILE_IDENTIFIER}.payload",
        "PayloadUUID": _new_uuid(),
        "PayloadDisplayName": "WorkSlop Bookmark (WebClip)",
        "PayloadDescription": (
            "Adds a WorkSlop bookmark icon to the home screen that opens "
            "the WorkSlop website. Removable; installs normally on retail "
            "iPhones; changes no system settings."
        ),
        # Standard WebClip payload keys only (Apple-documented).
        "Label": label.strip(),
        "URL": url.strip(),
        "IsRemovable": True,
        "Precomposed": True,
    }
    if include_icon:
        icon_bytes = _read_icon_bytes(icon_path)
        if not icon_bytes:
            raise ValueError("Icon file is empty.")
        payload["Icon"] = icon_bytes

    profile = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": WEBCLIP_PROFILE_IDENTIFIER,
        "PayloadUUID": _new_uuid(),
        "PayloadDisplayName": display_name.strip(),
        "PayloadDescription": (
            "WorkSlop-generated configuration profile that adds a bookmark "
            "icon to the home screen opening the WorkSlop website. Normal "
            "WebClip install on retail iPhones."
        ),
        "PayloadContent": [payload],
    }
    if organization and organization.strip():
        profile["PayloadOrganization"] = organization.strip()
    return profile


def write_mobileconfig(profile: dict, path: str) -> None:
    """Write the profile dict to ``path`` as an XML .mobileconfig plist."""
    with open(path, "wb") as fh:
        plistlib.dump(profile, fh, fmt=plistlib.FMT_XML, sort_keys=False)


def read_mobileconfig(path: str) -> dict:
    """Read a .mobileconfig back (used by tests / verification)."""
    with open(path, "rb") as fh:
        return plistlib.load(fh)
