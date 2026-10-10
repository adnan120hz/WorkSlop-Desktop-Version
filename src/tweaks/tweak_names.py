from enum import Enum, auto

class TweakID(Enum):
    # tweaks page
    PosterBoard = auto()
    Templates = auto()
    StatusBar = auto()
    IconThemes = auto()

    # springboard
    LockScreenFootnote = auto()
    WatchOSCompatibility = auto()
    AirDropDisableTimeLimit = auto()
    SBDontLockAfterCrash = auto()
    SBDontDimOrLockOnAC = auto()
    SBHideLowPowerAlerts = auto()
    SBHideACPower = auto()
    SBNeverBreadcrumb = auto()
    SBShowSupervisionTextOnLockScreen = auto()
    AirplaySupport = auto()
    SBMinimumLockscreenIdleTime = auto()
    SBAlwaysShowSystemApertureInSnapshots = auto()
    HideDICompletely = auto()
    SBShowAuthenticationEngineeringUI = auto()
    UseFloatingTabBar = auto()
    SBDisableIconParallax = auto()
    SBHideSearchAffordance = auto()

    # mobilegestalt (ported from leminlimez/Nugget; not supported on iOS 26.2+)
    DynamicIsland = auto()
    SupportsDynamicIsland = auto()
    ModelName = auto()
    BootChime = auto()
    EnableLGLPM = auto()
    DisableLGLPM = auto()
    RdarFix = auto()
    ChargeLimit = auto()
    CollisionSOS = auto()
    TapToWake = auto()
    CameraButton = auto()
    Parallax = auto()
    StageManager = auto()
    iPadOS = auto()
    iPadOSCacheData = auto()
    iPadApps = auto()
    Shutter = auto()
    Pencil = auto()
    ActionButton = auto()
    InternalStorage = auto()
    InternalInstall = auto()
    SRD = auto()
    AOD = auto()
    AODVibrancy = auto()
    # NOTE: in leminlimez/Nugget this tweak lives in load_eligibility()
    # (eligibility page); the tweak definition itself is verbatim.
    AIGestalt = auto()

    # eligibility (ported verbatim from leminlimez/Nugget's load_eligibility();
    # removed by GoldenNugget, re-added here using Nugget's original code)
    EUEnabler = auto()
    AIEligibility = auto()
    AIFeatureFlags = auto()
    AIFeatureFlagsUI = auto()
    SpoofModel = auto()
    SpoofHardware = auto()
    SpoofCPU = auto()
    CreateBRFolders = auto()

    # feature flags (ported from leminlimez/Nugget; removed by GoldenNugget,
    # re-added here using Nugget's original flag definitions)
    ClockAnim = auto()
    Lockscreen = auto()
    PhotoUI = auto()
    AI = auto()
    KioskMode = auto()

    # internal
    SBBuildNumber = auto()
    RTL = auto()
    LTR = auto()
    SBIconVisibility = auto()
    # NOTE: MetalForceHudEnabled was removed (audit B28) — upstream Nugget's
    # load_internal() defines it, but this fork carries no spec for it.
    iMessageDiagnosticsEnabled = auto()
    IDSDiagnosticsEnabled = auto()
    VCDiagnosticsEnabled = auto()
    AccessoryDeveloperEnabled = auto()
    KeyFlick = auto()
    DisableThermal = auto()

    DisableSecondsHand = auto()
    DisableSearchingWebsites = auto()
    ShowButtonHints = auto()

    AppStoreDebug = auto()
    NotesDebugMode = auto()
    BKDigitizerVisualizeTouches = auto()
    BKHideAppleLogoOnLaunch = auto()
    EnableWakeGestureHaptic = auto()
    PlaySoundOnPaste = auto()
    AnnounceAllPastes = auto()

    # liquid glass — Round 6 (2026-10-02, per user order): 71 audited candidates
    # added for pre-beta developer release. None device-tested yet.
    # See ~/workspace/riset/AUDIT-KANDIDAT-BARU.md for audit details.
    SolariumForceFallback = auto()
    # Deprecated alias for backward compat with old presets (pre-4.0)
    ForceSolariumFallback = SolariumForceFallback
    DisableSolariumSwiftUI = auto()
    GlassLegibility2 = auto()
    SolariumFeatureFlags = auto()
    GranularSpringBoard = auto()
    LGLPMGestalt = auto()
    DisallowGlassTime = auto()
    DisableLockScreenSpecular = auto()
    DisableClockSpecular = auto()
    DisableGlassLockScreen = auto()
    DisableGlassDock = auto()
    FlatIconsEverywhere = auto()
    DisableWidgetSpecular = auto()
    DisableDockSpecular = auto()
    DisableFolderSpecular = auto()
    ExcludeClearGlassShadows = auto()
    ExcludeDockShadow = auto()
    ExcludeSearchShadow = auto()
    DisableOuterRefraction = auto()
    DisableSolariumHDR = auto()
    DisableSpecularMotion = auto()
    DisableCompactChrome = auto()
    DisableSpecularEverywhere = auto()
    SuppressDICompletely = auto()
    DisableGlassDI = auto()
    DisallowGlassDI = auto()
    DisableIslandSpecular = auto()
    DisableGlassEverywhere = auto()
    DisallowGlassEverywhere = auto()
    DisableRefractionEverywhere = auto()
    ExcludeAllGlassShadows = auto()
    FlatDockEverywhere = auto()
    DisableGlassBlur = auto()
    DisallowGlassKeyboard = auto()
    # Blurr Motion (2026-10-03): the single candidate from the DesignLibrary
    # dossier whose key string is attested in the 23G83 binary
    # (~/workspace/riset/wave11/DOSSIER-BLURR-MOTION.md). Normal tweak, no
    # badge: its untested status lives in its description, not a lock.
    BlurrMotion = auto()
    # status bar visual (non-glass)
    StatusBarOverrides = auto()
    ShowSystemServices = auto()
    ShowBatteryPercentage = auto()
    # lock screen custom (non-glass)
    CustomLockDate = auto()
    # notifications (non-glass, Apple keys)
    NotifDisplayStyle = auto()
    NotifPreview = auto()
    NotifScheduled = auto()
    NotifSummarize = auto()
    NotifAnnounce = auto()
    NotifHighlights = auto()
    NotifAlertType = auto()
    NotifGrouping = auto()
    NotifVisibility = auto()
    NotifPriority = auto()
    # home screen non-glass
    DisableParallax = auto()
    HideSearchAffordance = auto()
    IconVisibility = auto()
    DisableClockSeconds = auto()
    # keyboard (non-glass)
    KbAutocorrect = auto()
    KbPrediction = auto()
    KbPredBar = auto()
    KbGestureIntro = auto()
    KbAutoLists = auto()
    # siri classic (non-glass)
    SiriEnabled = auto()
    SiriDataSharing = auto()
    SiriAutoPunct = auto()
    SiriVoiceTrigger = auto()
    SiriTriggerPhrase = auto()
    SiriSpeakerTTS = auto()
    SiriDeclined = auto()
    SiriVocab = auto()
    # animation (non-glass)
    AnimDragCoeff = auto()

    # risky (ported from leminlimez/Nugget's load_risky())
    DisableOTAFile = auto()
    CustomResolution = auto()

    # daemons
    Daemons = auto()
    ClearScreenTimeAgentPlist = auto()

    # Liquid Glass Tweaks (Nugget) — verbatim from leminlimez/Nugget
    # v7.4.1 (src/tweaks/nugget_lg.py). Own IDs so the Nugget set lives
    # next to, never inside, the WorkSlop v4 set above.
    NuggetForceSolariumFallback = auto()
    NuggetDisableSolarium = auto()
    NuggetIgnoreSolariumLinkedOnCheck = auto()
    NuggetNoLiquidClock = auto()
    NuggetNoLiquidDock = auto()
    NuggetDisableSpecularMotion = auto()
    NuggetDisableOuterRefraction = auto()
    NuggetDisableSolariumHDR = auto()
    NuggetSolariumFFSwiftUI = auto()
    NuggetSolariumFFSpringBoard = auto()
    NuggetSolariumFFIconServices = auto()
    NuggetSolariumFFDocumentCamera = auto()
    NuggetSolariumFFPhotos = auto()
    NuggetSolariumFFAppleMediaServices = auto()
    NuggetSolariumFFSharing = auto()
    NuggetSolariumFFMail = auto()

    # Liquid Glass Disable (Beta 1) — added 2026-10-04 as two delivery
    # routes for the Beta 1 SolariumForceFallback key; REMOVED from the
    # product in v14.0 by explicit user order (2026-10-07: "G1 G2 ga
    # work, hapus") after beta testing showed no effect. The enum
    # members stay as tombstones so old presets/journals naming them
    # still parse; they are recorded in REMOVED_TWEAK_IDS
    # (src/tweaks/capabilities.py) and must never resolve to an active
    # spec or payload again. The shared payload helpers live on in
    # src/tweaks/lg_disable.py (consumed by Squair + Latest).
    LGDisableG2 = auto()  # tombstone: managed overlay route (removed v14.0)
    LGDisableG1 = auto()  # tombstone: device file merge route (removed v14.0)

    # Squair Protocol (test) — test-only payload (2026-10-07): two
    # GlobalPreferences keys + a FeatureFlags/Domain file riding the
    # full-backup route. Own ID. See src/tweaks/lg_squair.py.
    LGDisableSquairTest = auto()

    # Liquid Glass (Latest) — REMOVED in v15 (user order 2026-10-10)
    # together with the "Liquid Glass iOS 26.6.1 RC S8" feature: the
    # author's own device test (2026-10-10) showed no on-screen effect.
    # Tombstone only — the member stays so old presets/journals naming
    # it still parse; it is recorded in REMOVED_TWEAK_IDS
    # (src/tweaks/capabilities.py) and must never resolve to an active
    # spec or payload again. src/tweaks/lg_latest.py survives only as
    # the rollback planner that strips this payload's keys from devices
    # that applied it under v14.
    LGDisableLatest = auto()  # tombstone: S8/Latest route (removed v15)

    # Liquid Glass firmware-research specs (2026-10-10): real Apple
    # firmware keys located by diffing iOS 26.1 (23B85) against iOS
    # 26.6.1 RC (23G82); each key's reader is verified alive in the
    # 26.6.1 firmware. The on-screen effect of every entry here is NOT
    # proven — see their registry descriptions.
    LGForceFallbackUIKit = auto()
    # Tombstone since v15.1 (user order 2026-10-10): the SwiftUI
    # enable switch is removed from the product (device-verdict: it
    # works but could not be switched back off — see the registry
    # note). The member stays so old presets/journals naming it still
    # parse; it is recorded in REMOVED_TWEAK_IDS
    # (src/tweaks/capabilities.py) and must never resolve to an active
    # spec or payload again. The Remove Tweaks dialog writes its key
    # back to false instead.
    LGForceFallbackSwiftUI = auto()  # tombstone: SwiftUI fallback enable (removed v15.1)
    LGNoBlurReducedFrost = auto()