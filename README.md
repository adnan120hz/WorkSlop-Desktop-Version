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

| iOS version | Tweaks | MobileGestalt |
|---|---|---|
| 26.x | Partial restore (sparse restore, no wipe) | iOS 26.1 and below only |
| 27 and newer | Backup → tweak → restore flow | Not supported (locked in the UI) |
| 25 and older | Not supported | iOS 17.0 – 25.x supported |

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
