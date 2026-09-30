from .tweaks import tweaks, TweakID
from .registry import SPECS
from .basic_plist_locations import FileLocation
from .tweak_classes import (
    BasicPlistTweak, AdvancedPlistTweak, NullifyFileTweak,
    MobileGestaltTweak, MobileGestaltPickerTweak,
    MobileGestaltMultiTweak, MobileGestaltCacheDataTweak,
    RdarFixTweak, FeatureFlagTweak,
)
from .eligibility_tweak import EligibilityTweak, AITweak, BookRestoreFileTweak
from .daemons_tweak import DANGEROUS_KEYS, INTERFACE_KEYS, UPSTREAM_DEFAULT_DAEMONS
from src.devicemanagement.constants import is_gestalt_supported_build


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
        TweakID.AODVibrancy: MobileGestaltTweak("ykpu7qyhqFweVMKtxNylWA"),
        # Ported verbatim from leminlimez/Nugget's load_eligibility()
        # (src/tweaks/tweak_loader.py). Nugget wires it to the eligibility
        # page's "Enable Apple Intelligence (for Unsupported Devices)"
        # checkbox; the tweak definition itself is identical.
        TweakID.AIGestalt: MobileGestaltTweak("A62OafQ85EJAiiqKn4agtg"),
    }


def load_rdar_fix(dev=None):
    """Ported from leminlimez/Nugget's load_rdar_fix()
    (src/tweaks/tweak_loader.py). In Nugget this is called from
    load_mobilegestalt(dev); here it is called from the MobileGestalt page's
    refresh() right after load_mobilegestalt(), because this fork's loader
    takes a build string (build gate) instead of the device.
    """
    if TweakID.RdarFix in tweaks:
        return
    tweaks.update({TweakID.RdarFix: RdarFixTweak()})
    if dev is not None:
        # load settings
        model = getattr(dev, "model", "") or ""
        tweaks[TweakID.RdarFix].get_rdar_mode(model)


def load_mobilegestalt(build: str = ""):
    """Register Nugget's MobileGestalt tweaks (idempotent).

    Build rule (user decision 2026-09-30): tweaks register only on
    iOS 16.0 -> iOS 26.2 beta 1 builds. Build-based (not version-based)
    so 26.2 beta 1 stays included while later 26.2 builds stay out.
    """
    if TweakID.DynamicIsland in tweaks:
        return
    try:
        if build and not is_gestalt_supported_build(build):
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
    # REAUDIT FIX: was a forked copy of the B22 dict — now uses the single
    # source of truth UPSTREAM_DEFAULT_DAEMONS from daemons_tweak.py so the
    # apply seed and the reset can never drift apart.
    defaults = dict(UPSTREAM_DEFAULT_DAEMONS)
    tweaks.update({
        TweakID.Daemons: AdvancedPlistTweak(
            FileLocation.disabledDaemons,
            defaults,
            owner=0, group=0,
            never_enable=DANGEROUS_KEYS,
            allowed_keys=INTERFACE_KEYS | frozenset(defaults),
        ),
        TweakID.ClearScreenTimeAgentPlist: NullifyFileTweak(FileLocation.screentime),
    })

def load_risky():
    """Ported from leminlimez/Nugget's load_risky()
    (src/tweaks/tweak_loader.py). Tweak definitions are verbatim.

    One adaptation: Nugget marks these ``is_risky=True`` and gates them
    behind a ``risky_allowed`` apply flag. This fork's tweak classes have no
    risky gating (GoldenNugget removed it), so the flag is dropped and the
    tweaks apply like any other enabled tweak. The key/value payloads are
    identical to upstream.
    """
    if TweakID.CustomResolution in tweaks:
        return
    additional_tweaks = {
        TweakID.DisableOTAFile: AdvancedPlistTweak(
            FileLocation.ota,
            {
                "MobileAssetServerURL-com.apple.MobileAsset.MobileSoftwareUpdate.UpdateBrain": "https://mesu.apple.com/assets/tvOS16DeveloperSeed",
                "MobileAssetSUAllowOSVersionChange": False,
                "MobileAssetSUAllowSameVersionFullReplacement": False,
                "MobileAssetServerURL-com.apple.MobileAsset.RecoveryOSUpdate": "https://mesu.apple.com/assets/tvOS16DeveloperSeed",
                "MobileAssetServerURL-com.apple.MobileAsset.RecoveryOSUpdateBrain": "https://mesu.apple.com/assets/tvOS16DeveloperSeed",
                "MobileAssetServerURL-com.apple.MobileAsset.SoftwareUpdate": "https://mesu.apple.com/assets/tvOS16DeveloperSeed",
                "MobileAssetAssetAudience": "65254ac3-f331-4c19-8559-cbe22f5bc1a6"
            }
        ),
        TweakID.CustomResolution: AdvancedPlistTweak(
            FileLocation.resolution,
            {}, # empty as to not cause issues when only 1 value is inputted
        )
    }
    tweaks.update(additional_tweaks)


def load_eligibility(dev=None):
    """Ported from leminlimez/Nugget's load_eligibility()
    (src/tweaks/tweak_loader.py). Tweak definitions are verbatim.

    Two deliberate adaptations (documented, logic unchanged):
    - Guard is on TweakID.EUEnabler, not TweakID.AIGestalt: this fork loads
      AIGestalt via get_mobilegestalt_tweaks(), so Nugget's original guard
      would wrongly skip the whole module once the MobileGestalt page ran.
    - TweakID.AIGestalt is not re-added here: it already comes from
      get_mobilegestalt_tweaks() with the identical definition. Re-adding
      would replace the instance and clobber the switch state.
    """
    if TweakID.EUEnabler in tweaks:
        return
    additional_tweaks = {
        TweakID.EUEnabler: EligibilityTweak(),
        TweakID.AIEligibility: AITweak(),
        TweakID.AIFeatureFlags: FeatureFlagTweak(flag_category="Siri", flag_names=['sae_override', 'assistant_engine_override']),
        TweakID.AIFeatureFlagsUI: FeatureFlagTweak(flag_category="SiriUI", flag_names=["sae"]),
        TweakID.SpoofModel: MobileGestaltPickerTweak("h9jDsbgj7xIVeIQ8S3/X3Q", values=[
            # Default
            "Placeholder", # 0 | Original

            # iPhone
            "iPhone16,1", # 1 | iPhone 15 Pro
            "iPhone16,2", # 2 | iPhone 15 Pro Max
            "iPhone17,3", # 3 | iPhone 16
            "iPhone17,4", # 4 | iPhone 16 Plus
            "iPhone17,1", # 5 | iPhone 16 Pro
            "iPhone17,2", # 6 | iPhone 16 Pro Max
            "iPhone18,3", # 7 | iPhone 17

            # A17 Pro iPads
            "iPad16,1", # 8 | iPad Mini (A17 Pro) (W)
            "iPad16,2", # 9 | iPad Mini (A17 Pro) (C)
        
            # M4 iPads
            "iPad16,5", # 10 | iPad Pro (13-inch) (M4) (W)
            "iPad16,6", # 11 | iPad Pro (13-inch) (M4) (C)
            "iPad16,3", # 12 | iPad Pro (11-inch) (M4) (W)
            "iPad16,4", # 13 | iPad Pro (11-inch) (M4) (C)

            # M2 iPads
            "iPad14,5", # 14 | iPad Pro (12.9-inch) (M2) (W)
            "iPad14,6", # 15 | iPad Pro (12.9-inch) (M2) (C)
            "iPad14,3", # 16 | iPad Pro (11-inch) (M2) (W)
            "iPad14,4", # 17 | iPad Pro (11-inch) (M2) (C)
            "iPad14,10", # 18 | iPad Air (13-inch) (M2) (W)
            "iPad14,11", # 19 | iPad Air (13-inch) (M2) (C)
            "iPad14,8", # 20 | iPad Air (11-inch) (M2) (W)
            "iPad14,9", # 21 | iPad Air (11-inch) (M2) (C)

            # M1 iPads
            "iPad13,4", # 22 | iPad Pro (11-inch) (M1) (W)
            "iPad13,5", # 23 | iPad Pro (11-inch) (M1) (C)
            "iPad13,8", # 24 | iPad Pro (12.9-inch) (M1) (W)
            "iPad13,9", # 25 | iPad Pro (12.9-inch) (M1) (C)
            "iPad13,16", # 26 | iPad Air (M1) (W)
            "iPad13,17", # 27 | iPad Air (M1) (C)
        ]),
        TweakID.SpoofHardware: MobileGestaltPickerTweak("oYicEKzVTz4/CxxE05pEgQ", values=[
            # Default
            "Placeholder", # 0 | Original

            # iPhone
            "D83AP", # 1 | iPhone 15 Pro
            "D84AP", # 2 | iPhone 15 Pro Max
            "D47AP", # 3 | iPhone 16
            "D48AP", # 4 | iPhone 16 Plus
            "D93AP", # 5 | iPhone 16 Pro
            "D94AP", # 6 | iPhone 16 Pro Max
            "V57AP", # 7 | iPhone 17

            # A17 Pro iPads
            "J410AP", # 8 | iPad Mini (A17 Pro) (W)
            "J411AP", # 9 | iPad Mini (A17 Pro) (C)
        
            # M4 iPads
            "J720AP", # 10 | iPad Pro (13-inch) (M4) (W)
            "J721AP", # 11 | iPad Pro (13-inch) (M4) (C)
            "J717AP", # 12 | iPad Pro (11-inch) (M4) (W)
            "J718AP", # 13 | iPad Pro (11-inch) (M4) (C)

            # M2 iPads
            "J620AP", # 14 | iPad Pro (12.9-inch) (M2) (W)
            "J621AP", # 15 | iPad Pro (12.9-inch) (M2) (C)
            "J617AP", # 16 | iPad Pro (11-inch) (M2) (W)
            "J618AP", # 17 | iPad Pro (11-inch) (M2) (C)
            "J537AP", # 18 | iPad Air (13-inch) (M2) (W)
            "J538AP", # 19 | iPad Air (13-inch) (M2) (C)
            "J507AP", # 20 | iPad Air (11-inch) (M2) (W)
            "J508AP", # 21 | iPad Air (11-inch) (M2) (C)

            # M1 iPads
            "J517AP", # 22 | iPad Pro (11-inch) (M1) (W)
            "J517xAP", # 23 | iPad Pro (11-inch) (M1) (C)
            "J522AP", # 24 | iPad Pro (12.9-inch) (M1) (W)
            "J522xAP", # 25 | iPad Pro (12.9-inch) (M1) (C)
            "J407AP", # 26 | iPad Air (M1) (W)
            "J408AP", # 27 | iPad Air (M1) (C)
        ]),
        TweakID.SpoofCPU: MobileGestaltPickerTweak("5pYKlGnYYBzGvAlIU8RjEQ", values=[
            # Default
            "Placeholder", # 0 | Original

            # iPhone
            "t8130", # 1 | iPhone 15 Pro
            "t8130", # 2 | iPhone 15 Pro Max
            "t8140", # 3 | iPhone 16
            "t8140", # 4 | iPhone 16 Plus
            "t8140", # 5 | iPhone 16 Pro
            "t8140", # 6 | iPhone 16 Pro Max
            "t8150", # 7 | iPhone 17

            # A17 Pro iPads
            "t8130", # 8 | iPad Mini (A17 Pro) (W)
            "t8130", # 9 | iPad Mini (A17 Pro) (C)
        
            # M4 iPads
            "t8182", # 10 | iPad Pro (13-inch) (M4) (W)
            "t8182", # 11 | iPad Pro (13-inch) (M4) (C)
            "t8182", # 12 | iPad Pro (11-inch) (M4) (W)
            "t8182", # 13 | iPad Pro (11-inch) (M4) (C)

            # M2 iPads
            "t8112", # 14 | iPad Pro (12.9-inch) (M2) (W)
            "t8112", # 15 | iPad Pro (12.9-inch) (M2) (C)
            "t8112", # 16 | iPad Pro (11-inch) (M2) (W)
            "t8112", # 17 | iPad Pro (11-inch) (M2) (C)
            "t8112", # 18 | iPad Air (13-inch) (M2) (W)
            "t8112", # 19 | iPad Air (13-inch) (M2) (C)
            "t8112", # 20 | iPad Air (11-inch) (M2) (W)
            "t8112", # 21 | iPad Air (11-inch) (M2) (C)

            # M1 iPads
            "t8103", # 22 | iPad Pro (11-inch) (M1) (W)
            "t8103", # 23 | iPad Pro (11-inch) (M1) (C)
            "t8103", # 24 | iPad Pro (12.9-inch) (M1) (W)
            "t8103", # 25 | iPad Pro (12.9-inch) (M1) (C)
            "t8103", # 26 | iPad Air (M1) (W)
            "t8103", # 27 | iPad Air (M1) (C)
        ])
    }
    # load settings
    if dev != None:
        additional_tweaks[TweakID.SpoofModel].value[0] = dev.model
        additional_tweaks[TweakID.SpoofHardware].value[0] = dev.hardware
        additional_tweaks[TweakID.SpoofCPU].value[0] = dev.cpu
    # add to tweaks
    tweaks.update(additional_tweaks)
    # AIGestalt is Nugget's eligibility-page switch for Apple Intelligence;
    # this fork provides it via get_mobilegestalt_tweaks(). Ensure it exists
    # so the Eligibility section works even if the MobileGestalt page never
    # loaded (identical verbatim definition, only added when missing).
    if TweakID.AIGestalt not in tweaks:
        tweaks[TweakID.AIGestalt] = MobileGestaltTweak("A62OafQ85EJAiiqKn4agtg")
