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

def is_supported_by_fork(version: str) -> bool:
    # WorkSlop rule (user decision 2026-09-30): ALL iOS 26 versions use the
    # partial restore path (sparse restore, no wipe). iOS 27+ keeps the
    # three-phase protective flow. Below iOS 26 stays unsupported.
    try:
        return Version(str(version)) >= Version("26.0")
    except Exception:
        # an empty or unparsable version cannot be verified, so treat it as
        # unsupported rather than letting Version() raise into the UI
        return False


def is_gestalt_supported(version: str) -> bool:
    # MobileGestalt rule follows leminlimez/Nugget upstream 100%:
    # not supported on iOS 26.2+, never will be. Available on 26.1 and below.
    try:
        return Version(str(version)) < Version("26.2")
    except Exception:
        return False
