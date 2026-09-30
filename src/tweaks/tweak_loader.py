from .tweaks import tweaks, TweakID
from .registry import SPECS
from .basic_plist_locations import FileLocation
from .tweak_classes import (
    BasicPlistTweak, AdvancedPlistTweak, NullifyFileTweak,
    MobileGestaltTweak, MobileGestaltPickerTweak,
    MobileGestaltMultiTweak, MobileGestaltCacheDataTweak,
)
from .daemons_tweak import DANGEROUS_KEYS, INTERFACE_KEYS
from src.devicemanagement.constants import Version


def get_mobilegestalt_tweaks() -> dict:
    # Ported verbatim from leminlimez/Nugget
    # (src/tweaks/tweak_loader.py::get_mobilegestalt_tweaks).
    return {
        TweakID.DynamicIsland: MobileGestaltPickerTweak("oPeik/9e8lQWMszEjbPzng", subkey="ArtworkDeviceSubType", values=[2436, 2556, 2796, 2622, 2868, 2736]),
        TweakID.SupportsDynamicIsland: MobileGestaltTweak("YlEtTtHlNesRBMal1CqRaA"),
        TweakID.ModelName: MobileGestaltTweak("oPeik/9e8lQWMszEjbPzng", subkey="ArtworkDeviceProductDescription", value=""),
        TweakID.BootChime: MobileGestaltTweak("QHxt+hGLaBPbQJbXiUJX3w"),
        TweakID.EnableLGLPM: MobileGestaltTweak("SAGvsp6O6kAQ4fEfDJpC4Q"),
        TweakID.DisableLGLPM: MobileGestaltTweak("SAGvsp6O6kAQ4fEfDJpC4Q", value=0),
        TweakID.ChargeLimit: MobileGestaltTweak("37NVydb//GP/GrhuTN+exg"),
        TweakID.CollisionSOS: MobileGestaltTweak("HCzWusHQwZDea6nNhaKndw"),
        TweakID.TapToWake: MobileGestaltTweak("yZf3GTRMGTuwSV/lD7Cagw"),
        TweakID.CameraButton: MobileGestaltMultiTweak({"CwvKxM2cEogD3p+HYgaW0Q": 1, "oOV1jhJbdV3AddkcCg0AEA": 1}),
        TweakID.Parallax: MobileGestaltTweak("UIParallaxCapability", value=0),
        TweakID.StageManager: MobileGestaltTweak("qeaj75wk3HF4DwQ8qbIi7g", value=1),
        TweakID.iPadOS: MobileGestaltMultiTweak({"mG0AnH/Vy1veoqoLRAIgTA": 1, "UCG5MkVahJxG1YULbbd5Bg": 1, "ZYqko/XM5zD3XBfN5RmaXA": 1, "nVh/gwNpy7Jv1NOk00CMrw": 1, "uKc7FPnEO++lVhHWHFlGbQ": 1}),
        TweakID.iPadOSCacheData: MobileGestaltCacheDataTweak(slice_start=1616, slice_length=200),
        TweakID.iPadApps: MobileGestaltTweak("9MZ5AdH43csAUajl/dU+IQ", value=[1, 2]),
        TweakID.Shutter: MobileGestaltMultiTweak({"h63QSdBCiT/z0WU6rdQv6Q": "US", "zHeENZu+wbg7PUprwNwBWg": "LL/A"}),
        TweakID.Pencil: MobileGestaltTweak("yhHcB0iH0d1XzPO/CFd3ow"),
        TweakID.ActionButton: MobileGestaltTweak("cT44WE1EohiwRzhsZ8xEsw"),
        TweakID.InternalStorage: MobileGestaltTweak("LBJfwOEzExRxzlAnSuI7eg"),
        TweakID.InternalInstall: MobileGestaltTweak("EqrsVvjcYDdxHBiQmGhAWw"),
        TweakID.SRD: MobileGestaltTweak("XYlJKKkj2hztRP1NWWnhlw"),
        TweakID.AOD: MobileGestaltMultiTweak(
                                {"2OOJf1VhaM7NxfRok3HbWQ": 1, "j8/Omm6s1lsmTDFsXjsBfA": 1}),
        TweakID.AODVibrancy: MobileGestaltTweak("ykpu7qyhqFweVMKtxNylWA")
    }


def load_mobilegestalt(version: str = ""):
    """Register Nugget's MobileGestalt tweaks (idempotent).

    Version rule follows Nugget upstream 100%: MobileGestalt is not
    supported on iOS 26.2+ (never will be). It stays available on
    iOS 26.1 and below.
    """
    if TweakID.DynamicIsland in tweaks:
        return
    try:
        if version and Version(str(version)) >= Version("26.2"):
            return
    except Exception:
        return
    tweaks.update(get_mobilegestalt_tweaks())


def _build_spec(spec):
    if spec.factory is not None:
        return spec.factory()
    return BasicPlistTweak(spec.location, spec.key, value=spec.value)


def load_plist_tweaks():
    """Register every registry-defined tweak that isn't loaded yet (idempotent).

    Specs marked ``disabled`` are cut off entirely: they are never registered,
    so they neither render nor apply.
    """
    tweaks.update({spec.id: _build_spec(spec) for spec in SPECS
                   if spec.id not in tweaks and not spec.disabled})


def load_daemons():
    if TweakID.Daemons in tweaks:
        return
    # Daemons start empty; each interface toggle adds its own keys. Only
    # interface-visible keys (INTERFACE_KEYS) survive filtering, so unrelated
    # or hidden daemons can never leak into the apply pass or a stored preset.
    defaults = {}
    tweaks.update({
        TweakID.Daemons: AdvancedPlistTweak(
            FileLocation.disabledDaemons,
            defaults,
            owner=0, group=0,
            never_enable=DANGEROUS_KEYS,
            allowed_keys=INTERFACE_KEYS,
        ),
        TweakID.ClearScreenTimeAgentPlist: NullifyFileTweak(FileLocation.screentime),
    })