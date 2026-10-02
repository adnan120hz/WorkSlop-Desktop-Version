"""Device compatibility for tweaks.

The constraints themselves live in the tweak registry
(``TweakSpec.min_version`` / ``iphone_only`` / ``ipad_only`` /
``requires_gestalt``); this module only evaluates them, together with the
one shared MobileGestalt capability decision. The backend apply pass uses
the same predicate via ``src.tweaks.capabilities`` so the UI and the apply
path cannot disagree.
"""
from src.tweaks.capabilities import tweak_deliverability


def is_tweak_compatible(tweak_id, device_version: str, is_iphone: bool,
                        device_build: str = "") -> bool:
    """Return True if the tweak makes sense on the given device.

    Registry version/device-class constraints and, for MobileGestalt-backed
    tweaks, the shared MobileGestalt decision must all pass. Unknown device
    evidence never blocks ordinary tweaks, but always blocks
    MobileGestalt-backed ones (fail-closed).
    """
    deliverable, _reason, _message = tweak_deliverability(
        tweak_id, device_version=device_version, device_build=device_build,
        is_iphone=is_iphone)
    return deliverable


def tweak_incompatibility_reason(tweak_id, device_version: str,
                                 is_iphone: bool, device_build: str = "") -> str:
    """User-facing reason a tweak is locked, or "" when it is compatible."""
    deliverable, _reason, message = tweak_deliverability(
        tweak_id, device_version=device_version, device_build=device_build,
        is_iphone=is_iphone)
    return "" if deliverable else message
