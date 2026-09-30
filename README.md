# WorkSlop Desktop

**Owner & Developer: [@Adnan.120hz](https://github.com/adnan120hz)**

Customize your iPhone without jailbreak — tweaks, MobileGestalt flags, wallpapers,
themes and backups in one app, with the same Cobalt Flow look on Windows, Linux and macOS.

WorkSlop Desktop is a fork of [GoldenNugget](https://github.com/GoldenNugget-Team/GoldenNugget)
with a redesigned interface and a safer backup system: when the protective device
backup reaches 100%, the file manager opens with the finished backup selected so
you can copy it somewhere safe before the apply continues.

> [!WARNING]
> Always back up your data before applying tweaks. WorkSlop Desktop tries to
> protect your data, but unexpected problems can still happen — we are not
> responsible for any data loss or bootloops. Use at your own risk.

## Features

- **Home** — device overview, quick actions and status
- **Tweaks** — SpringBoard options, internal options, status bar, daemons and more
- **MobileGestalt** — device feature flags ported from Nugget (see version support below)
- **Wallpaper** — PosterBoard animated wallpapers, descriptors and templates
- **Backup** — full iTunes-style backup, protective backup, and restore
- **Themes** — icon themes and passcode themes
- **Settings** — appearance, language, safety options and about

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
| 16.7 – 16.7.11 | 20H19, 20H24, 20H30, 20H57, 20H68, 20H115, 20H219, 20H315, 20H332, 20H350 |
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
| Tweaks (Apply) | All 49 builds. iOS 26.x and below: partial sparse restore (no wipe). iOS 27: classic protective flow (backup → tweak → **reboot** → wipe → reconnect → restore). The device reboots on Apply, like the original GoldenNugget. |
| MobileGestalt | **Open on iOS 16.0 → iOS 26.2 beta 1** (builds `20A362`–`23C5027f`). Locked on 26.2 beta 2 and newer — menu stays visible with the reason. |
| Status Bar | **Locked on any iOS 27 build** (`24A…`). Open on iOS 26 and below. |
| Daemons / Liquid Glass | Unchanged, as before. |

> Standalone backup actions (**Full Backup**) do **not** reboot the device —
> they just export the backup file to the folder you choose, like saving it
> for later. Only **Restore Backup** and **Apply** reboot the device.

The MobileGestalt menu stays visible on all versions but locks itself automatically
on iOS 26.2 and newer.

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
[build workflow](.github/workflows/build.yml) on every push to `main`.

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
| MobileGestalt module port | [Nugget](https://github.com/leminlimez/Nugget) by leminlimez |
| MobileGestalt menu port | [misakaReborn](https://github.com/straight-tamago/misakaReborn) by straight-tamago |

The full contributor list (upstream developers, PosterRestore team, translators and
library authors) is shown in the app under **Settings → About → Credits**.

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**,
following the upstream GoldenNugget license. See [LICENSE](LICENSE) for the full text.
