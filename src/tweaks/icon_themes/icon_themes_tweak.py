# FROZEN 2026-10-09 (user order): Icon Themes menu is device-proven.
# Do not change behavior without an explicit order from the user;
# verified by tools/test_icon_themes_frozen.py.
"""Icon theming via HomeDomain WebClip folders.

Port of Cowabunga (Lite)'s "icon theming" feature to GoldenNugget. The real
app icons are never touched: for every themed app a WebClip folder is created
at ``HomeDomain/Library/WebClips/WorkSlop_<bundleID>,<displayName>.webclip/``
(WebClip folders written by older builds used the ``Cowabunga_`` prefix;
nothing in the app matches folders by prefix — see apply_tweak — so those
shortcuts simply stay on the device until the user deletes them.)
containing an ``Info.plist`` whose ``ApplicationBundleIdentifier`` points at
the REAL app bundle id — so tapping the replaced icon launches the actual app
directly (no "open in Safari" banner) — and an ``icon.png``. The folders are
delivered as regular HomeDomain ``FileToRestore`` entries, so they ride the
same restore path as the well-tested HomeDomain tweak files on every
supported version.
"""

import hashlib
import os
import plistlib
import shutil
import tempfile
import zipfile
from shutil import copyfile

from PySide6.QtCore import QCoreApplication, QStandardPaths

from ..tweak_classes import Tweak
from .icon_theme import IconTheme

from src.utils.file_to_restore import FileToRestore


def persistent_themes_dir() -> str:
    """Stable folder holding the icon PNGs so applies/presets never depend on
    the original picker location (which could move or disappear)."""
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    folder = os.path.join(base, "GoldenNugget", "IconThemes")
    os.makedirs(folder, exist_ok=True)
    return folder


def build_pack_hash_index(catalog) -> dict:
    """Map the sha256 of bundled icon files to their catalog entry.

    *catalog* is an iterable of ``(bundle_id, display_name, light_path,
    dark_path)``; a path may be empty or missing (e.g. the iOS 18 pack
    ships no Dark Shortcuts). Light is inserted first so artwork whose
    Light and Dark renders are byte-identical resolves to Light.
    Returns ``{sha256: (bundle_id, display_name, dark)}``.
    """
    index: dict = {}
    for bundle_id, display_name, light_path, dark_path in catalog:
        for dark, path in ((False, light_path), (True, dark_path)):
            if not path or not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            index.setdefault(digest, (bundle_id, display_name, dark))
    return index


def make_webclip_plist(bundle_id: str, display_name: str) -> bytes:
    """WebClip Info.plist exactly like Cowabunga's ``makeInfoPlist``."""
    info = {
        "ApplicationBundleIdentifier": bundle_id,
        "ApplicationBundleVersion": 1,
        "ClassicMode": False,
        "ConfigurationIsManaged": False,
        "ContentMode": "UIWebClipContentModeRecommended",
        "FullScreen": True,
        "IconIsPrecomposed": False,
        "IconIsScreenShotBased": False,
        "IgnoreManifestScope": False,
        "IsAppClip": False,
        "Orientations": 0,
        "ScenelessBackgroundLaunch": False,
        "Title": display_name,
        "WebClipStatusBarStyle": "UIWebClipStatusBarStyleDefault",
        "RemovalDisallowed": False,
    }
    return plistlib.dumps(info, fmt=plistlib.PlistFormat.FMT_XML)


class IconThemesTweak(Tweak):
    def __init__(self):
        super().__init__(key=None)
        self.themes: list[IconTheme] = []

    def uses_domains(self):
        # WebClip folders all live under HomeDomain.
        return not self.is_empty()

    def is_empty(self) -> bool:
        return len(self.themes) == 0

    def add_theme(self, theme: IconTheme):
        # Replace an existing theme for the same bundle instead of adding a
        # second (and potentially conflicting) WebClip folder.
        for existing in self.themes:
            if existing.bundle_id == theme.bundle_id:
                self.themes.remove(existing)
                break
        self.themes.append(theme)

    def remove_theme(self, bundle_id: str):
        self.themes = [t for t in self.themes if t.bundle_id != bundle_id]

    @staticmethod
    def strip_icon_suffix(filename: str) -> str:
        """Strip Cowabunga's icon-name suffixes (``-large``, ``@2x``, ``@3x``)
        so ``com.apple.AppStore@2x.png`` maps to the bundle id
        ``com.apple.AppStore`` — same rules as ``appIDFromIcon``."""
        base = os.path.splitext(filename)[0]
        for suffix in ("-large", "@2x", "@3x"):
            if base.endswith(suffix):
                return base[: -len(suffix)]
        return base

    @staticmethod
    def _dpi_rank(rel_path: str) -> int:
        # Prefer the most detailed icon a pack ships: top-level flat files
        # rank best, then "@3x", then "@2x" subfolders.
        parts = rel_path.replace("\\", "/").split("/")
        parent = parts[-2].lower() if len(parts) > 1 else ""
        if len(parts) == 1:
            return 0
        if "3x" in parent or "@3x" in parent:
            return 1
        if "2x" in parent or "@2x" in parent:
            return 2
        return 3

    @classmethod
    def scan_icon_pack(cls, folder: str) -> list[tuple[str, str]]:
        """Scan an icon-pack folder for ``<bundleID>.png`` files.

        Mirrors Cowabunga's theme folder (flat files named by bundle id) but
        also descends into ``2x``/``3x`` subfolders (choosing the highest-DPI
        match) and ignores ``__MACOSX``/dotfile junk found in real .theme
        archives. Returns ``[(bundle_id, abs_path)]`` sorted by bundle id.
        """
        IMAGE_EXTENSIONS = (".png", ".heic", ".jpg", ".jpeg", ".webp")
        best: dict[str, tuple[int, int, str]] = {}  # bundle_id -> (rank, len, path)
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs
                       if not d.startswith((".", "_", "__MACOSX"))]
            for name in sorted(files):
                if name.startswith(".") or name.startswith("._"):
                    continue
                if not name.lower().endswith(IMAGE_EXTENSIONS):
                    continue
                path = os.path.join(root, name)
                if not os.path.isfile(path):
                    continue
                bundle_id = cls.strip_icon_suffix(name)
                if not bundle_id:
                    continue
                rel = os.path.relpath(path, folder)
                rank = (cls._dpi_rank(rel), len(rel), path)
                prev = best.get(bundle_id)
                if prev is None or rank < prev:
                    best[bundle_id] = rank
        return sorted((bid, path) for bid, (_, _, path) in best.items())

    def import_pack(self, folder: str) -> tuple[int, list[str]]:
        """Add every icon in *folder* as a theme.

        Pack icons default to ``display_name=""`` (label hidden) matching the
        trend of these packs; per-app labels can be added individually on top.
        Returns ``(added, skipped_bundle_ids)``.
        """
        added = 0
        skipped = []
        for bundle_id, path in self.scan_icon_pack(folder):
            theme = IconTheme(bundle_id=bundle_id, icon_path=path)
            if not self.store_icon(theme):
                skipped.append(bundle_id)
                continue
            self.add_theme(theme)
            added += 1
        return added, skipped

    def import_pack_zip(self, archive_path: str,
                        theme_name: str = None) -> tuple[int, list[str]]:
        """Extract an icon-pack archive and import the icons inside.

        Follows Cowabunga: explore-repo zips store their icons in a
        ``<ThemeName>/`` folder, standalone .theme archives expose an
        ``IconBundles`` folder. Returns ``(added, skipped_bundle_ids)``.
        """
        tmp = tempfile.mkdtemp(prefix="icontheme_pack_")
        try:
            with zipfile.ZipFile(archive_path) as zf:
                self._safe_extractall(zf, tmp)
            folder = self.resolve_icon_folder(tmp, theme_name)
            return self.import_pack(folder)
        except (zipfile.BadZipFile, OSError):
            return 0, []
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def import_pack_zip_matched(self, archive_path: str,
                                hash_index: dict) -> dict:
        """Import a pack zip by CONTENT, never by file name.

        Some packs (e.g. "iOS 18 App Icons by catwithabaloon") ship
        generic file names (``App Icon-37.png``) that carry no bundle id
        at all, so the name-based :meth:`import_pack_zip` can only
        invent bogus themes pointing at apps that do not exist. Here
        every extracted image is sha256-matched against *hash_index*
        (built from the bundled catalog files via
        :func:`build_pack_hash_index`): a byte-identical file IS the
        catalog icon, so no bundle id is ever guessed from a name.

        One theme per app — Light wins when both variants match (the
        same rule as the iOS 18 table's Add All) — and apps already in
        Icon Themes are skipped so a hand-picked variant is never
        clobbered by a bulk import. Files matching nothing come back in
        ``unmatched`` (paths relative to the zip root) so the caller can
        report them by name; they are never silently dropped and never
        turned into invented bundle ids.

        Returns a dict: ``archive_ok``, ``imported`` (list of
        ``(bundle_id, display_name, dark)``), ``already_present``
        (bundle ids skipped), ``store_failed`` (bundle ids whose icon
        could not be copied into the persistent store) and ``unmatched``
        (relative file names).
        """
        result = {
            "archive_ok": False,
            "imported": [],
            "already_present": [],
            "store_failed": [],
            "unmatched": [],
        }
        image_exts = (".png", ".heic", ".jpg", ".jpeg", ".webp")
        tmp = tempfile.mkdtemp(prefix="icontheme_match_")
        try:
            try:
                with zipfile.ZipFile(archive_path) as zf:
                    self._safe_extractall(zf, tmp)
            except (zipfile.BadZipFile, OSError):
                return result
            result["archive_ok"] = True

            # bundle_id -> (dark, display_name, extracted path)
            chosen: dict = {}
            for root, dirs, files in os.walk(tmp):
                dirs.sort()
                for name in sorted(files):
                    if not name.lower().endswith(image_exts):
                        continue
                    path = os.path.join(root, name)
                    with open(path, "rb") as f:
                        digest = hashlib.sha256(f.read()).hexdigest()
                    match = hash_index.get(digest)
                    if match is None:
                        result["unmatched"].append(
                            os.path.relpath(path, tmp))
                        continue
                    bundle_id, display_name, dark = match
                    prev = chosen.get(bundle_id)
                    # Light wins over Dark; first match wins otherwise.
                    if prev is None or (prev[0] and not dark):
                        chosen[bundle_id] = (dark, display_name, path)

            existing = {t.bundle_id for t in self.themes}
            for bundle_id in sorted(chosen):
                dark, display_name, path = chosen[bundle_id]
                if bundle_id in existing:
                    result["already_present"].append(bundle_id)
                    continue
                theme = IconTheme(bundle_id=bundle_id,
                                  display_name=display_name,
                                  icon_path=path)
                if not self.store_icon(theme):
                    result["store_failed"].append(bundle_id)
                self.add_theme(theme)
                existing.add(bundle_id)
                result["imported"].append((bundle_id, display_name, dark))
            return result
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _safe_extractall(zf: zipfile.ZipFile, dest: str) -> None:
        """extractall() with a zip-slip guard (CWE-22).

        A crafted archive can carry entries like ``../../evil.sh`` that a
        plain extractall() would write outside *dest*. Delegates to the
        shared ``src.utils.zip_safe.safe_extractall`` so the guard logic
        exists in exactly one place.
        """
        from src.utils.zip_safe import safe_extractall
        safe_extractall(zf, dest)

    @staticmethod
    def resolve_icon_folder(extract_root: str, theme_name: str = None) -> str:
        """Locate the folder holding the icons inside an extracted archive."""
        if theme_name:
            named = os.path.join(extract_root, theme_name)
            if os.path.isdir(named):
                return named
        best = extract_root
        best_len = 0
        for root, dirs, files in os.walk(extract_root):
            # prefer a directory literally named IconBundles
            if os.path.basename(root) == "IconBundles":
                return root
            # otherwise the icon folder is the one holding the MOST files.
            # (Picking the fewest -- e.g. a Docs/ or Preview/ sidecar folder --
            # silently imported nothing from zips that ship sidecars next to
            # the icons.)
            n = len(files)
            if n > best_len:
                best, best_len = root, n
        return best

    def store_icon(self, theme: IconTheme):
        """Copy a theme's icon into the persistent store and point it there.

        Returns True when the icon is durably available for future applies.
        Idempotent for icons that already live in the store.
        """
        if theme.icon_data is not None:
            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in theme.bundle_id)
            dest = os.path.join(persistent_themes_dir(), f"{safe}.png")
            try:
                with open(dest, "wb") as f:
                    f.write(theme.icon_data)
                theme.icon_path = dest
                theme.icon_data = None
                return True
            except OSError:
                return False
        if theme.icon_path and os.path.isfile(theme.icon_path):
            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in theme.bundle_id)
            dest = os.path.join(persistent_themes_dir(), f"{safe}.png")
            try:
                if os.path.realpath(theme.icon_path) != os.path.realpath(dest):
                    copyfile(theme.icon_path, dest)
                theme.icon_path = dest
                return True
            except OSError:
                return False
        return False

    def sanitize_display_name(self, name: str) -> str:
        # Commas break the WebClip folder name pattern (it's a single comma-
        # separated string), and path separators would break restore paths.
        return "".join(" " if c in ",/" else c for c in name)

    def apply_tweak(self, files_to_restore: list[FileToRestore],
                    output_dir: str = None,
                    update_label=lambda x: None):
        if self.is_empty():
            return
        update_label(QCoreApplication.tr("Generating icon themes..."))
        skipped = []
        for theme in self.themes:
            display_name = self.sanitize_display_name(theme.display_name)
            folder = f"Library/WebClips/WorkSlop_{theme.bundle_id},{display_name}.webclip"

            # Info.plist
            files_to_restore.append(FileToRestore(
                contents=make_webclip_plist(theme.bundle_id, display_name),
                restore_path=f"{folder}/Info.plist",
                domain="HomeDomain"
            ))

            # icon.png — bytes by preference, then the stored path, then final
            # fallback to the persistent store copy.
            data = theme.get_icon_data()
            if data is None and theme.icon_path and os.path.isfile(theme.icon_path):
                with open(theme.icon_path, "rb") as f:
                    data = f.read()
            if data is None:
                skipped.append(theme.bundle_id)
                continue
            files_to_restore.append(FileToRestore(
                contents=data,
                restore_path=f"{folder}/icon.png",
                domain="HomeDomain"
            ))
        if skipped:
            update_label(QCoreApplication.tr(
                "Skipped icon themes without icon file: {0}").format(", ".join(skipped)))
        update_label(QCoreApplication.tr("Adding icon themes..."))