"""Shared page-identifier enum used by both the GUI and the backend reset flow.

Historically defined in ``src/gui/pages/pages_list.py``; it moved here so the
backend (``device_manager`` reset pass) no longer imports the GUI package.
``src/gui/pages/pages_list.py`` re-exports both symbols for the GUI side.
"""

from enum import Enum

from packaging.version import InvalidVersion

from src.devicemanagement.constants import Version


class Page(Enum):
    Home = 0
    Gestalt = 1
    EUEnabler = 2
    StatusBar = 3
    Springboard = 4
    InternalOptions = 5
    LiquidGlass = 6
    Daemons = 7
    Posterboard = 8
    Templates = 9
    Passcode = 10
    RiskyTweaks = 11
    Tweaks = 12
    Apply = 13
    Settings = 14

    def getPageName(self) -> str:
        name_map = [
            "Home",
            "Mobile Gestalt",
            "Eligibility",
            "Status Bar",
            "Springboard",
            "Internal",
            "Liquid Glass",
            "Daemons",
            "PosterBoard",
            "Templates",
            "Passcode",
            "Resolution Modifications",
            "Tweaks",
            "Apply",
            "Settings"
        ]
        return name_map[self.value]

def get_resettable_pages(device_manager) -> list[Page]:
    # The device version can be unknown at this point: get_current_device_version()
    # returns "" until a device is selected and its info has loaded, and
    # Version("") raises InvalidVersion — the Reset dialog used to die in its
    # constructor and the button looked completely dead. Parse defensively
    # instead, and treat an unknown version conservatively below.
    raw_version = ""
    try:
        raw_version = str(
            device_manager.get_current_device_version() or "").strip()
    except Exception:
        raw_version = ""
    try:
        device_ver = Version(raw_version) if raw_version else None
    except InvalidVersion:
        device_ver = None
    # B10 FIX: every tweak family now has a reset — previously Liquid Glass,
    # Feature Flags (on the Tweaks page), Risky, Eligibility and MobileGestalt
    # could never be reset from Settings.
    page_list: list[Page] = [
        Page.Springboard, Page.InternalOptions, Page.Daemons,
        Page.Tweaks,          # Feature Flags live on the Tweaks page
        Page.LiquidGlass,
        Page.RiskyTweaks,
        Page.EUEnabler,       # Eligibility
        Page.Gestalt,         # MobileGestalt (restores the pristine plist)
    ]

    # Status Bar is broken on iOS 27 (no write permissions for Speakeasy flags)
    # so the feature is hidden on iOS 27+. The entry is version-gated, so it
    # is only offered when the device is KNOWN to be below iOS 27 — an
    # unknown/unparseable version hides it rather than guessing.
    if device_ver is not None and device_ver < Version("27.0"):
        page_list.insert(0, Page.StatusBar)

    return page_list