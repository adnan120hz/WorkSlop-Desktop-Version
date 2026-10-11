from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from pymobiledevice3.ca import create_keybag_file
from pymobiledevice3.exceptions import CloudConfigurationAlreadyPresentError
from pymobiledevice3.lockdown import LockdownClient
from pymobiledevice3.services.mobile_config import MobileConfigService

from src.utils.log_util import log_info, log_warn

# Canonical list of setup panes to mark as skipped. This is the single source
# of truth for the *pane list* on every skip-setup path:
#   - the standalone CLI (skip_setup.py) — reuses this list, but builds its
#     own cloud-config dict (not byte-identical to build_cloud_config below)
#   - the iOS 27 Phase-5 sweep (skip_all_setup27 below; was mislabelled
#     "Phase-4" — audit N72)
#   - the iOS 26 cloud-config path (device_manager.add_skip_setup)
# It is the union of the curated iOS 27 list and the older iOS 26 list so no pane
# is lost on either OS (an identifier that is unknown to a given iOS is a no-op).
# Keep the list here and never fork a copy.
SKIP_ALL_PANES = [
    'Location',
    'Restore',
    'SIMSetup',
    'Android',
    'AppleID',
    'IntendedUser',
    'TOS',
    'Siri',
    'ScreenTime',
    'Diagnostics',
    'SoftwareUpdate',
    'Passcode',
    'Biometric',
    'Payment',
    'Zoom',
    'DisplayTone',
    'MessagingActivationUsingPhoneNumber',
    'HomeButtonSensitivity',
    'CloudStorage',
    'ScreenSaver',
    'TapToSetup',
    'Keyboard',
    'PreferredLanguage',
    'SpokenLanguage',
    'WatchMigration',
    'OnBoarding',
    'TVProviderSignIn',
    'TVHomeScreenSync',
    'Privacy',
    'TVRoom',
    'iMessageAndFaceTime',
    'AppStore',
    'Safety',
    'Multitasking',
    'ActionButton',
    'TermsOfAddress',
    'AccessibilityAppearance',
    'Welcome',
    'Appearance',
    'RestoreCompleted',
    'UpdateCompleted',
    'WiFi',
    'Display',
    'Tone',
    'LanguageAndLocale',
    'TouchID',
    'TrueToneDisplay',
    'FileVault',
    'iCloudStorage',
    'iCloudDiagnostics',
    'Registration',
    'DeviceToDeviceMigration',
    'UnlockWithWatch',
    'Accessibility',
    'All',
    'ExpressLanguage',
    'Language',
    'Region',
    'Avatar',
    'DeviceProtection',
    'Key',
    'LockdownMode',
    'Wallpaper',
    'PrivacySubtitle',
    'SecuritySubtitle',
    'DataSubtitle',
    'AppleIDSubtitle',
    'AppearanceSubtitle',
    'PreferredLang',
    'OnboardingSubtitle',
    'AppleTVSubtitle',
    'Intelligence',
    'WebContentFiltering',
    'CameraButton',
    'AdditionalPrivacySettings',
    'EnableLockdownMode',
    'OSShowcase',
    'SafetyAndHandling',
    'Tips',
    'AgeBasedSafetySettings',
]

def skip_setup_panes() -> list:
    """Resolve the exact ``SkipSetup`` pane list: every pane is skipped,
    Apple ID sign-in included. Keeps ``SKIP_ALL_PANES`` as the canonical list.
    """
    return list(SKIP_ALL_PANES)


def build_cloud_config(existing: dict | None, supervised: bool = False,
                       organization_name: str = "") -> dict:
    """Build the cloud configuration dict (single source of truth).

    Used by both skip-setup deliveries so they produce byte-identical config:
      * iOS 27: ``skip_all_setup27`` pushes it natively with
        ``MobileConfigService.set_cloud_configuration`` (Phase 5).
      * iOS 26: ``device_manager.add_skip_setup`` embeds it into Phase 2's
        sparse restore as ``CloudConfigurationDetails.plist``.
    """
    cloud_config = dict(existing or {})
    cloud_config['SkipSetup'] = skip_setup_panes()
    cloud_config["AllowPairing"] = True
    cloud_config["ConfigurationWasApplied"] = True
    cloud_config["CloudConfigurationUIComplete"] = True
    cloud_config["IsSupervised"] = False
    cloud_config["ConfigurationSource"] = 0
    cloud_config["PostSetupProfileWasInstalled"] = True
    if supervised:
        cloud_config["IsSupervised"] = True
        # create/add the keybag
        if organization_name:
            with TemporaryDirectory() as temp_dir:
                keybag_file = Path(temp_dir) / 'keybag'
                create_keybag_file(keybag_file, organization_name)
                cer = x509.load_pem_x509_certificate(keybag_file.read_bytes())
                public_key = cer.public_bytes(Encoding.DER)
                # make sure the mdm is removable
                cloud_config["OrganizationName"] = organization_name
                # N71: deliberately fresh per supervised push — each
                # supervised enrollment is a new supervision identity, so a
                # stable magic would be wrong here. Not idempotent across
                # pushes, but a second push is blocked by
                # CloudConfigurationAlreadyPresentError anyway, so the
                # non-idempotency never compounds in practice.
                cloud_config['OrganizationMagic'] = str(uuid4())
                cloud_config['IsMDMUnremovable'] = False
                cloud_config['SupervisorHostCertificates'] = [public_key]
        else:
            # remove keybag info
            if 'OrganizationMagic' in cloud_config:
                cloud_config.pop('OrganizationMagic')
            if 'SupervisorHostCertificates' in cloud_config:
                cloud_config.pop('SupervisorHostCertificates')
    return cloud_config


async def skip_all_setup27(ld: LockdownClient, udid: str | None = None,
                           supervised: bool = False,
                           organization_name: str = ""):
    async with MobileConfigService(lockdown=ld) as mcs:
        cloud_config = build_cloud_config(
            await mcs.get_cloud_configuration(),
            supervised=supervised,
            organization_name=organization_name)
        await mcs.set_cloud_configuration(cloud_config)


async def maybe_skip_setup_after_g1(udid: str | None) -> bool:
    """Best-effort Setup Assistant skip after the iOS 27 G1 full restore.

    Never raises: every failure mode returns False, so it is safe to CALL
    from anywhere. It opens its own lockdown session (never reuses the
    caller's client, which may be stale after the restore + optional
    reboot), probes that the device actually answers queries, then runs
    the existing ``skip_all_setup27`` push. An already-present cloud
    configuration counts as idempotent success.

    WIRING VERDICT (audit M20): do NOT auto-wire this unconditionally after
    every G1 apply. The G1 route never wipes, so a healthy post-restore
    device boots back to the home screen — never to Setup Assistant — and
    there is no reliable host-side signal distinguishing "stranded at
    Hello" from "still booting normally". An unconditional push would write
    a cloud-configuration record onto the user's daily device in the common
    case for zero benefit. Use it only as a user-confirmed recovery action
    ("the device shows Hello after the restore") — never as an automatic
    post-restore step.

    Precondition (caller responsibility): the G1 restore must no longer be
    in flight — call only after ``deliver_ios27_payload`` has returned.
    There is no host-side "restore in progress" flag; sequencing is the
    guard. The liveness probe below is a second line of defence, not a
    restore detector.
    """
    from src.devicemanagement.session import lockdown_session

    if not udid:
        log_warn("maybe_skip_setup_after_g1: no UDID — refusing a blind push")
        return False
    try:
        # Own session with a bounded trust wait: the device was paired
        # moments ago, so this reconnects silently on the normal path.
        async with lockdown_session(udid, pair_timeout=30.0) as ld:
            try:
                # Liveness probe: a device mid-restore/mid-reboot does not
                # answer lockdown queries. (This cannot detect "restore
                # still running" — see the precondition above.)
                if not getattr(ld, "product_version", None):
                    log_warn("maybe_skip_setup_after_g1: device reachable "
                             "but not answering queries — not safe, skipping")
                    return False
            except Exception as probe_err:
                log_warn(f"maybe_skip_setup_after_g1: liveness probe failed "
                         f"({type(probe_err).__name__}) — skipping")
                return False
            try:
                await skip_all_setup27(ld, udid)
            except CloudConfigurationAlreadyPresentError:
                log_info("maybe_skip_setup_after_g1: cloud configuration "
                         "already present — setup already handled")
                return True
            log_info("maybe_skip_setup_after_g1: Setup Assistant panes skipped")
            return True
    except Exception as e:
        log_warn(f"maybe_skip_setup_after_g1: skipped safely "
                 f"({type(e).__name__}: {e})")
        return False
