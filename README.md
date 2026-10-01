<p align="center">
  <img src="assets/workslop-icon.jpg" width="180" alt="WorkSlop Desktop icon">
</p>

# WorkSlop Desktop

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![Version](https://img.shields.io/badge/version-v3.4%20stable-green.svg)]()

**Owner & Developer: [@Adnan.120hz](https://github.com/adnan120hz)**

Customize your iPhone without jailbreak — system tweaks, Liquid Glass controls,
MobileGestalt flags, feature flags, eligibility, wallpapers, icon & passcode
themes, app-data browsing and full backups in one app, with the same Sky look
on Windows, Linux and macOS.

WorkSlop Desktop is a fresh fork of
[GoldenNugget](https://github.com/GoldenNugget-Team/GoldenNugget) with a
redesigned Sky interface, **extra features and wider iOS support**: tweak
modules ported from [Nugget](https://github.com/leminlimez/Nugget)
(MobileGestalt, eligibility, RDAR fix, risky tweaks), a Liquid Glass section
for iOS 26, iMazing-style read-only App Data browsing, real full backups,
Indonesian translations, and per-iOS support gating — unsupported tweaks are
shown locked with the reason, never hidden. It also has a safer backup
system: when the protective device backup reaches 100%, the file manager
opens with the finished backup selected so you can copy it somewhere safe
before the apply continues.

> [!WARNING]
> Always back up your data before applying tweaks. WorkSlop Desktop tries to
> protect your data, but unexpected problems can still happen — we are not
> responsible for any data loss or bootloops. Use at your own risk.
> **Effectiveness on real iPhones is still unverified** — please report what
> you find in [Issues](https://github.com/adnan120hz/desk/issues).

## Features

### Home
- Device overview: model, iOS version, build, UDID, connection status.
- Quick-action cards: **Tweaks**, **Liquid Glass**, **App Data**,
  **MobileGestalt**, **PosterBoard**, **Daemons**, **Status Bar**,
  **Custom Icon**, **Passcode Theme** — each jumps straight to its page.

### Tweaks
The main customization page, organized in sections. Every control shows its
support range; **anything your connected iOS does not support stays visible
but locked** (disabled, with the reason in a tooltip) instead of being hidden
or silently toggleable.

- **Liquid Glass** — ~25 toggles for iOS 26's glass renderer: the master
  switch **"Disable Liquid Glass (Recommended for iOS 26.6.1)"**, Force
  Solarium Fallback, per-surface disables (Lock Screen clock, Dock, buttons,
  widgets, folders), specular/reflection controls and flat-icon options.
  iOS 26.0 and newer only.
- **SpringBoard** — SpringBoard system options (ported from GoldenNugget).
- **Feature Flags** — SpringBoard / Photos / SwiftUI / IconServices / Mail /
  Sharing / DocumentCamera / AppleMediaServices feature flags. Writes to
  `/var/preferences/FeatureFlags/Global.plist` via the exploit-based route,
  which community tooling reports working **up to iOS 26.1** — the switches
  lock automatically above that. On iOS 27 they are shown as experimental:
  research found no confirmed working delivery channel there yet.
- **Internal Options** — internal/debug-style options including KeyFlick.
- **Eligibility** — Nugget's eligibility module ported verbatim: EU Enabler
  with region code, Apple Intelligence for unsupported devices, eligibility
  file + Siri feature flags, model/hardware/CPU spoofing with the original
  model list. MobileGestalt-family controls (AIGestalt, spoofing) lock
  outside the supported range. Honest limit: the EU Enabler's
  `/var/MobileAsset/...` Config.plist cannot be delivered by this fork
  (Nugget sends it via BookRestore, which this fork does not have), so that
  file is skipped with a warning while the `/var/db/...` files go through
  the normal sparse restore.
- **Risky** — Disable OTA updates file and custom resolution (ported from
  Nugget's risky module).

### MobileGestalt
- 23 device feature-flag tweaks ported **verbatim** from
  [Nugget](https://github.com/leminlimez/Nugget) by leminlimez, plus the
  RDAR fix switch and Dynamic Island type control.
- **Open on iOS 16.0 → iOS 26.2 beta 1**, locked on 26.2 beta 2 and newer —
  the menu stays visible with the reason, per Apple's closure of the restore
  route on newer builds.

### Liquid Glass (Home menu)
- One-tap shortcut from Home straight to the Liquid Glass tweak section.

### PosterBoard / Wallpaper
- Animated wallpapers, PosterBoard descriptors and templates, including
  video wallpapers (ffmpeg + OpenCV).

### Daemons
- Disable system daemons. No iOS build gating — available on all supported
  builds.

### Status Bar
- Status bar customization. **Locked on any iOS 27 build**, open on
  iOS 26 and below.

### App Data — read-only
- **iMazing-style per-app backup browsing**: for apps that deny direct
  container access, the app takes a targeted backup of only
  `AppDomain-<bundle_id>` and lets you browse and download files from it.
- Apps that allow direct access can still be browsed over the normal
  channel. Honest limits (same as iMazing): App Store apps without File
  Sharing simply do not expose their container — an Apple restriction,
  and the UI shows which access level each app grants.
- **No write support**: this page never modifies app data.

### Themes
- **Custom Icon** — themed app icons & labels.
- **Passcode Theme** — custom keypad themes (`.passthm` files).

### Backup
- **Full Backup** — real full iTunes/Finder-style backup (`mb.backup`
  without filters) to a folder you choose, in the standard `<folder>/<UDID>/`
  layout, with real 0–100% progress from mobilebackup2.
- **Protective backup** — automatic device backup before tweaks are applied
  on the iOS 27 flow; the file manager opens with the finished backup
  highlighted at 100% so you can copy it somewhere safe.
- **Restore Backup** — restore a previously taken backup.

### Settings
- Appearance: Sky theme, accent color picker.
- Language: English / Indonesian (in-app translations, `.qm`).
- Safety options and update checker (checks **adnan120hz/desk** releases,
  not upstream).
- **About → Credits**: full contributor list (upstream developers,
  PosterRestore team, translators, library authors).

### How Apply works per iOS version
| iOS | Apply method |
|---|---|
| 26.x and below | Partial sparse restore, **no wipe** (GoldenNugget's built-in method, unchanged). |
| 27.x | Classic protective flow: backup → apply tweaks → **reboot** → wipe → reconnect → restore backup. The device reboots on Apply, like the original GoldenNugget. |

> Standalone backup actions (**Full Backup**) do **not** reboot the device —
> they just export the backup file to the folder you choose. Only **Restore
> Backup** and **Apply** reboot the device.

### Version support

WorkSlop Desktop only supports the **49 iOS builds** listed below.
Anything else is rejected, even if its version number looks newer.

| iOS | Builds |
|---|---|
| 16.0 – 16.0.3 | 20A362, 20A371, 20A380, 20A392 |
| 16.1 – 16.1.2 | 20B82, 20B101, 20B110 |
| 16.2 | 20C65 |
| 16.3 – 16.3.1 | 20D47, 20D67 |
| 16.4 – 16.4.1 | 20E247, 20E252 |
| 16.5 – 16.5.1 | 20F66, 20F75 |
| 16.6 – 16.6.1 | 20G75, 20G81 |
| 16.7.x | 20H19, 20H24, 20H30, 20H57, 20H68, 20H115, 20H219, 20H315, 20H332, 20H350 |
| 18.0 | 22A3354 |
| 18.1 betas | 22B5007p, 22B5023e, 22B5034e, 22B5045g |
| 26.0 / 26.0.1 | 23A341, 23A342 |
| 26.1 | 23B85 |
| 26.2 betas | 23C5027f (beta 1), 23C5035e, 23C5042d |
| 26.2 | 23C89 |
| 26.3 | 23D57 |
| 26.4 | 23E215 |
| 26.5 | 23F72 |
| 27.0 betas / 27.0 | 24A5264w, 24A5279h, 24A5288g, 24A5299d, 24A5309f, 24A5315a, 24A5320a, 24A335 |

Feature gating per build:

| Feature | Rule |
|---|---|
| Tweaks (Apply) | All 49 builds. iOS 26.x and below: partial sparse restore (no wipe). iOS 27: protective flow (backup → tweak → **reboot** → wipe → reconnect → restore). |
| Feature Flags | Fully supported on **iOS 26.1 and lower**; locked above (the exploit-based `Global.plist` route stops working past 26.1 per community tooling). Experimental on iOS 27 — may silently do nothing. |
| MobileGestalt | **Open on iOS 16.0 → iOS 26.2 beta 1** (builds `20A362`–`23C5027f`). Locked on 26.2 beta 2 and newer — menu stays visible with the reason. |
| Status Bar | **Locked on any iOS 27 build** (`24A…`). Open on iOS 26 and below. |
| Daemons | No build gating — available on all 49 builds. |
| Liquid Glass | iOS 26.0 and newer only (hidden on older versions); no upper lock. |

## Requirements

<details>
<summary>Windows</summary>

- Either the [Apple Devices (from Microsoft Store)](https://apps.microsoft.com/detail/9np83lwlpz9k) app or [iTunes (from Apple's website)](https://www.apple.com/itunes/)
</details>

<details>
<summary>Linux</summary>

- [usbmuxd](https://github.com/libimobiledevice/usbmuxd)
- [libimobiledevice](https://github.com/libimobiledevice/libimobiledevice)
</details>

<details>
<summary>Running from Python</summary>

- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3)
- [PySide6](https://doc.qt.io/qtforpython-6/) (PySide6-Essentials on non-Linux, selected automatically)
- [ffmpeg-python](https://pypi.org/project/ffmpeg-python/) (video wallpapers)
- [opencv-python](https://pypi.org/project/opencv-python/) (video wallpapers)
- Python 3.10 or newer
</details>

> All pinned dependencies are in `requirements.txt` (including PyInstaller for building).

## Running the Python program

> [!NOTE]
> It is highly recommended to use a virtual environment:
> ```sh
> python3 -m venv .env   # only needed once
> ```
macOS/Linux:
```sh
source .env/bin/activate
```
Windows:
```sh
.env\Scripts\activate.bat
```
Install packages and run:
```sh
pip install -r requirements.txt   # only needed once
python main_app.py
```
> Depending on your system configuration, use either `python`/`pip` or `python3`/`pip3`.

## Building

Prebuilt binaries for Windows, macOS and Linux are produced by the
[build workflow](.github/workflows/build.yml) on every push to `main`
(6 artifacts: Windows, macOS Apple Silicon, macOS Intel, macOS Intel Legacy,
Linux x64, Linux aarch64).

To build locally you need the pinned dependencies above, then:
```sh
pip install -r requirements.txt
python compile.py
```

## Credits

| Role | Project / Person |
|---|---|
| Owner & Developer | [@Adnan.120hz](https://github.com/adnan120hz) |
| Main upstream (this is a fork of) | [GoldenNugget](https://github.com/GoldenNugget-Team/GoldenNugget) |
| MobileGestalt / eligibility / RDAR / risky ports | [Nugget](https://github.com/leminlimez/Nugget) by leminlimez |

The full contributor list (upstream developers, PosterRestore team, translators and
library authors) is shown in the app under **Settings → About → Credits**.

## License

This project is licensed under the **GNU Affero General Public License v3.0
(AGPL-3.0)** — this is required and cannot be changed, because WorkSlop
Desktop is a fork of GoldenNugget which is itself AGPL-3.0. See
[LICENSE](LICENSE) for the full text.
