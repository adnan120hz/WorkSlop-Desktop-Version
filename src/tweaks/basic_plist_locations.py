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

    # Daemons
    disabledDaemons = "/var/db/com.apple.xpc.launchd/disabled.plist"
    screentime = "/var/mobile/Library/Preferences/com.apple.ScreenTimeAgent.plist"

    # MobileGestalt cache (ported from leminlimez/Nugget)
    mga = "/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches/com.apple.MobileGestalt.plist"
