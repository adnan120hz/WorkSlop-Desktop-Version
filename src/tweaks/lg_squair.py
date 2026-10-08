"""Squair Protocol (test) — payload core + planner for the Squair test.

TEST-ONLY payload, ordered as a device experiment (Squair's two Discord
hints). It rides the existing Liquid Glass Disable full-backup route
(``src/restore/lgd_full.py``); it is NOT a product claim and nothing here
claims any file disables Liquid Glass.

Payload (exact):

* **File A** — merge into the device's own
  ``/var/mobile/Library/Preferences/.GlobalPreferences.plist``
  (HomeDomain ``Library/Preferences/.GlobalPreferences.plist``): add
  exactly two keys, ``SBDisallowGlassTime`` and
  ``SBDisallowGlassButtons``, as real bool ``true``. The write REPLACES
  the whole file through the full-backup route, so it is built from the
  live device file through the same fail-hard diff gate as G1
  (``lg_disable.build_g1_payload``): 100% of the original keys intact or
  the apply is cancelled. The Beta 1 G1/G2 behaviour (the
  ``SolariumForceFallback`` key) is untouched.
* **File Domain** — inject
  ``FeatureFlags/Domain/SpringBoard.plist`` into
  ``SystemPreferencesDomain`` with the XML plist
  ``{"SpringBoard": {"SolariumElasticHUD": {"Enabled": false}}}``
  (pure bool, solver-style nesting, no ``DevelopmentPhase``). The
  ``FeatureFlags/`` + ``FeatureFlags/Domain/`` directory rows are created
  by the injector.

Audit verdict carried honestly (step8 squair addendum + R20): the backup
restore channel is predicted to SKIP the Domain file silently (only the
empty directory lands) — the Domain file is a written, testable
prediction, not a delivery. That is why the journal/UI must never claim
the Domain file landed.

Like ``lg_disable``, this module stays free of the device stack (no
``src.restore`` import): payload builders + tuple planners only.
"""

import plistlib

from src.exceptions.nugget_exception import NuggetException
from src.tweaks import lg_disable
from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.tweak_classes import BasicPlistTweak

FEATURE_NAME = "Lock Screen Keys (Test)"

# File A keys (exactly two; real bool true, enforced by the builders).
GP_KEYS = ("SBDisallowGlassTime", "SBDisallowGlassButtons")
GP_KEY_VALUES = {key: True for key in GP_KEYS}

# File A target = the same device file G1 merges (HomeDomain).
G1_DOMAIN = lg_disable.G1_DOMAIN
G1_REL_PATH = lg_disable.G1_REL_PATH

# File Domain target (SystemPreferencesDomain, per
# src.restore.path_mapping for /var/preferences/).
DOMAIN = "SystemPreferencesDomain"
DOMAIN_REL_PATH = "FeatureFlags/Domain/SpringBoard.plist"

# The Domain file content: nested SpringBoard PrefDomainMap shape with a
# real bool false — never the integer 0, never a DevelopmentPhase key.
DOMAIN_FILE_DICT = {"SpringBoard": {"SolariumElasticHUD": {"Enabled": False}}}

# Inject-tuple metadata, identical to what src.restore.lgd_full forces
# for every full-route payload (kept literal: tweak modules must not
# import src.restore).
FILE_MODE = 0o100644  # S_IFREG | 0644
FILE_OWNER = 501
FILE_GROUP = 501

# Honest journal/log note: the Domain file may land but cannot be proven
# (or, if landed, removed) through this channel. Written to the apply
# journal entry when this payload is delivered.
DOMAIN_FILE_NOTE = (
    "Lock Screen Keys (Test): the FeatureFlags/Domain/SpringBoard.plist "
    "payload was injected into the backup, but its landing on the "
    "device is NOT confirmed — it is predicted to be skipped silently "
    "by the restore channel (only the empty FeatureFlags/Domain "
    "directory is expected to appear). If it did land, it cannot be "
    "removed by a restore; only the two .GlobalPreferences.plist keys "
    "are rolled back."
)

DOMAIN_ROLLBACK_NOTE = (
    "Lock Screen Keys (Test) rollback: only the two "
    ".GlobalPreferences.plist keys (SBDisallowGlassTime, "
    "SBDisallowGlassButtons) were removed. The "
    "FeatureFlags/Domain/SpringBoard.plist file, if it landed on the "
    "device, cannot be removed by a restore and was left in place."
)


def build_domain_file_bytes() -> bytes:
    """The exact Domain-file payload (XML plist, sort_keys=True)."""
    return plistlib.dumps(
        DOMAIN_FILE_DICT, fmt=plistlib.FMT_XML, sort_keys=True)


def load_domain_file_dict(data) -> dict:
    """Parse Domain-file bytes back; raise ValueError on any deviation."""
    result = lg_disable.load_plist_dict(data)
    if result != DOMAIN_FILE_DICT:
        raise ValueError(
            f"Domain file dict mismatch: {result!r} != {DOMAIN_FILE_DICT!r}")
    return result


def _inject_tuple(domain: str, rel_path: str, data: bytes):
    """One full-route inject tuple (mode/owner/group force-stamped)."""
    return (domain, rel_path, bytes(data), FILE_MODE, FILE_OWNER,
            FILE_GROUP)


def plan_squair_apply_payloads(gp_base, extra_inserts=None) -> list:
    """Inject tuples for a Squair apply: File A merge + File Domain.

    ``gp_base`` MUST be the parsed live device
    ``.GlobalPreferences.plist`` (fail-closed without it, like G1).
    ``extra_inserts`` are deliberately staged keys from other routes
    writing the same file in the same apply pass (e.g. G1's candidate key
    when both routes are enabled): they ride the merge so the later
    full-file write cannot silently drop them.
    """
    if not isinstance(gp_base, dict):
        raise NuggetException(
            "Lock Screen Keys (Test): the full-backup route needs the "
            "device's own .GlobalPreferences.plist as the File A merge "
            "base, and it could not be read. Nothing was written.")
    inserts = dict(GP_KEY_VALUES)
    if extra_inserts:
        inserts.update(extra_inserts)
    file_a = lg_disable.build_g1_payload(gp_base, inserts)
    return [
        _inject_tuple(G1_DOMAIN, G1_REL_PATH, file_a),
        _inject_tuple(DOMAIN, DOMAIN_REL_PATH, build_domain_file_bytes()),
    ]


def plan_squair_rollback_payloads(fresh_base):
    """Rollback plan from a FRESH device capture.

    Returns ``(payloads, note)``: one inject tuple writing the fresh
    ``.GlobalPreferences.plist`` back with exactly the two Squair keys
    removed (never the stored pre-apply original — the device state may
    have moved on), plus the honest note that the Domain file cannot be
    removed by a restore.
    """
    if not isinstance(fresh_base, dict):
        raise NuggetException(
            "Lock Screen Keys (Test): rollback needs a fresh read of the "
            "device's .GlobalPreferences.plist, and it could not be "
            "read or parsed. Nothing was written.")
    merged = {k: v for k, v in fresh_base.items() if k not in GP_KEYS}
    payload = plistlib.dumps(merged, fmt=plistlib.FMT_BINARY, sort_keys=True)
    parsed = lg_disable.load_plist_dict(payload)
    if parsed != merged:
        raise ValueError(
            "Lock Screen Keys rollback payload failed its own round-trip check.")
    return [_inject_tuple(G1_DOMAIN, G1_REL_PATH, payload)], \
        DOMAIN_ROLLBACK_NOTE


class LGDSquairTweak(BasicPlistTweak):
    """File A staging for the Squair test payload.

    Like G1, the whole-file payload REPLACES the device's
    ``.GlobalPreferences.plist``, so staging is a surgical merge into the
    device's live file (``_lgd_base``, armed by DeviceManager's prepare
    step). Unlike G1 this NEVER stages through the generic sparse pass:
    the File Domain payload can only ride the full-backup route, so
    ``apply_tweak`` marks ``staged`` (armed + enabled) and leaves
    ``other_tweaks`` untouched; DeviceManager diverts the marker into a
    second gated full-route run. With no live base it stages nothing
    (fail closed) — the apply pass then simply has no Squair payload,
    exactly like the armed-G1 contract.
    """

    def __init__(self):
        super().__init__(FileLocation.globalPreferencesHomeDomain,
                         GP_KEYS[0], value=True)
        self.staged = False
        self._lgd_base = None

    def apply_tweak(self, other_tweaks: dict) -> dict:
        if not self.enabled:
            self.staged = False
            return other_tweaks
        if not isinstance(self._lgd_base, dict):
            # No live device base armed this pass → fail closed:
            # nothing is staged and the full route is never invoked.
            self.staged = False
            return other_tweaks
        # Validate the merge NOW (fail-hard diff gate, same as G1) so a
        # bad base surfaces at staging time, not mid-restore. The route
        # re-plans from the same base and verifies the injected bytes.
        lg_disable.build_g1_payload(self._lgd_base, dict(GP_KEY_VALUES))
        self.staged = True
        return other_tweaks
