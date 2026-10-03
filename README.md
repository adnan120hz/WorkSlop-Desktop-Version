<p align="center">
  <img src="assets/workslop-icon.jpg" width="160" alt="WorkSlop Desktop icon">
</p>

<h1 align="center">WorkSlop Desktop</h1>

<p align="center">
  A desktop application for customizing iPhone settings and appearance without
  a jailbreak, over a USB connection. WorkSlop Desktop is built with PySide6
  and is derived from the GoldenNugget project.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg" alt="License: AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg" alt="Platform: Windows | macOS | Linux">
  <a href="https://github.com/adnan120hz/WorkSlop-Desktop-Version/releases/latest"><img src="https://img.shields.io/badge/version-v11.0.1-brightgreen.svg" alt="Version v11.0.1"></a>
  <a href="https://github.com/adnan120hz/WorkSlop-Desktop-Version/releases"><img src="https://img.shields.io/badge/releases-GitHub-black.svg" alt="GitHub Releases"></a>
</p>

---

## Public Release

The current public release of WorkSlop Desktop is **v11.0.1**. It is available
for all three desktop platforms:

| Platform | Archive |
| --- | --- |
| Windows | `WorkSlopDesktop-v11.0.1-Windows.zip` |
| Linux (x86_64) | `WorkSlopDesktop-v11.0.1-Linux.tar.gz` |
| Linux (ARM64) | `WorkSlopDesktop-v11.0.1-Linux-aarch64.tar.gz` |
| macOS (Apple Silicon) | `WorkSlopDesktop-v11.0.1-macOS-AppleSilicon.zip` |
| macOS (Intel) | `WorkSlopDesktop-v11.0.1-macOS-Intel.zip` |
| macOS (Intel, legacy) | `WorkSlopDesktop-v11.0.1-macOS-IntelLegacy.zip` |

Download:
[github.com/adnan120hz/WorkSlop-Desktop-Version/releases/latest](https://github.com/adnan120hz/WorkSlop-Desktop-Version/releases/latest)

All earlier versions (v11.0 and below) predate the current public release and
several of them were published as pre-releases; v11.0.1 is the version
recommended for general use.

> [!WARNING]
> Always back up your iPhone before applying any tweak. WorkSlop Desktop
> includes protective-backup measures, but unexpected problems — including
> data loss — remain possible. Use this software at your own risk.

## What's New in v11.0.1

v11.0.1 is a small, focused maintenance release. It changes no tweak or
payload; it refines the backup workflow and interface consistency:

- The fixed "Backup Location" panel has been removed from the Backup page.
  When a Full Backup or a Protective Backup starts, the folder is now chosen
  in the system file picker; it is created automatically if it does not exist
  yet and the choice is remembered. The automatic protective backup that runs
  before an apply uses the same folder.
- The Backup page shows a live progress strip at the bottom (current step,
  percentage and progress bar) while a backup or restore is running.
- The Themes page and the classic Apply page are color-matched to the Nugget
  interface; the Themes page is fully dark in that interface.
- The Apply progress log ("Restoring to device… %" with the progress bar) is
  now shown in all three interfaces.

See [CHANGELOG.md](CHANGELOG.md) for the full release history.

## Features

### Three interfaces

The interface can be switched at any time under **Settings → Appearance**:

- **WorkSlop (Main)** — the original WorkSlop interface.
- **WorkSlop 2** — the classic shell with WorkSlop icons and the blue/white
  WorkSlop identity.
- **Nugget** — the original Nugget look and layout; only the application name
  and icon are WorkSlop's.

### Customization areas

- Liquid Glass controls (a WorkSlop set, plus a 100%-Nugget set inside the
  Nugget-based interfaces)
- SpringBoard options
- Status Bar customization
- MobileGestalt flags
- Feature Flags
- Eligibility options
- Daemons and services control
- PosterBoard (wallpapers)
- Icon themes and passcode themes
- Full Backup and protective backup

<p align="center">
  <img src="docs/images/interface-workslop-main.png" width="49%" alt="Apply page with progress log in the WorkSlop (Main) interface">
  <img src="docs/images/interface-nugget.png" width="49%" alt="Apply page in the Nugget interface">
</p>

> [!NOTE]
> What any individual tweak does on a given iPhone depends on the iOS version
> and build installed. Some options are version-gated and are shown locked,
> with the reason, when a device does not support them. There is no guarantee
> that a particular tweak takes effect on every iOS version — make a backup
> before applying, and test changes one at a time.

## Getting Started

1. Download the archive for your platform from
   [Releases](https://github.com/adnan120hz/WorkSlop-Desktop-Version/releases/latest)
   and extract it.
2. Run the application.
3. Connect your iPhone with a USB cable and tap **Trust** on the iPhone when
   asked to trust this computer.
4. Create a backup (Full Backup recommended) before applying any tweak.
5. Enable the options you want, then use the **Apply** page.

Platform requirements:

- **Windows** — the [Apple Devices](https://apps.microsoft.com/detail/9np83lwlpz9k)
  app from the Microsoft Store, or iTunes from Apple's website.
- **macOS** — no additional software required.
- **Linux** — `usbmuxd` and `libimobiledevice`.

Questions and bug reports:
[GitHub Issues](https://github.com/adnan120hz/WorkSlop-Desktop-Version/issues)

### Running from source

```sh
pip install -r requirements.txt
python main_app.py
```

Python 3.10 or newer is required. To build a standalone binary:

```sh
pip install -r requirements.txt
python compile.py
```

## Changelog

### v11.0.1 — 2026-10-03

- Backup folder is chosen in the system file picker when a Full Backup or
  Protective Backup starts (created automatically and remembered); the fixed
  "Backup Location" panel was removed.
- Live progress strip at the bottom of the Backup page.
- Themes and classic Apply pages color-matched to the Nugget interface.
- Apply progress log shown in all three interfaces.
- No tweak changes.

### v11.0 — 2026-10-03

- Three selectable interfaces: WorkSlop (Main), WorkSlop 2 and Nugget.
- Liquid Glass section rebuilt around the WorkSlop set restored verbatim to
  its v4 form, plus a separate 100%-Nugget Liquid Glass set in the
  Nugget-based interfaces.
- Eligibility and MobileGestalt options locked (fail-closed) on iOS 26.2
  beta 2 (build `23C5035e`) and newer; supported up to `23C5027f`.
- Backup stall watchdog on every backup path; new WorkSlop brand icon;
  beta tester team credited on the Home page.

[Full changelog](CHANGELOG.md)

## Credits

**Developer:** Adnan.120hz
([TikTok](https://www.tiktok.com/@adnan.120hz?_r=1&_t=ZS-9AElXliY2Me) ·
[GitHub](https://github.com/adnan120hz) ·
[Official Website](https://adnan120hz.vercel.app))

**UI reference:** Nugget UI

WorkSlop Desktop is based on
[GoldenNugget](https://github.com/GoldenNugget-Team/GoldenNugget) and
incorporates modules from [Nugget](https://github.com/leminlimez/Nugget) by
leminlimez.

Also credited: awesomenull · Wind0ws11Aero · PosterRestore ·
pymobiledevice3 · PySide6 · Quiet Daemon (Mikasa-san) · Snoolie ·
f1shy-dev · JJTech0130

**Beta tester team:** Charlie, rfrz1d_, Davy (@Davydavpn)

## License

WorkSlop Desktop is licensed under the **GNU Affero General Public License
v3.0 (AGPL-3.0)**. As a derivative of GoldenNugget, it remains under the same
license as its upstream. See [LICENSE](LICENSE) for the full text.
