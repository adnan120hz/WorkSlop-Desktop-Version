from sys import platform, argv
import os
import re
import shutil # Added for the macOS fix
import subprocess
import platform as _platform_mod
import PyInstaller.__main__

target_arch = next((arg for arg in argv if arg.startswith("--target-arch=")), None)
if target_arch:
    print(f"[+] Target arch: {target_arch}")


def _package_macos_app(dist_path):
    """Zip the built .app bundle so the top-level archive entry is WorkSlopDesktop.app.

    PyInstaller --onedir --windowed produces BOTH dist/WorkSlopDesktop.app and a loose
    dist/WorkSlopDesktop/ folder. Zipping the wrong one makes users extract a bare
    'Contents' folder that Finder does not treat as an app (issue #29).
    ditto --keepParent pins WorkSlopDesktop.app as the archive root and preserves
    symlinks/resource forks, so extraction yields a proper .app bundle.
    """
    arch = None
    if target_arch:
        m = re.search(r"=([^=]+)$", target_arch)
        if m:
            arch = m.group(1)
    arch_label = arch or _platform_mod.machine()
    arch_map = {"arm64": "Apple-Silicon", "x86_64": "Intel", "universal2": "Universal"}
    arch_label = arch_map.get(arch_label, arch_label)

    app_path = os.path.join(dist_path, "WorkSlopDesktop.app")
    if not os.path.isdir(app_path):
        print(f"[!] macOS packaging skipped: {app_path} not found")
        return

    zip_path = os.path.join(dist_path, f"WorkSlopDesktop-macOS-{arch_label}.zip")
    subprocess.run(
        ["ditto", "-c", "-k", "--keepParent", app_path, zip_path],
        check=True,
    )
    print(f"[+] macOS app packaged: {zip_path} (extracts to WorkSlopDesktop.app)")

# Base PyInstaller args
import sys as _sys
if _sys.platform == "darwin":
    _icon_file = "workslop.icns"
elif os.name == "nt":
    _icon_file = "workslop.ico"
else:
    _icon_file = "workslop_icon.png"
args = [
'workslop_cli.py',
    '--name=WorkSlopDesktop',
    f'--icon={_icon_file}',
    '--onedir',
    '--noconfirm',
    '--collect-all=pymobiledevice3',
    '--collect-all=pillow_heif',
    '--collect-all=PIL',
    '--add-data=files/:files',
    '--copy-metadata=pyimg4',
    '--hidden-import=zeroconf',
    '--hidden-import=pyimg4',
    '--hidden-import=zeroconf._utils.ipaddress',
    '--hidden-import=zeroconf._handlers.answers',
    '--hidden-import=src.qt.resources_rc',
    '--add-data=src/qt:src/qt',
    # Bundle the helper tool modules (imported lazily by the CLI wrapper).
    '--hidden-import=apply_wallpaper',
    '--hidden-import=restore_cache',
    '--hidden-import=restore',
    '--hidden-import=skip_setup',
    '--hidden-import=main_app',
    # Runtime window icon (loaded by MainWindow from repo root).
    '--add-data=workslop_icon.png' + (';.' if os.name == 'nt' else ':.'),
]

if target_arch:
    args.append(target_arch)

# macOS-specific flags
if platform == "darwin":
    
    # --- MACOS OPENSSL FIX ---
    # Delete sslpsk_pmd3's bundled OpenSSL before PyInstaller collects it.
    # This forces fallback to Python's built-in _ssl without breaking codesign.
    try:
        import sslpsk_pmd3
        sslpsk_path = os.path.dirname(sslpsk_pmd3.__file__)
        dylibs_path = os.path.join(sslpsk_path, "__dot__dylibs")
        if os.path.exists(dylibs_path):
            print(f"[-] macOS Fix: Removing conflicting bundled dylibs from {dylibs_path}")
            shutil.rmtree(dylibs_path, ignore_errors=True)
    except ImportError:
        print("[!] sslpsk_pmd3 not found, skipping macOS dylib cleanup.")
    # -------------------------

    args.append('--windowed')
    args.append('--osx-bundle-identifier=com.adnan120hz.WorkSlopDesktop')

    try:
        import secrets_nugget.compile_config as compile_config
        args.append('--osx-entitlements-file=entitlements.plist')
        args.append(f"--codesign-identity={compile_config.CODESIGN_HASH}")
    except ImportError:
        print("[!] Codesign skipped: compile_config not found")

elif os.name == 'nt':
    args.append('--version-file=version.txt')
    args.append('--add-data=workslop.ico;.')
    
    try:
        import pytun_pmd3
        package_path = os.path.dirname(pytun_pmd3.__file__)
        print(f"[+] Found pytun_pmd3 at: {package_path}")
        args.append('--add-binary')
        args.append(f"{package_path}/*;pytun_pmd3")
    except ImportError:
        print("[!] ERROR: Could not import pytun_pmd3. Ensure it is installed with pip.")
        import site
        site_packages_path = site.getsitepackages()[1]
        args.append('--add-binary')
        args.append(f"{site_packages_path}/pytun_pmd3/*;pytun_pmd3")

    if os.path.isdir("ffmpeg/bin"):
        args.append('--add-data=ffmpeg/bin;ffmpeg/bin')
    else:
        print("[!] ffmpeg not bundled: folder not found")

    if os.path.isdir("idevice"):
        args.append('--add-data=idevice;idevice')
    else:
        print("[!] libimobiledevice binaries not bundled: 'idevice' folder not found")

# zsign (built from source via tools/build_zsign.py) — the sideloading
# engine looks for it next to the frozen executable, in the vendor dir,
# on PATH, or via WORKSLOP_ZSIGN. Bundling it here covers the common case.
_zsign = os.path.join("vendor", "zsign.exe" if os.name == "nt" else "zsign")
if os.path.isfile(_zsign):
    _sep = ";" if os.name == "nt" else ":"
    args.append('--add-binary')
    args.append(f"{_zsign}{_sep}.")
    print(f"[+] Bundling zsign: {_zsign}")
else:
    print("[!] zsign not bundled: run tools/build_zsign.py first "
          "(sideload signing will need zsign on PATH or WORKSLOP_ZSIGN)")

PyInstaller.__main__.run(args)

if platform == "darwin":
    _package_macos_app("dist")