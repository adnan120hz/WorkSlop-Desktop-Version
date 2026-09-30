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


def is_gestalt_supported_build(build: str) -> bool:
    # MobileGestalt rule (user decision 2026-09-30): open and usable from
    # iOS 16.0 through iOS 26.2 beta 1. Locked on 26.2 beta 2 and newer.
    return _norm_build(build) in MOBILEGESTALT_BUILDS


def is_ios27_build(build: str) -> bool:
    # Any iOS 27 build = the whole 24 train (24A = 27.0, 24B = 27.1, ...).
    # Used to lock the Status Bar menu, which is only open on iOS 26 and
    # below (user decision 2026-09-30: locked on any iOS 27).
    return _norm_build(build).startswith("24")


# WorkSlop Desktop explicit per-build support list (user decision 2026-09-30).
# Only these iOS builds are supported — 49 builds, iOS 16.0 -> iOS 27.0.
SUPPORTED_BUILDS = frozenset({
    # iOS 16.x
    "20A362", "20A371", "20A380", "20A392",
    "20B82", "20B101", "20B110",
    "20C65",
    "20D47", "20D67",
    "20E247", "20E252",
    "20F66", "20F75",
    "20G75", "20G81",
    "20H19", "20H24", "20H30", "20H57", "20H68",
    "20H115", "20H219", "20H315", "20H332", "20H350",
    # iOS 18.x
    "22A3354",
    "22B5007p", "22B5023e", "22B5034e", "22B5045g",
    # iOS 26.x
    "23A341", "23A342",          # 26.0, 26.0.1
    "23B85",                     # 26.1
    "23C5027f",                  # 26.2 beta 1
    "23C5035e", "23C5042d",      # 26.2 betas
    "23C89",                     # 26.2
    "23D57",                     # 26.3
    "23E215",                    # 26.4
    "23F72",                     # 26.5
    # iOS 27.0
    "24A5264w", "24A5279h", "24A5288g", "24A5299d",
    "24A5309f", "24A5315a", "24A5320a",  # 27.0 betas
    "24A335",                    # 27.0
})

# Builds after iOS 26.2 beta 1 — MobileGestalt stays locked on these.
_POST_262B1_BUILDS = frozenset({
    "23C5035e", "23C5042d",      # 26.2 beta 2+
    "23C89",                     # 26.2
    "23D57", "23E215", "23F72",  # 26.3 - 26.5
    "24A5264w", "24A5279h", "24A5288g", "24A5299d",
    "24A5315a", "24A5320a", "24A5309f",
    "24A335",                    # 27.0
})

# MobileGestalt: iOS 16.0 -> iOS 26.2 beta 1 (35 builds).
MOBILEGESTALT_BUILDS = SUPPORTED_BUILDS - _POST_262B1_BUILDS
