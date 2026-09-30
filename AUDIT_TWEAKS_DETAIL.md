# AUDIT TWEAKS DETAIL — WorkSlop Desktop

**Repo:** `~/workspace/desk` · **Branch:** `main` · **HEAD saat audit:** `4624960`
**Tanggal:** 2026-09-30 · **Metode:** read-only, 5 auditor paralel, tiap temuan diverifikasi ke `file:line`
**UI tidak disentuh** (frozen). Laporan ini hanya soal tweaks.

> Aturan status: **OK** = ter-wire ke Apply dan logika kode benar. **BUG** = cacat dengan `file:line`.
> **GIMMICK** = UI doang, tidak ada efek. **UNVERIFIED** = tidak bisa dibuktikan tanpa iPhone asli
> (apakah iOS benar-benar menghormati key/nilai tersebut). Hampir semua tweak berstatus
> OK-secara-kode **tapi** UNVERIFIED-secara-device — dua hal berbeda, jangan dicampur.

## Ringkasan eksekutif

| Keluarga tweak | Jumlah toggle | OK (kode) | BUG | GIMMICK | UNVERIFIED (efek device) |
|---|---|---|---|---|---|
| SpringBoard (plist) | 17 | 16 | 1 (B9) | 0 | 17 |
| Internal Options (plist) | 19 | 19 | 0* | 0 | 19 |
| Feature Flags | 13 | 12 | 1 (B6) | 0 | 13 |
| Liquid Glass / Solarium | 98 | 98 | 0 | 0 | 98 (key tanpa provenansi) |
| MobileGestalt | 23 | 20 | 3 (B2,B5 parsial) | 0 | 23 |
| Eligibility | 9 | 8 | 1 (B3/B8) | 0 | 9 |
| RdarFix | 1 | 0 | 1 (B5) | 0 | 1 |
| Risky (OTA, CustomResolution) | 2 | 1 | 1 (B5) | 0 | 2 |
| Daemons | ~14 | 12 | 2 (B12,B25) | 0 | 14 |
| Status Bar | 31 | 17 | 14 (B9) | 0 | 31 |
| Icon Themes | 3 | 2 | 1 (B18) | 0 | 3 |
| PosterBoard | 9 | 9 | 0 | 0 | 9 |
| **TOTAL** | **~239** | — | **34 temuan unik** | **1** | **~239** |

*Internal Options: kodenya benar, tapi 11 di antaranya memicu bug HIGH B1 (GP replace) di iOS 27.

**Temuan unik: 34** (5 HIGH, ~13 MEDIUM/MAJOR, sisanya LOW/INFO). **GIMMICK: 1**
(EUEnabler Method 1/2 — pilihannya no-op). **Tidak ditemukan switch mati total** selain itu —
semua toggle lain punya cabang handler di apply flow (klaim "no GIMMICK" dari auditor plist
terverifikasi untuk 147 specs).

**Klaim prior terverifikasi dalam audit ini:**
- Port verbatim dari leminlimez/Nugget: **TERBUKTI** untuk MobileGestalt (23/23 identik),
  Eligibility (char-identical kecuali import), RdarFix (identik), Feature Flags, SpringBoard,
  Internal, Risky, Daemons (dengan 4 deviasi kecil yang didokumentasikan di bawah).
- K3 wiring MobileGestalt/Eligibility ke Apply: **TERBUKTI** (`device_manager.py:1171-1181`,
  `1227-1240`).
- Zip-slip icon_themes: **SUDAH FIX** (`icon_themes_tweak.py:170` → `_safe_extractall`).
  Tapi zip-slip **masih hidup** di `.tendies` dan `.batter` (B2, B3).
- Klaim AGENTS.md "bundled base plist" untuk GP: **SALAH** — tidak ada base plist di repo.

---

## 1. SpringBoard — 17 tweak (`src/tweaks/registry.py:575-627`, UI `src/gui/ios/tweaks.py:293-310`)

Apply: `device_manager.py:1109` (BasicPlistTweak). Semua upstream-verbatim kecuali 2 adisi fork.

| Tweak ID | Display name | Payload (file / key = value) | Key real? | Revert | Status |
|---|---|---|---|---|---|
| LockScreenFootnote | Lock Screen Footnote Text | footnote plist / `LockScreenFootnote`="" | UNVERIFIED | **Tidak** (B24) | UNVERIFIED |
| WatchOSCompatibility | Allow pairing with any watchOS version | nanoregistry / `_watchos_compatibility` dict | UNVERIFIED | **Tidak** | **BUG B9** — `ipad_only=True` (`registry.py:578-580`), tidak bisa diakses di iPhone |
| AirDropDisableTimeLimit | Disable AirDrop Time Limit for Everyone Option | airdrop / `OverrideTimeLimitEveryoneMode`=True | plausible, UNVERIFIED | **Tidak** | UNVERIFIED |
| SBDontLockAfterCrash | Disable Lock After Respring | springboard / `SBDontLockAfterCrash`=True | Real (well-known) | Ya (`:1421-1422`) | OK |
| SBDontDimOrLockOnAC | Disable Screen Dimming While Charging | springboard / `SBDontDimOrLockOnAC`=True | Real | Ya | OK |
| SBHideLowPowerAlerts | Disable Low Battery Alerts | springboard / `SBHideLowPowerAlerts`=True | Real | Ya | OK |
| SBHideACPower | Hide AC Power on Lock Screen | springboard / `SBHideACPower`=True | Real | Ya | OK |
| SBNeverBreadcrumb | Disable Breadcrumbs | springboard / `SBNeverBreadcrumb`=True | Real | Ya | OK |
| SBShowSupervisionTextOnLockScreen | Show Supervision Text on Lock Screen | springboard / `SBShowSupervisionTextOnLockScreen`=True | plausible, UNVERIFIED | Ya | UNVERIFIED |
| AirplaySupport | Enable AirPlay support for Stage Manager | springboard / `SBExtendedDisplayOverrideSupportForAirPlayAndDontFileRadars`=True | Real | Ya | OK |
| SBMinimumLockscreenIdleTime | Auto-Lock (Lock Screen) | springboard / `SBMinimumLockscreenIdleTime`=5 (0–600) | Real | Ya | OK |
| SBAlwaysShowSystemApertureInSnapshots | Show Dynamic Island in Screenshots | springboard / `SBAlwaysShowSystemApertureInSnapshots`=True | Real | Ya | OK |
| HideDICompletely | Hide Dynamic Island Completely | springboard / `SBSuppressDynamicIslandCompletely`=True | plausible, UNVERIFIED | Ya | UNVERIFIED |
| SBShowAuthenticationEngineeringUI | Show Red/Green Authentication Line | springboard / `SBShowAuthenticationEngineeringUI`=True | plausible, UNVERIFIED | Ya | UNVERIFIED |
| UseFloatingTabBar | Disable Floating Tab Bar | uikit / `UseFloatingTabBar`=**False** (iPad-only) | plausible, UNVERIFIED | Ya | UNVERIFIED |
| SBDisableIconParallax | Disable Icon Parallax | springboard / `SBDisableParallax`=True | Real | Ya | OK (adisi fork) |
| SBHideSearchAffordance | Hide Search Button on Home Screen | springboard / `SBHomeScreenShowsSearchAffordance`=**False** | plausible, UNVERIFIED | Ya | UNVERIFIED (adisi fork) |

## 2. Internal Options — 19 tweak (`src/tweaks/registry.py:629-666`)

Apply: `device_manager.py:1109`. Revert: `device_manager.py:1440-1448` (Page.InternalOptions).
11 tweak bertarget `FileLocation.globalPreferences` → memicu **BUG B1** di iOS 27.

| Tweak ID | Display name | Payload (file / key = value) | Key real? | Status |
|---|---|---|---|---|
| SBBuildNumber | Show Build Version in Status Bar | GP / `UIStatusBarShowBuildVersion`=True | Real | OK |
| RTL | Force Right-to-Left Layout | GP / `NSForceRightToLeftWritingDirection`=True | Real | OK (kontradiksi dengan LTR, B30) |
| LTR | Force Left-to-Right Layout | GP / `NSForceLeftToRightWritingDirection`=True | Real | OK (kontradiksi dengan RTL, B30) |
| SBIconVisibility | Show Hidden Icons on Home Screen | GP / `SBIconVisibility`=True | plausible, UNVERIFIED | UNVERIFIED |
| iMessageDiagnosticsEnabled | iMessage Debugging | GP / `iMessageDiagnosticsEnabled`=True | plausible, UNVERIFIED | UNVERIFIED |
| IDSDiagnosticsEnabled | Continuity Debugging | GP / `IDSDiagnosticsEnabled`=True | plausible, UNVERIFIED | UNVERIFIED |
| VCDiagnosticsEnabled | FaceTime Debugging | GP / `VCDiagnosticsEnabled`=True | plausible, UNVERIFIED | UNVERIFIED |
| AccessoryDeveloperEnabled | Show Accessory Developer Settings | GP / `AccessoryDeveloperEnabled`=True | plausible, UNVERIFIED | UNVERIFIED |
| KeyFlick | Keyboard Key Flicks | GP / `GesturesEnabled`=True | Real (historis Nugget) | OK |
| DisableSecondsHand | Disable Clock Icon Seconds Hand | GP / `SBDisableClockIconSecondsHand`=True | plausible, UNVERIFIED | UNVERIFIED |
| DisableSearchingWebsites | Disable Spotlight Searching in Websites | GP / `SBSearchDisabledDomains`=True | **mencurigakan** — domain list sebagai bool | UNVERIFIED |
| ShowButtonHints | Show Hardware Button Hints in Screenshots | GP / `SBHardwareButtonHintDropletsAlwaysVisibleInSnapshots`=True | plausible, UNVERIFIED | UNVERIFIED |
| AppStoreDebug | App Store Debug Gesture | appStore / `debugGestureEnabled`=True | plausible, UNVERIFIED | UNVERIFIED |
| NotesDebugMode | Notes Debug Mode | notes / `DebugModeEnabled`=True | plausible, UNVERIFIED | UNVERIFIED |
| BKDigitizerVisualizeTouches | Show Touches With Debug Info | backboardd / `BKDigitizerVisualizeTouches`=True | Real | OK |
| BKHideAppleLogoOnLaunch | Hide Respring Icon | backboardd / `BKHideAppleLogoOnLaunch`=True | Real | OK |
| EnableWakeGestureHaptic | Vibrate on Raise-to-Wake | coreMotion / `EnableWakeGestureHaptic`=True | plausible, UNVERIFIED | UNVERIFIED |
| PlaySoundOnPaste | Play Sound on Paste | pasteboard / `PlaySoundOnPaste`=True | plausible, UNVERIFIED | UNVERIFIED |
| AnnounceAllPastes | Show Notifications for System Pastes | pasteboard / `AnnounceAllPastes`=True | plausible, UNVERIFIED | UNVERIFIED |

`FindMyFriends`: **tidak ada** di `src/` (grep repo-wide) — benar tidak di-port. Bukan bug.

## 3. Feature Flags — 13 tweak (`src/tweaks/registry.py:113-149`, UI Tweaks → Feature Flags)

Target: `/var/preferences/FeatureFlags/Global.plist`. Apply: `device_manager.py:1104-1107` →
ditulis di `:1244-1249`. **Tidak ada reset** (B10). Semua verbatim dari Nugget.

| Tweak ID | Display name | Kategori / flag | Key real? | Status |
|---|---|---|---|---|
| ClockAnim | Enable Lockscreen Clock Animation | SpringBoard / `SwiftUITimeAnimation` | Nugget-ported, UNVERIFIED | UNVERIFIED |
| Lockscreen | Enable Duplicate Lockscreen Button and Quickswitch | SpringBoard / `AutobahnQuickSwitchTransition`, `SlipSwitch`, `PosterEditorKashida` | Nugget-ported, UNVERIFIED | UNVERIFIED |
| PhotoUI | Enable Old Photo UI | Photos / `Lemonade` (inverted) | Real (well-known), UNVERIFIED di sini | UNVERIFIED |
| AI | Enable Apple Intelligence | SpringBoard / `Domino`, `SuperDomino` | Nugget-ported, UNVERIFIED | UNVERIFIED (beda dari AIFeatureFlags eligibility — tidak duplikat) |
| KioskMode | Enable Kiosk Mode | PreferencesFramework / `ForcedRetailKioskMode` | Nugget-ported, UNVERIFIED | UNVERIFIED |
| SolariumFFSwiftUI | Disable Solarium — SwiftUI | SwiftUI / `Solarium` (inverted) | Nugget-ported, UNVERIFIED | UNVERIFIED |
| SolariumFFSpringBoard | Disable Solarium — SpringBoard | SpringBoard / `SolariumElasticHUD` (inverted) | Nugget-ported, UNVERIFIED | UNVERIFIED |
| SolariumFFIconServices | Disable Solarium — Icon Services | IconServices / `EnhancedGlass`, `SolariumCornerRadius` (inverted) | Nugget-ported, UNVERIFIED | UNVERIFIED |
| SolariumFFDocumentCamera | Disable Liquid Glass in Documents Camera | DocumentCamera / `CaptureLiquidGlass` (inverted) | Nugget-ported, UNVERIFIED | UNVERIFIED |
| SolariumFFPhotos | Disable Liquid Glass in Photos | Photos / `SolariumGridMagicPocket` (inverted) | Nugget-ported, UNVERIFIED | UNVERIFIED |
| SolariumFFAppleMediaServices | Disable Liquid Glass in Apple Media Services | AppleMediaServices / `Solarium` (inverted) | Nugget-ported, UNVERIFIED | UNVERIFIED |
| SolariumFFSharing | Disable Liquid Glass in Share Sheet | Sharing / `ShareSheetSolarium` (inverted) | Nugget-ported, UNVERIFIED | UNVERIFIED |
| SolariumFFMail | Disable Liquid Glass in Mail | Mail / `SolariumSearch` (inverted) | Nugget-ported, UNVERIFIED | UNVERIFIED |

**BUG B6:** `FeatureFlagTweak.apply_tweak` (`src/tweaks/tweak_classes.py:399-418`) tidak punya
enabled-guard — menulis flag bahkan saat tweak mati (`{Enabled: False}`), dan Global.plist
ditulis di **setiap** apply walau user tidak menyentuh flag apapun.

---

## 4. Liquid Glass / Solarium — 98 tweak (`src/tweaks/registry.py:172-569`, UI Tweaks → Liquid Glass)

Target semua: `/var/Managed Preferences/mobile/.GlobalPreferences.plist`
(`FileLocation.globalPreferences`, ManagedPreferencesDomain).
Apply: `device_manager.py:1109` → ditulis di `:1242-1251`. **Tidak ada reset khusus**
(Page.LiquidGlass tidak ada di `_reset_tweaks`; hanya "Reset Internal Options" yang
ikut menghapusnya dengan men-null-kan seluruh file GP).

**Key reality: UNVERIFIED untuk 98/98.** Tidak ada provenansi di repo (tidak ada
dyld-strings/reverse-engineering notes; 41 di antaranya self-declare
"Type inferred; unverified on-device" di deskripsinya). Key yang tidak dikenal di
NSGlobalDomain diabaikan iOS — mode gagalnya "diam-diam tidak ngapa-ngapain".

### 4a. Solarium core (`registry.py:172-245`)

| Tweak ID | Display name | Key = value | Status |
|---|---|---|---|
| ForceSolariumFallback | Force Solarium Fallback | `SolariumForceFallback`=True | UNVERIFIED |
| IgnoreSolariumLinkedOnCheck | Ignore Solarium Linked-On Check | `com.apple.SwiftUI.IgnoreSolariumLinkedOnCheck`=True | UNVERIFIED |
| ForceSolariumIntelligence | Force Solarium Intelligence | `SolariumForceIntelligence`=True | UNVERIFIED |
| ForceEnhancedSpeculars | Force Enhanced Speculars | `SolariumForceEnhancedSpeculars`=True | UNVERIFIED |
| UISolariumFallback | UI Solarium Fallback | `UISolariumForceFallback`=True | UNVERIFIED |
| IgnoreSolariumHardwareCheck | Ignore Solarium Hardware Check | `com.apple.SwiftUI.IgnoreSolariumHardwareCheck`=True | UNVERIFIED |
| IgnoreSolariumOptOut | Ignore Solarium Opt-Out | `com.apple.SwiftUI.IgnoreSolariumOptOut`=True | UNVERIFIED |
| DisallowGlassButtons | Disallow Glass Buttons | `SBDisallowGlassButtons`=True | UNVERIFIED |
| DisallowGlassLockScreen | Disallow Glass Lock Screen | `SBDisallowGlassLockScreen`=True | UNVERIFIED |
| DisableSpecularEverywhere | Disable Specular Everywhere | `SBDisableSpecularEverywhere`=True | UNVERIFIED |
| NoLiquidClock | Disable Liquid Glass on LS Clock | `SBDisallowGlassTime`=True | UNVERIFIED |
| NoLiquidDock | Disable Liquid Glass on Dock | `SBDisableGlassDock`=True | UNVERIFIED |
| DisableSpecularMotion | Disable Specular Motion | `SBDisableSpecularEverywhereUsingLSSAssertion`=True | UNVERIFIED |
| DisableOuterRefraction | Disable Outer Refraction | `SolariumDisableOuterRefraction`=True | UNVERIFIED |
| DisableSolariumHDR | Disable Solarium HDR | `SolariumAllowHDR`=**False** (inverted) | UNVERIFIED |
| DisableWidgetSpecular | Disable Widget Specular | `SBDisableWidgetSpecular`=True | UNVERIFIED |
| DisableDockSpecular | Disable Dock Specular | `SBDisableDockSpecular`=True | UNVERIFIED |
| DisableFolderSpecular | Disable Folder Specular | `SBDisableFolderSpecular`=True | UNVERIFIED |
| ExcludeClearGlassShadows | Exclude All Clear Glass Shadows | `SBExcludeAllClearGlassShadows`=True | UNVERIFIED |
| ExcludeDockShadow | Exclude Dock Shadow | `SBExcludeDockShadow`=True | UNVERIFIED |
| ExcludeSearchShadow | Exclude Search Shadow | `SBExcludeSearchShadow`=True | UNVERIFIED |
| UseFlatIconsEverywhere | Use Flat Icons Everywhere | `SBUseFlatIconsEverywhere`=True | UNVERIFIED |

### 4b. SwiftUI/UIKit debug switches (`registry.py:251-296`)

| Tweak ID | Display name | Key | Status |
|---|---|---|---|
| GlassContainerLogging | Glass Container Logging | `com.apple.SwiftUI.GlassContainerLogging` | UNVERIFIED |
| FlexiGlassMacOS | Flexi Glass (macOS path) | `com.apple.SwiftUI.FlexiGlassMacOS` | UNVERIFIED — key macOS di halaman iOS, hampir pasti no-op |
| FlexiGlassMacOSPointer | Flexi Glass (macOS Pointer) | `com.apple.SwiftUI.FlexiGlassMacOSPointer` | UNVERIFIED — sama |
| InvisibilitySuppressesGlass | Invisible View Suppresses Glass | `com.apple.UIKit.InvisibilitySuppressesGlass` | UNVERIFIED |
| EnableGlassEffectBridgeLayers | Enable Glass Effect Bridge Layers | `EnableGlassEffectBridgeLayers` | UNVERIFIED |
| EnableGaussianGlassEffectBridgeLayers | Enable Gaussian Glass Bridge Layers | `EnableGaussianGlassEffectBridgeLayers` | UNVERIFIED |
| UnifiedSystemBackgroundColorsEnabled | Unified System Background Colors | `UnifiedSystemBackgroundColorsEnabled` | UNVERIFIED |
| UnaryGlassContainerEnabled | Unary Glass Container | `UnaryGlassContainerEnabled` | UNVERIFIED |
| EnableSolariumCompactChrome | Enable Solarium Compact Chrome | `EnableSolariumCompactChrome` | UNVERIFIED |
| DisableSolariumCompactChrome | Disable Solarium Compact Chrome | `DisableSolariumCompactChrome` | UNVERIFIED — pasangan kontradiktif, tanpa mutual exclusion |

### 4c. DesignLibrary/Calistoga recipes (`registry.py:303-394`)

| Tweak ID | Display name | Key = value | Status |
|---|---|---|---|
| SolariumIncreasedDiffusion | Increased Diffusion | `SolariumIncreasedDiffusion`=True | UNVERIFIED |
| SolariumUseDisplayAngle | Use Display Angle | `SolariumUseDisplayAngle`=True | UNVERIFIED |
| SolariumTintMask | Tint Mask | `SolariumTintMask`=True | UNVERIFIED |
| SolariumBackgroundFilter | Background Filter | `SolariumBackgroundFilter`=True | UNVERIFIED |
| SolariumHighlightWhite | Highlight White Point | `SolariumHighlightWhite`=1.0 (0–1, inferred) | UNVERIFIED |
| SolariumLiveTuning | Live Tuning | `SolariumLiveTuning`=True | UNVERIFIED |
| SolariumHierarchicalStyle | Solarium Hierarchical Style | `SolariumHierarchicalStyle`=1 (0–10, inferred) | UNVERIFIED |
| GlassHierarchicalStyle | Glass Hierarchical Style | `GlassHierarchicalStyle`=1 (0–10, inferred) | UNVERIFIED — duplikat dekat di atas |
| GlassVisualDebug | Glass Visual Debug | `GlassVisualDebug`=True | UNVERIFIED |
| GlassVisualWarnings | Glass Visual Warnings | `GlassVisualWarnings`=True | UNVERIFIED |
| BlurFillExperiment | Blur Fill Experiment | `blurFillExperiment`=True | UNVERIFIED — deskripsi: "exact behavior unknown" |
| AdaptiveGlassHysteresisDarkRange | Adaptive Glass Hysteresis (Dark Range) | `AdaptiveGlassHysteresisDarkRangeArray`="" TEXT | UNVERIFIED — deskripsi akui TEXT "may be ignored" |
| AdaptiveGlassHysteresisLightRange | Adaptive Glass Hysteresis (Light Range) | `AdaptiveGlassHysteresisLightRangeArray`="" TEXT | UNVERIFIED — sama |
| CalistogaLargeRefraction | Large Refraction (Calistoga) | `CalistogaLargeRefraction`=True | UNVERIFIED |
| CalistogaRegularClearer | Regular Tier Clearer (Calistoga) | `CalistogaRegularClearer`=True | UNVERIFIED |
| CalistogaBackdropMarginIncludesBlur | Backdrop Margin Includes Blur (Calistoga) | `CalistogaBackdropMarginIncludesBlur`=True | UNVERIFIED |
| CalistogaAllowLumaTracking | Allow Luma Tracking (Calistoga) | `CalistogaAllowLumaTracking`=True | UNVERIFIED |
| CalistogaSidebarAccentOpacity | Sidebar Accent Opacity (Calistoga) | `CalistogaSidebarAccentOpacity`=1.0 (0–1, inferred) | UNVERIFIED |
| CalistogaPerceptualBackdropScale | Perceptual Backdrop Scale (Calistoga) | `CalistogaPerceptualBackdropScale`=1.0 (0–2, inferred) | UNVERIFIED |
| CalistogaKeyboardGlass | Keyboard Glass (Calistoga) | `CalistogaKeyboardGlass`=True | UNVERIFIED |
| CalistogaCameraGlass | Camera Glass (Calistoga) | `CalistogaCameraGlass`=True | UNVERIFIED |

### 4d. UISolarium floating/stacked (`registry.py:401-569`, key = `UISolarium` + nama ID)

45 tweak (opacity/rotasi/translasi/border/debug untuk floating content, focus specular,
stacked image rendering). Semua: Apply `device_manager.py:1109`, tanpa revert khusus,
**UNVERIFIED** (mayoritas self-declare type inferred). Daftar lengkap ID:
`FloatingContentViewSpecularHighlightOpacity`, `FloatingContentViewUnfocusedBorderOpacity`,
`FloatingContentViewUnfocusedBorderWidth`, `FloatingContentViewEnableBackgroundFills`,
`FloatingContentViewDebugBackgroundFills`, `FloatingContentViewPunchoutShadow`,
`FloatingContentViewModifyTransformMode`, `FloatingContentViewOverrideRotationX/Y`,
`FloatingContentViewOverrideTranslationX/Y`, `FloatingContentViewModifyRotationStrength`,
`FloatingContentViewModifyTranslationStrength`, `FocusSpecularHighlightMaxSize`,
`FocusSpecularHighlightScaleFactor`, `FocusSpecularHighlightSensitivity`,
`FocusSpecularHighlightNormalizedPositionX/Y`, `NewStackedImageRenderingEnabled`,
`NewStackedImageFiltersEnabled`, `NewStackedImage3DTransformsEnabled`,
`NewStackedImage3DTransformedGlassLayer`, `NewStackedImageSpecularEnabled`,
`NewStackedImageSpecularOpacity`, `NewStackedImageRadiosityEnabled`,
`NewStackedImageForceAdjustMotionForSize`, `NewStackedImageForceDefaultScaleSizeIncrease`,
`NewStackedImageInnerParallaxScale`, `NewStackedImageAsymmetricScale`,
`NewStackedImageProgressiveScale`, `NewStackedImageAdditionalTranslation`,
`NewStackedImageFocusedAdditionalScaleAmount`, `StackedImageContainerDefaultMaxDepth`,
`StackedImageContainerDefaultRotationX/Y`, `StackedImageContainerDefaultTranslationX/Y`,
`StackedImageContainerModifyMaxDepthStrength`, `StackedImageContainerModifyRotationStrength`,
`StackedImageContainerModifyTranslationStrength`,
`StackedImageContainerModifyInnerParallaxScaleStrength`,
`StackedImageContainerModifyTransformMinWidth/MaxWidth/MinHeight/MaxHeight`.

---

## 5. MobileGestalt — 23 tweak (`src/tweaks/tweak_loader.py:17-44`, UI `src/gui/ios/mobilegestalt.py`)

Delivery: key ditulis ke `CacheExtra`/`CacheData` dari plist MobileGestalt milik user,
di-restore ke `/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/
Library/Caches/com.apple.MobileGestalt.plist` (`FileLocation.mga`,
`src/tweaks/basic_plist_locations.py:34`).
Apply: tombol halaman `device_manager.py:487-498` + main apply K3 `:1171-1181`, `:1227-1240`.
Gate versi: `src/devicemanagement/constants.py:64-81` — allowlist 106 build, iOS 16.0–26.2 beta 1
(`23C5027f`), terkunci dari 26.2 beta 2 (`23C5035e`).

| Tweak ID | Display name | Payload (MG key = value) | Key real? | Status |
|---|---|---|---|---|
| DynamicIsland | Dynamic Island (dropdown) | `oPeik/9e8lQWMszEjbPzng`→`ArtworkDeviceSubType` ∈ [2436,2556,2796,2622,2868,2736]; auto `YlEtTtHlNesRBMal1CqRaA`=1 | Ya | **BUG** — nilai `2736` tidak terjangkau (6 label vs 6 value, index-1) |
| SupportsDynamicIsland | Supports Dynamic Island | `YlEtTtHlNesRBMal1CqRaA`=1 | Ya | OK / UNVERIFIED |
| ModelName | Custom Model Name | `ArtworkDeviceProductDescription`=<teks user> | Ya | OK / UNVERIFIED |
| BootChime | Boot Chime | `QHxt+hGLaBPbQJbXiUJX3w`=1 | Ya | OK / UNVERIFIED |
| EnableLGLPM | Enable Low Power Mode (LGLPM) | `SAGvsp6O6kAQ4fEfDJpC4Q`=1 | Ya | **BUG** — key sama dengan DisableLGLPM, tanpa mutual exclusion |
| DisableLGLPM | Disable Low Power Mode (LGLPM) | `SAGvsp6O6kAQ4fEfDJpC4Q`=0 | Ya | **BUG** — sama di atas |
| ChargeLimit | Charge Limit | `37NVydb//GP/GrhuTN+exg`=1 | Ya | OK / UNVERIFIED |
| CollisionSOS | Collision SOS | `HCzWusHQwZDea6nNhaKndw`=1 | Ya | OK / UNVERIFIED |
| TapToWake | Tap to Wake | `yZf3GTRMGTuwSV/lD7Cagw`=1 | Ya | OK / UNVERIFIED |
| CameraButton | Camera Button (iPhone 16 Settings) | `CwvKxM2cEogD3p+HYgaW0Q`=1, `oOV1jhJbdV3AddkcCg0AEA`=1 | Ya | OK / UNVERIFIED |
| Parallax | Disable Parallax | `UIParallaxCapability`=0 | Ya | OK / UNVERIFIED |
| StageManager | Stage Manager | `qeaj75wk3HF4DwQ8qbIi7g`=1 | Ya | OK / UNVERIFIED |
| iPadOS | Enable iPadOS | 5 keys =1 | Ya | OK / UNVERIFIED |
| iPadOSCacheData | (mengikuti iPadOS) | patch biner `CacheData` (`tweak_classes.py:315-413`) | n/a | UNVERIFIED — raise jika pattern tidak ketemu, abort seluruh apply |
| iPadApps | iPad Apps | `9MZ5AdH43csAUajl/dU+IQ`=[1,2] | Ya | OK / UNVERIFIED |
| Shutter | Shutter Sound | `h63QSdBCiT/z0WU6rdQv6Q`="US", `zHeENZu+wbg7PUprwNwBWg`="LL/A" | Ya | OK / UNVERIFIED |
| Pencil | Apple Pencil | `yhHcB0iH0d1XzPO/CFd3ow`=1 | Ya | OK / UNVERIFIED |
| ActionButton | Action Button | `cT44WE1EohiwRzhsZ8xEsw`=1 | Ya | OK / UNVERIFIED |
| InternalStorage | Show Internal Storage | `LBJfwOEzExRxzlAnSuI7eg`=1 | Ya | OK / UNVERIFIED |
| InternalInstall | Internal Install | `EqrsVvjcYDdxHBiQmGhAWw`=1 | Ya | OK / UNVERIFIED |
| SRD | SRD | `XYlJKKkj2hztRP1NWWnhlw`=1 | Ya | OK / UNVERIFIED |
| AOD | Always On Display | `2OOJf1VhaM7NxfRok3HbWQ`=1, `j8/Omm6s1lsmTDFsXjsBfA`=1 | Ya | OK / UNVERIFIED |
| AODVibrancy | AOD Vibrancy | `ykpu7qyhqFweVMKtxNylWA`=1 | Ya | OK / UNVERIFIED |

**Revert: tidak ada** untuk semua 23 (satu-satunya jalan: matikan switch + re-apply).
**BUG tambahan:** tweak gestalt yang terkunci (iOS 27/26.2b2+) tidak di-skip — melempar
`NuggetException` di `device_manager.py:1224-1227` dan menggagalkan **seluruh** apply.

---

## 6. Eligibility — 9 tweak (`src/tweaks/eligibility_tweak.py`, UI `src/gui/ios/eligibility.py`)

Semua payload verbatim dari upstream Nugget (terverifikasi char-identical kecuali import).

| Tweak ID | Display name | Payload | Key real? | Apply | Status |
|---|---|---|---|---|---|
| EUEnabler | Enable EU Enabler (+ Method 1/2, Region Code) | `/var/db/os_eligibility/eligibility.plist` (DatabaseDomain), region replace | Real (upstream) | `device_manager.py:1135-1142` → `:1187-1201` | **GIMMICK parsial** — dropdown Method 1/2 no-op (beda hanya di Config.plist yang tidak pernah terkirim); **BUG** `eval()` + replace "US" global merusak key `OS_ELIGIBILITY_DOMAIN_PHOSPHORUS` (`eligibility_tweak.py:17-27`) |
| AIEligibility | (ikut "Enable Eligibility File") | `/var/db/eligibilityd/eligibility.plist` — `OS_ELIGIBILITY_DOMAIN_CALCIUM/GREYMATTER` | Real (upstream) | `:1143-1146` → `:1202-1206` | UNVERIFIED |
| AIFeatureFlags | (ikut "Enable Eligibility File") | `/var/preferences/FeatureFlags/Global.plist` — Siri/`sae_override`, `assistant_engine_override` | Real (upstream) | `:1104-1108` | **BUG B6** (no enabled guard) |
| AIFeatureFlagsUI | (ikut "Enable Eligibility File") | sama — SiriUI/`sae` | Real (upstream) | sama | **BUG B6** |
| AIGestalt | Enable Apple Intelligence (for Unsupported Devices) | `CacheExtra["A62OafQ85EJAiiqKn4agtg"]`=1 (plist MG milik user) | Real (upstream) | K3 `:1171-1185` → `:1213-1231` | UNVERIFIED |
| SpoofModel | Spoofed Model (dropdown) | `CacheExtra["h9jDsbgj7xIVeIQ8S3/X3Q"]` | Real (upstream) | K3 | OK / UNVERIFIED (off-by-one upstream sudah di-fix di sini) |
| SpoofHardware | Spoof Hardware Model | `CacheExtra["oYicEKzVTz4/CxxE05pEgQ"]` | Real (upstream) | K3 | OK / UNVERIFIED |
| SpoofCPU | Spoof CPU Model | `CacheExtra["5pYKlGnYYBzGvAlIU8RjEQ"]` | Real (upstream) | K3 | OK / UNVERIFIED |
| CreateBRFolders | Create Eligibility/FEature Flags Folder | file kosong `FeatureFlags/Placeholder`, `eligibilityd/Placeholder` | n/a | `:1148-1153` | OK (minor: sampah tidak dibersihkan) |

Catatan: Config.plist di `/var/MobileAsset/…` **tidak bisa terkirim** (butuh BookRestore yang
tidak ada di fork ini) — di-skip dengan warning eksplisit (`device_manager.py:1193-1201`),
bukan diam-diam. Satu-satunya payload yang butuh akses di luar sparse restore.

## 7. RdarFix — 1 tweak (`src/tweaks/tweak_classes.py:200-234`, UI MobileGestalt page)

| Aspek | Detail |
|---|---|
| Display name | dinamis: "RDAR Fix"/"Revert RDAR fix"/"Dynamic Island Status Bar Fix"/… |
| Payload | `/var/Managed Preferences/mobile/com.apple.iokit.IOMobileGraphicsFamily.plist` → `canvas_height`/`canvas_width` per mode |
| Apply | `device_manager.py:1109-1111` (cabang BasicPlistTweak) — **tapi tidak** lewat tombol Apply halaman MobileGestalt (`:487-498` hanya iterasi tipe MobileGestalt*) |
| Revert | **BUG B5 (HIGH):** revert **me-replace** seluruh plist jadi `{"nugget": 0}` (`tweak_classes.py:205`) — resolusi asli tidak pernah disimpan, tidak di-restore |

## 8. Risky — 2 tweak (`src/gui/ios/risky.py`, `src/tweaks/tweak_loader.py:139-157`)

| Tweak ID | Display name | Payload | Apply | Status |
|---|---|---|---|---|
| DisableOTAFile | Disable OTA Updates (file) | `/var/Managed Preferences/mobile/com.apple.MobileAsset.plist` — 7 keys (5× `MobileAssetServerURL-*` → tvOS16DeveloperSeed, `…AllowOSVersionChange=False`, `…AllowSameVersionFullReplacement=False`, `MobileAssetAssetAudience`=…) | `:1109-1111` | **BUG:** tidak ada revert — sekali aktif, blokir OTA menetap |
| CustomResolution | Set a Custom Device Resolution | **File yang sama dengan RdarFix** — `canvas_height`/`canvas_width` dari input user | `:1109-1111` | **BUG:** tidak ada revert + tabrakan replace dengan RdarFix (last-write-wins diam-diam) |

## 9. Daemons — ~14 (`src/tweaks/daemons_tweak.py`, UI `src/gui/ios/daemons.py`)

Enum: thermalmonitord, OTA (4 service), UsageTrackingAgent, GameCenter, ScreenTime, CrashReports,
Diagnostics, ATWAKEUP, Tips, VPN, Location, ChineseLAN + master switch + ClearScreenTimeAgentPlist.
Apply: `device_manager.py:1112` (NullifyFileTweak) untuk ScreenTimeAgent; daemon lain via
`disabled.plist`. **BUG B12:** apply me-replace seluruh `/var/db/com.apple.xpc.launchd/disabled.plist`
(fork seed `{}`; upstream seed 6 default). **BUG:** HotLoad daemon-forcing tidak pernah
`set_enabled(True)` (`device_manager.py:743`) — safety rule diam-diam tidak jalan.
`DANGEROUS_DAEMONS` kosong (security theater, temuan lama).

---

## 10. Status Bar — 31 kontrol (`src/gui/ios/statusbar.py`, `src/tweaks/status_bar/`)

Mekanisme: struct biner `StatusBarOverrideData` (`status_setter.py:186-224`);
iOS 27: `StatusBarOverrides.archive` NSKeyedArchiver (`statusbar_archive.py:80-141`).
Apply: `device_manager.py:1156`. Revert: `:1388-1417` (ter-cover, termasuk reset archive iOS 27).

| Kontrol (file:line) | Payload (field struct) | Status |
|---|---|---|
| Time text (`:61`) | `overrideTimeString`=1, `timeString` | **BUG** stale closure `:332` |
| Date text (`:66`) | `overrideDateString`, `dateString` | **BUG** stale closure |
| Breadcrumb (`:71`) | `overrideBreadcrumb`, `breadcrumbTitle` | **BUG** stale closure |
| Battery detail (`:76`) | `overrideBatteryDetailString`, `batteryDetailString` | **BUG** stale closure |
| Carrier (`:85`) | `overrideServiceString`, `serviceString` (+iOS27 archive `STStatusBarDataCellularEntry.string`) | **BUG** stale closure |
| Service badge (`:90`) | `overridePrimaryServiceBadgeString` | **BUG** stale closure |
| Secondary carrier (`:95`) | archive `secondaryCellularEntry.string` | **BUG** stale closure |
| Secondary badge (`:100`) | classic only | **BUG** stale closure |
| GSM bars (`:114`) | `overrideGSMSignalStrengthBars` 0–5 | **BUG** stale closure `:383` (+ paksa ikon cellular visible) |
| Secondary GSM bars (`:119`) | `overrideSecondaryGSMSignalStrengthBars` | **BUG** stale closure |
| Wi-Fi bars (`:124`) | `overrideWifiSignalStrengthBars` | **BUG** stale closure |
| Battery capacity (`:130`) | `overrideBatteryCapacity` 0–100 | **BUG** stale closure |
| Data network type (`:135`) | `overrideDataNetworkType` 0–30 | **BUG** stale closure |
| Secondary network type (`:140`) | `overrideSecondaryDataNetworkType` | **BUG** stale closure |
| Raw cellular (`:160`) | `overrideDisplayRawGSMSignal` | OK |
| Raw Wi-Fi (`:165`) | `overrideDisplayRawWifiSignal` | OK |
| 14× Disable icon (`:173-187`) | `overrideItemIsEnabled[…]`=1, `itemIsEnabled`=0 | OK |
| Silly Mode (`:199`) | semua 46 item visible (transform app-side, tidak mutasi struct) | OK |
| Master switch (`:52`) | gate `Tweak.enabled` | OK |

**BUG B9 (MEDIUM):** stale closure — nilai edit user hilang saat toggle off→on
(`statusbar.py:332` teks, `:383` angka). Semua field struct REAL (port Nugget).

## 11. Icon Themes — 3 opsi (`src/gui/ios/icon_themes.py`, `src/tweaks/icon_themes/`)

| Opsi | Payload | Apply | Status |
|---|---|---|---|
| Add Icon Theme (bundle ID + label + gambar) | HomeDomain `Library/WebClips/Cowabunga_<bundleID>,<displayName>.webclip/` — Info.plist (15 key WebClip) + `icon.png` (`icon_themes_tweak.py:259-290`) | `device_manager.py:1128-1133` | OK / UNVERIFIED (key WebClip presumed real, mirror Cowabunga) |
| Download Icon Packs | sama (dari zip unduhan) | sama | OK — zip-slip **sudah di-fix** (`:170` → `_safe_extractall` `:179-189`) |
| Delete (per-theme) | hapus dari list lokal saja | n/a | OK (lokal) |

**BUG B18 (MEDIUM):** thumbnail tidak pernah render — kondisi terbalik
(`icon_themes.py:184-196`), semua kartu tampil "?".
**Revert: tidak ada** di device (reset in-app hanya lokal; user hapus WebClip manual di iPhone).

## 12. PosterBoard — 9 opsi (`src/gui/ios/posterboard.py`, `src/tweaks/posterboard/`)

| Opsi | Payload | Apply | Status |
|---|---|---|---|
| Import .tendies | AppDomain `com.apple.PosterBoard`: `…/PRBPosterExtensionDataStore/…/configurations/<uuid>/…` + sqlite `PBFPosterExtensionDataStoreSQLiteDatabase.sqlite3` dimodifikasi | `device_manager.py:1116-1126` | OK / UNVERIFIED — **BUG B2:** zip-slip di `tendie_file.py:52-55` |
| Import .batter templates | domain dari `config.json` template (bisa absolute `/var/…`) | sama | OK / UNVERIFIED — **BUG B3:** zip-slip `template_file.py:151-152`; **BUG:** traversal ekstraksi resource `:128-137`, traversal path restore `templates_tweak.py:71`, **penghapusan file host arbitrer** via RemoveOption (`remove_option.py:45-57`) |
| Video tab (6 kontrol) | bundle CAML / live-photo descriptor | via `apply_tweak` `:348-349` | OK / UNVERIFIED |
| Reset (Collections/Suggested/Gallery/Full) | `b""` di descriptors/GalleryCache/Extensions/Backups + sqlite kosong skema + `PBF_*` keys | via `apply_tweak` | OK / UNVERIFIED — satu-satunya undo device-side |
| Disable PosterBoard | tidak ada (early return) | self-gated | OK |
| Force refresh (Settings) | `unprotectedUserDefaults.plist` dengan key `PBF_*` | `device_manager.py:1123` | OK |

Skema sqlite **REAL** (divalidasi lawan DB device asli, `pb_config_manager.py:30-66`).
Bug sqlite_sequence lama **SUDAH FIX**.

---

## Daftar bug konsolidasi (prioritas, dedup antar auditor)

### HIGH
1. **B1 — iOS 27: apply me-REPLACE `.GlobalPreferences.plist` live user dengan dict tweak-only.**
   `src/devicemanagement/device_manager.py:1267-1278`. Tidak merge, tidak ada base plist di
   repo. Menghapus bahasa/region/keyboard user begitu ≥1 GP tweak (98 Solarium + 11 Internal)
   aktif di iOS 27. Guard comment mendeskripsikan risiko tapi tidak mencegahnya. Phase 0
   sengaja skip file ini di protective backup (`src/restore/protective.py:299`) → tidak bisa
   di-restore. (Dikonfirmasi 2 auditor independen.)
2. **B2 — Zip-slip CWE-22 di import `.tendies`.** `src/tweaks/posterboard/tendie_file.py:52-55`
   (`extractall` tanpa sanitasi, file dari user = untrusted).
3. **B3 — Zip-slip CWE-22 di import template `.batter`.** `src/tweaks/posterboard/template_file.py:151-152`.
4. **B4 — Template RemoveOption bisa hapus file host arbitrer.** `src/tweaks/posterboard/template_options/remove_option.py:45-57`
   (`../` dari `config.json` template → `os.remove`/`rmtree`). Varian tulis: `replace_option.py:106`,
   `set_option.py:332`, `picker_option.py:114,123-124`; traversal ekstraksi `template_file.py:128-137`;
   traversal path restore device-side `templates_tweak.py:71`.
5. **B5 — Revert RdarFix menghancurkan plist resolusi.** `src/tweaks/tweak_classes.py:205` —
   revert me-replace seluruh `/var/Managed Preferences/mobile/com.apple.iokit.IOMobileGraphicsFamily.plist`
   jadi `{"nugget": 0}`; resolusi asli tidak pernah disimpan. Tabrakan dengan CustomResolution
   (file sama, last-write-wins diam-diam).

### MEDIUM / MAJOR
6. **B6 — `FeatureFlagTweak` tanpa enabled-guard.** `src/tweaks/tweak_classes.py:399-418` —
   menulis flag walau tweak mati; Global.plist ditulis di setiap apply.
7. **B7 — `_build_apply_summary` mengabaikan Eligibility/Risky/MobileGestalt/ClearScreenTimeAgentPlist.**
   `src/gui/main_window_mixins.py:644`; gate "Nothing to apply" (`:807-811`) **memblokir Apply**
   padahal `_apply_tweak_pass` menangani semuanya.
8. **B8 — `eval()` + replace "US" global di eligibility.** `src/tweaks/eligibility_tweak.py:17-27` —
   merusak key `OS_ELIGIBILITY_DOMAIN_PHOSPHORUS` untuk region non-US; input UI masuk ke `eval`.
9. **B9 — StatusBar stale closure.** `src/gui/ios/statusbar.py:332, 383` — nilai edit hilang saat
   toggle off→on (temuan lama, masih ada).
10. **B10 — Tidak ada reset untuk Liquid Glass / Feature Flags / Risky / Eligibility / MobileGestalt.**
    `_reset_tweaks` (`device_manager.py:1387-1478`) hanya StatusBar/Springboard/Daemons/InternalOptions;
    `get_resettable_pages` (`src/utils/pages.py:48-56`) tidak menawarkan sisanya.
11. **B11 — `WatchOSCompatibility` `ipad_only=True`.** `src/tweaks/registry.py:578-580` —
    disembunyikan di iPhone, satu-satunya device yang pairing Apple Watch. (Upstream tidak punya gate ini.)
12. **B12 — HotLoad daemon-forcing mati diam-diam.** `device_manager.py:743` tidak pernah
    `set_enabled(True)`; `apply_tweak` early-return saat disabled (`tweak_classes.py:163-166`).
13. **B13 — Hidden-feature skip dead code.** `device_manager.py:1098` bandingkan `TweakID` vs
    string nama (`hotload.py:211-217`) — selalu False.
14. **B14 — Gestalt terkunci meracuni seluruh apply.** `device_manager.py:1224-1227` melempar
    `NuggetException` (bukan skip) saat tweak gestalt aktif di build terkunci.
15. **B15 — Opsi DI `2736` tidak terjangkau.** `src/gui/ios/mobilegestalt.py:36-43` (6 label vs 6 value).
16. **B16 — Reset Internal Options men-null-kan GP HomeDomain bahkan di iOS 26** (`device_manager.py:1443`)
    padahal apply iOS 26 tidak pernah menulisnya — reset lebih destruktif dari apply.
17. **B17 — EUEnabler Method 1/2 = GIMMICK.** Satu-satunya beda adalah Config.plist yang tidak
    pernah terkirim (`eligibility_tweak.py:83-101` vs `device_manager.py:1193-1201`).
18. **B18 — Thumbnail icon theme tidak pernah render.** `src/gui/ios/icon_themes.py:184-196`
    (kondisi terbalik).

### LOW / INFO
- B19 Enable/Disable LGLPM key sama tanpa mutual exclusion (`mobilegestalt.py:281-282`).
- B20 RdarFix tidak dihormati tombol Apply halaman MobileGestalt (`device_manager.py:487-498`).
- B21 SpringBoard reset tidak cover footnote/airdrop/nanoregistry (`:1421-1422`).
- B22 Daemons apply replace `disabled.plist`, seed `{}` vs 6 default upstream.
- B23 Truncation tendie diam-diam max 5 (`device_manager.py:615`).
- B24 PB DB churn untuk template non-PB (`device_manager.py:617-620`).
- B25 `packaging` di-import tapi tidak di requirements (3 file).
- B26 Pasangan kontradiktif RTL/LTR, Enable/DisableSolariumCompactChrome tanpa mutual exclusion.
- B27 `FlexiGlassMacOS*` — key macOS di halaman iOS, hampir pasti no-op.
- B28 Dead IDs: `MetalForceHudEnabled`, `DisableSolarium` (hotload list, tanpa spec).
- B29 GSM bars paksa ikon cellular visible (`status_bar_tweak.py:119-125`).
- B30 iOS 27 master-ON tanpa carrier override men-stage reset archive (`status_bar_tweak.py:29-43`).
- B31 Placeholder litter CreateBRFolders; B32 `InvalidRegionCodeException` tidak pernah di-raise.
- B33 Page-vs-apply gate gestalt tidak konsisten (build-only vs build-OR-version).

### Yang SUDAH FIX (terverifikasi dalam audit ini)
- Zip-slip icon_themes (`icon_themes_tweak.py:170`).
- sqlite_sequence PosterBoard (`pb_config_manager.py`).
- K3 wiring MobileGestalt/Eligibility ke Apply (`device_manager.py:1171-1181`).
- Off-by-one spoof iPad (`eligibility.py:192-216`).
- tr() plural-form backup (`backup.py`, commit 0eb39d0).

---

## Matriks revert/reset

| Keluarga | Reset via Settings | Undo manual (toggle-off + re-apply) |
|---|---|---|
| SpringBoard | Ya (parsial — footnote/airdrop/nano tidak) | Ya |
| Internal Options | Ya (**nuklir**: null-kan seluruh GP) | Ya |
| Status Bar | Ya | Ya |
| Daemons | Ya | Ya |
| Feature Flags | **Tidak** | Ya (implisit, karena apply selalu tulis stock) |
| Liquid Glass | **Tidak** (hanya via Reset Internal Options = nuke GP) | Ya |
| MobileGestalt | **Tidak** | Ya |
| Eligibility | **Tidak** | Ya (kecuali file yang ditulis; EU/AI persist) |
| RdarFix | **Tidak** | **Tidak** (revert merusak — B5) |
| Risky | **Tidak** | **Tidak** (OTA/resolusi menetap) |
| Icon Themes | Lokal saja | **Tidak** (WebClip menetap di device) |
| PosterBoard | Via Reset PosterBoard di halamannya | Ya (reset modes) |

## Catatan jujur

1. **Efek di device tidak bisa diverifikasi tanpa iPhone** — semua status OK di atas artinya
   "kode benar & ter-wire", bukan "terbukti bekerja di iOS". Klaim "bekerja" butuh device test.
2. **98 key Solarium tanpa provenansi** — kemungkinan besar sebagian dekoratif (diabaikan iOS).
   Jangan presentasikan sebagai "98 tweak Liquid Glass yang bekerja".
3. **iOS 26.2 beta 2+ menutup jalur MobileGestalt** — 23 tweak gestalt mati by design di build baru.
4. Upstream Nugget issue #1073: Apple Intelligence eligibility mungkin sudah tidak mempan di
   iOS/macOS 26.5+ (validasi Apple-side berubah).
5. Anisette bergantung 1 host pihak ketiga; error MBErrorDomain selalu didiagnosa "device kekunci".

*— Laporan dihasilkan 2026-09-30 oleh 5 auditor read-only, disintesis koordinator. UI tidak diubah.*
