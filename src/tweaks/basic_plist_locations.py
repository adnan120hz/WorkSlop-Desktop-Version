from enum import Enum

class FileLocation(Enum):
    # Feature Flags
    featureflags = "/var/preferences/FeatureFlags/Global.plist"
    
    # SpringBoard Options
    springboard = "/var/Managed Preferences/mobile/com.apple.springboard.plist"
    footnote = "/var/containers/Shared/SystemGroup/systemgroup.com.apple.configurationprofiles/Library/ConfigurationProfiles/SharedDeviceConfiguration.plist"
    airdrop = "/var/Managed Preferences/mobile/com.apple.sharingd.plist"
    nanoregistry = "/var/mobile/Library/Preferences/com.apple.NanoRegistry.plist"

    # Status Bar
    # iOS 27+: SpringBoard unarchives the carrier name from this file.
    # iOS 26 and below used the classic struct at
    # /var/mobile/Library/SpringBoard/statusBarOverrides instead.
    statusBarOverridesArchive = "/var/mobile/Library/SpringBoard/StatusBarOverrides.archive"
    
    # Internal Options
    globalPreferences = "/var/Managed Preferences/mobile/.GlobalPreferences.plist"
    globalPreferencesHomeDomain = "/var/mobile/Library/Preferences/.GlobalPreferences.plist"
    appStore = "/var/Managed Preferences/mobile/com.apple.AppStore.plist"
    backboardd = "/var/Managed Preferences/mobile/com.apple.backboardd.plist"
    coreMotion = "/var/Managed Preferences/mobile/com.apple.CoreMotion.plist"
    pasteboard = "/var/Managed Preferences/mobile/com.apple.Pasteboard.plist"
    notes = "/var/Managed Preferences/mobile/com.apple.mobilenotes.plist"
    uikit = "/var/Managed Preferences/mobile/com.apple.UIKit.plist"
    # Accessibility (managed). Used by the Liquid Glass "Increase Contrast"
    # mitigation tweak — managed prefs override the HomeDomain copy.
    accessibility = "/var/Managed Preferences/mobile/com.apple.Accessibility.plist"
    # Per-app managed preferences — Liquid Glass per-app ("apps") focus
    # (2026-10-01). Each app reads its own bundle domain first, so a
    # per-app UserDefaults key can override the global
    # .GlobalPreferences.plist value. Delivered via ManagedPreferencesDomain,
    # the same channel as every other managed tweak on this page.
    appMessages = "/var/Managed Preferences/mobile/com.apple.MobileSMS.plist"
    appSafari = "/var/Managed Preferences/mobile/com.apple.mobilesafari.plist"
    appSettings = "/var/Managed Preferences/mobile/com.apple.Preferences.plist"
    appMail = "/var/Managed Preferences/mobile/com.apple.mobilemail.plist"
    appPhotos = "/var/Managed Preferences/mobile/com.apple.mobileslideshow.plist"
    appCamera = "/var/Managed Preferences/mobile/com.apple.camera.plist"
    appPhone = "/var/Managed Preferences/mobile/com.apple.mobilephone.plist"

    # Daemons
    disabledDaemons = "/var/db/com.apple.xpc.launchd/disabled.plist"
    screentime = "/var/mobile/Library/Preferences/com.apple.ScreenTimeAgent.plist"

    # MobileGestalt cache (ported from leminlimez/Nugget)
    mga = "/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches/com.apple.MobileGestalt.plist"
    # (ported from leminlimez/Nugget; used by RdarFixTweak/CustomResolution)
    resolution = "/var/Managed Preferences/mobile/com.apple.iokit.IOMobileGraphicsFamily.plist"

    # Risky Options (ported from leminlimez/Nugget)
    ota = "/var/Managed Preferences/mobile/com.apple.MobileAsset.plist"
