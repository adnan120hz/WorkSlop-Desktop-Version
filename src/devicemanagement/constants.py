from dataclasses import dataclass

from packaging.version import Version


class Device:
    def __init__(self,
                udid: int, usb: bool, name: str,
                version: str, build: str,
                model: str, hardware: str, cpu: str, locale: str
            ):
        self.udid = udid
        self.connected_via_usb = usb
        self.name = name
        self.version = version
        self.build = build
        self.model = model
        self.hardware = hardware
        self.cpu = cpu
        self.locale = locale

def _norm_build(build) -> str:
    try:
        return str(build or "").strip()
    except Exception:
        return ""


def is_build_supported(build: str) -> bool:
    # WorkSlop rule (user decision 2026-09-30): ONLY the iOS builds listed
    # in SUPPORTED_BUILDS are supported. Anything else is rejected, even if
    # its version number looks newer.
    return _norm_build(build) in SUPPORTED_BUILDS


def _parse_version(version):
    try:
        return Version(str(version or "").strip())
    except Exception:
        return None


def is_version_supported(version: str) -> bool:
    # Cable-based detection (user decision 2026-09-30): the iOS version is
    # read straight from the device over the cable (lockdown ProductVersion).
    # Any 16.0 -> 26.x version is supported for the tweak flow even when its
    # exact build number is not in the allowlist (RC variants, new patches).
    v = _parse_version(version)
    if v is None:
        return False
    return Version("16.0") <= v < Version("27.0")


# REAUDIT FIX: is_version_ios27() was dead code — zero callers (the codebase
# settled on inline `Version(x) >= Version("27.0")` checks with their own
# None-guarding). Removed the unused helper; behavior unchanged.


def is_device_supported(build: str, version: str) -> bool:
    # A device is usable when EITHER its build is allowlisted OR its
    # cable-reported iOS version is in the supported range.
    return is_build_supported(build) or is_version_supported(version)


def is_gestalt_supported_build(build: str) -> bool:
    # MobileGestalt rule (user decision 2026-09-30): open and usable from
    # iOS 16.0 through iOS 26.2 beta 1. Locked on 26.2 beta 2 and newer.
    return _norm_build(build) in MOBILEGESTALT_BUILDS


def is_gestalt_supported_version(version: str) -> bool:
    # Cable-based fallback for MobileGestalt. ProductVersion cannot tell
    # 26.2 beta 1 apart from beta 2+, so anything 26.2+ needs the
    # build-level check (conservative: locked).
    v = _parse_version(version)
    if v is None:
        return False
    return Version("16.0") <= v < Version("26.2")


def is_gestalt_supported(build: str, version: str) -> bool:
    return mobilegestalt_decision(build, version).supported


@dataclass(frozen=True)
class MobileGestaltDecision:
    """The one MobileGestalt capability decision shared by every surface.

    ``supported`` is true only for the explicit ``supported`` state. Locked
    and unknown states are both fail-closed: callers must not enable, restore,
    count, or deliver a MobileGestalt-backed tweak from either one.
    """

    state: str              # "supported", "locked", or "unknown"
    supported: bool         # True only when state == "supported"
    reason_code: str        # stable machine-readable code (never localized)
    user_message: str       # short user-facing explanation
    source: str             # "build", "version", or "none"
    build: str              # normalized build used for the decision
    version: str            # normalized version used for the decision

    @property
    def known(self) -> bool:
        return self.state != "unknown"


def _norm_version(version) -> str:
    try:
        return str(version or "").strip()
    except Exception:
        return ""


def mobilegestalt_decision(build: str = "", version: str = "") -> MobileGestaltDecision:
    """Return the single MobileGestalt capability decision.

    Exact build evidence is authoritative because ProductVersion cannot tell
    iOS 26.2 beta 1 from beta 2 or later. The version branch is only a
    fallback when the exact build is absent or unknown to every relevant
    build set. No device / no usable evidence is ``unknown``, never
    compatible.
    """
    norm_build = _norm_build(build)
    norm_version = _norm_version(version)
    parsed_version = _parse_version(norm_version)

    if not norm_build and parsed_version is None:
        if not norm_version:
            return MobileGestaltDecision(
                state="unknown", supported=False, reason_code="NO_DEVICE",
                user_message="Connect a device to check MobileGestalt support.",
                source="none", build=norm_build, version=norm_version)
        return MobileGestaltDecision(
            state="unknown", supported=False,
            reason_code="UNKNOWN_BUILD_AND_VERSION",
            user_message="MobileGestalt support cannot be determined for this device yet.",
            source="none", build=norm_build, version=norm_version)

    if norm_build in MOBILEGESTALT_BUILDS:
        if parsed_version is not None and parsed_version >= Version("26.2"):
            return MobileGestaltDecision(
                state="supported", supported=True,
                reason_code="BUILD_VERSION_CONFLICT",
                user_message="MobileGestalt is supported on this iOS build.",
                source="build", build=norm_build, version=norm_version)
        return MobileGestaltDecision(
            state="supported", supported=True, reason_code="BUILD_ALLOWLISTED",
            user_message="MobileGestalt is supported on this iOS build.",
            source="build", build=norm_build, version=norm_version)

    if norm_build in _POST_262B1_BUILDS:
        return MobileGestaltDecision(
            state="locked", supported=False,
            reason_code="BUILD_LOCKED_POST_26_2_BETA_1",
            user_message="MobileGestalt is locked on this iOS build (supported through iOS 26.2 beta 1 only).",
            source="build", build=norm_build, version=norm_version)

    if norm_build in SUPPORTED_BUILDS:
        return MobileGestaltDecision(
            state="locked", supported=False, reason_code="BUILD_NOT_ALLOWLISTED",
            user_message="MobileGestalt is not supported on this iOS build.",
            source="build", build=norm_build, version=norm_version)

    # Exact build was empty or unknown to all relevant sets: version fallback.
    if parsed_version is not None and parsed_version < Version("26.2"):
        return MobileGestaltDecision(
            state="supported", supported=True, reason_code="VERSION_BEFORE_26_2",
            user_message="MobileGestalt is supported on this iOS version.",
            source="version", build=norm_build, version=norm_version)
    if parsed_version is not None and parsed_version >= Version("26.2"):
        return MobileGestaltDecision(
            state="locked", supported=False,
            reason_code="VERSION_26_2_OR_NEWER_LOCKED",
            user_message="MobileGestalt is locked on iOS 26.2 and newer unless a supported exact build is known.",
            source="version", build=norm_build, version=norm_version)

    return MobileGestaltDecision(
        state="unknown", supported=False,
        reason_code="UNKNOWN_BUILD_AND_VERSION",
        user_message="MobileGestalt support cannot be determined for this device yet.",
        source="none", build=norm_build, version=norm_version)


def is_ios27_build(build: str) -> bool:
    # Any iOS 27 build = the whole 24 train (24A = 27.0, 24B = 27.1, ...).
    # Used to lock the Status Bar menu, which is only open on iOS 26 and
    # below (user decision 2026-09-30: locked on any iOS 27).
    return _norm_build(build).startswith("24")


# WorkSlop Desktop explicit per-build support list.
# Every iOS 17.0 -> iOS 27.2 build from the user's verified list (2026-09-30),
# plus the verified iOS 16.x range and the 26.2 beta 1 MobileGestalt boundary
# build. The device is ALSO accepted when its cable-reported ProductVersion is
# inside 16.0 -> 26.x (see is_device_supported), so RC variants and new
# patches keep working even before their exact build is listed here.
SUPPORTED_BUILDS = frozenset({
    # ---- iOS 16.x (20A - 20H) — research-verified by me (2026-09-30),
    # 16.0 -> 16.7.16 complete. User handled 17/18/26/27, I filled 16. ----
    # 16.0 - 16.0.3 (20A357 = 16.0 RTM)
    "20A357", "20A362", "20A371", "20A380", "20A392",
    # 16.1 - 16.1.2
    "20B82", "20B101", "20B110",
    # 16.2
    "20C65",
    # 16.3 - 16.3.1
    "20D47", "20D67",
    # 16.4 - 16.4.1
    "20E247", "20E252",
    # 16.5 - 16.5.1
    "20F66", "20F75",
    # 16.6 - 16.6.1
    "20G75", "20G81",
    # 16.7 - 16.7.16 (verified builds only; 17.5.2 was cancelled by Apple)
    "20H19", "20H30",
    "20H115", "20H232", "20H240",
    "20H307", "20H320", "20H330", "20H343",
    "20H348", "20H350", "20H360", "20H364", "20H365",
    "20H370", "20H380", "20H392",
    # ---- iOS 17.x (21A - 21H) — user-verified list 2026-09-30 ----
    # 17.0 - 17.0.3
    "21A329", "21A340", "21A350", "21A351", "21A360",
    # 17.1 - 17.1.2
    "21B74", "21B80", "21B91", "21B101",
    # 17.2 - 17.2.1
    "21C62", "21C66",
    # 17.3 - 17.3.1
    "21D50", "21D61",
    # 17.4 - 17.4.1
    "21E219", "21E236", "21E237",
    # 17.5 - 17.5.1  (17.5.2 was cancelled by Apple, never released)
    "21F79", "21F90",
    # 17.6 - 17.6.1
    "21G80", "21G93", "21G101",
    # 17.7 - 17.7.2
    "21H16", "21H216", "21H221",
    # ---- iOS 18.x (22A - 22H) — user-verified list 2026-09-30 ----
    # 18.0 - 18.0.1
    "22A3354", "22A3370",
    # 18.1 - 18.1.1
    "22B83", "22B91",
    # 18.2 - 18.2.1
    "22C152", "22C161",
    # 18.3 - 18.3.2 (22D8063/22D8075/22D8082 = iPhone 16e variants, 22D64 = iPhone 11)
    "22D63", "22D64", "22D72", "22D82",
    "22D8063", "22D8075", "22D8082",
    # 18.4 - 18.4.1
    "22E240", "22E252",
    # 18.5
    "22F76",
    # 18.6 - 18.6.2
    "22G86", "22G90", "22G100",
    # 18.7 - 18.7.10 (22H123 = 18.7.2 RC, 22H333 = 18.7.7 RC, 22H373 = 18.7.10 RC)
    "22H20", "22H31", "22H123", "22H124", "22H217", "22H218",
    "22H311", "22H320", "22H333", "22H340", "22H352", "22H355",
    "22H373", "22H374",
    # ---- iOS 26.x (23A - 23H) — verified 2026-09-30 (ipsw.me, iClarified,
    # 3uTools, MacRumors forums; RC/beta builds included so users on
    # pre-release builds are not rejected) ----
    # 26.0 betas 1-8
    "23A5260n", "23A5276f", "23A5287g", "23A5297i",
    "23A5308g", "23A5318c", "23A5326a", "23A5330a",
    # 26.0 RC + final (23A330 = iPhone 17 pre-installed, 23A345 = 17 Pro)
    "23A330", "23A340", "23A341", "23A345",
    # 26.0.1
    "23A355",
    # 26.1
    "23B85",
    # 26.2 beta 1 (MobileGestalt boundary, inclusive)
    "23C5027f",
    # 26.2 beta 2 (MobileGestalt locked from here) + 26.2 RC/final
    "23C5035e", "23C52", "23C54", "23C55",
    # 26.2.1
    "23C71",
    # 26.3 RC + final + 26.3.1
    "23D125", "23D127", "23D8133",
    # 26.4 betas 3-4 + RC + final + 26.4.1 + 26.4.2
    "23E5223f", "23E5223k", "23E5234a", "23E244",
    "23E246", "23E254", "23E261",
    # 26.5 betas 1-4 + RC + final + 26.5.1 + 26.5.2
    "23F5043g", "23F5043k", "23F5059e", "23F5069b", "23F75",
    "23F77", "23F81", "23F84",
    # 26.6 betas 2/5 + RC/final + 26.6.1 (RC 23G82 + final 23G83) + 26.6.2
    "23G5043d", "23G5057c",
    "23G71", "23G82", "23G83", "23G90",
    # 26.7 + 26.7.1
    "23H24", "23H30",
    # ---- iOS 27.x (24A - 24B) — user-verified list 2026-09-30 ----
    # 27.0 betas 1-8
    "24A5355q", "24A5370h", "24A5380h", "24A5390f",
    "24A5408d", "24A5418b", "24A5424a", "24A5430a",
    # 27.0 RC + final
    "24A435", "24A437",
    # 27.2 betas 1-2
    "24B5084k", "24B5089g",
})

# Builds after iOS 26.2 beta 1 — MobileGestalt stays locked on these.
_POST_262B1_BUILDS = frozenset({
    "23C5035e",                  # 26.2 beta 2 (lock starts here)
    "23C52", "23C54", "23C55",   # 26.2 RC/final
    "23C71",                     # 26.2.1
    "23D125", "23D127", "23D8133",  # 26.3 RC/final + 26.3.1
    "23E5223f", "23E5223k", "23E5234a", "23E244",  # 26.4 betas + RC
    "23E246", "23E254", "23E261",  # 26.4 - 26.4.2
    "23F5043g", "23F5043k", "23F5059e", "23F5069b", "23F75",  # 26.5 betas + RC
    "23F77", "23F81", "23F84",   # 26.5 - 26.5.2
    "23G5043d", "23G5057c",      # 26.6 betas
    "23G71", "23G82", "23G83",   # 26.6 - 26.6.1
    "23G90",                     # 26.6.2
    "23H24", "23H30",            # 26.7 - 26.7.1
    "24A5355q", "24A5370h", "24A5380h", "24A5390f",
    "24A5408d", "24A5418b", "24A5424a", "24A5430a",
    "24A435", "24A437",          # 27.0
    "24B5084k", "24B5089g",      # 27.2 betas
})

# MobileGestalt: iOS 16.0 -> iOS 26.2 beta 1 (inclusive).
MOBILEGESTALT_BUILDS = SUPPORTED_BUILDS - _POST_262B1_BUILDS
