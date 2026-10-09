"""Caller-side guards for icon-pack zip imports (Fix Audit 4 + 88).

The frozen ``IconThemesTweak`` importers do the actual extraction and
importing; everything that can go wrong *before* an archive is trusted
lives here, on the caller side, so the frozen model never changes:

* a zip over a sane size limit is rejected before it is even opened
  (a downloaded or picked pack is a handful of PNGs — the bundled
  101-icon catalog is nowhere near this limit);
* a password-protected (encrypted) zip raises a readable
  :class:`IconPackImportError` instead of leaking zipfile's raw
  ``RuntimeError: ... password ...`` to the UI;
* a downloaded pack that matches the bundled catalog is verified
  through the existing SHA-256 hash-matched importer; any other pack
  must at least be shaped like an icon pack (icons named by bundle ID,
  the naming rule ``scan_icon_pack`` consumes) before the name-based
  importer sees it, and the outcome says plainly which of the two
  happened — hash-verified vs name-only.
"""

from __future__ import annotations

import io
import os
import zipfile
from dataclasses import dataclass, field

#: Sane ceiling for one icon pack, enforced BEFORE opening/extraction.
#: Real packs (the bundled 101-icon catalog included) are tens of MB;
#: 200 MB leaves generous headroom without letting a hostile or broken
#: download balloon into an unbounded extraction.
MAX_ICON_PACK_ZIP_BYTES = 200 * 1024 * 1024

_IMAGE_EXTENSIONS = (".png", ".heic", ".jpg", ".jpeg", ".webp")
_NAME_SUFFIXES = ("-large", "@2x", "@3x")


class IconPackImportError(Exception):
    """A user-readable icon-pack import failure (never a raw zip error)."""


@dataclass
class PackImportOutcome:
    """What one downloaded-pack import actually did (Fix Audit 88)."""

    added: int = 0
    skipped: list = field(default_factory=list)
    already_present: int = 0
    hash_verified: bool = False

    @property
    def verification_note(self) -> str:
        if self.hash_verified:
            return ("Icons verified by SHA-256 against the bundled "
                    "catalog.")
        return ("Icons imported by file name only — NOT hash-verified "
                "against the bundled catalog.")


def ensure_pack_zip_within_limit(size_bytes: int,
                                 limit: int = MAX_ICON_PACK_ZIP_BYTES) -> None:
    """Reject an oversized pack before it is opened (Fix Audit 4)."""
    if size_bytes > limit:
        raise IconPackImportError(
            f"That icon pack is {size_bytes / (1024 * 1024):.1f} MB — "
            f"over the {limit // (1024 * 1024)} MB safety limit for a "
            "single icon pack, so it was not opened.")


def probe_pack_zip(source) -> list:
    """Open ``source`` (path or bytes) just far enough to trust it.

    Returns the entry names. Raises :class:`IconPackImportError` with a
    readable message for a non-zip file and for a password-protected
    archive — zipfile would otherwise surface the latter as a raw
    ``RuntimeError`` mentioning "password" deep inside extraction.
    """
    try:
        if isinstance(source, (bytes, bytearray)):
            archive = zipfile.ZipFile(io.BytesIO(bytes(source)))
        else:
            archive = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError) as exc:
        raise IconPackImportError(
            "That file could not be read as an icon pack (.zip)."
        ) from exc
    with archive:
        infos = archive.infolist()
        if any(info.flag_bits & 0x1 for info in infos):
            raise IconPackImportError(
                "That icon pack is password-protected (encrypted), so "
                "it cannot be imported. Remove the password protection "
                "and try again.")
        return [info.filename for info in infos]


def _strip_icon_suffix(filename: str) -> str:
    """Mirror of the pack naming rule (``<bundleID>[-large|@2x|@3x]``)."""
    base = os.path.splitext(filename)[0]
    for suffix in _NAME_SUFFIXES:
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def bundle_id_icon_names(names) -> list:
    """Entries shaped like pack icons: image files named by bundle ID."""
    out = []
    for name in names:
        base = name.replace("\\", "/").split("/")[-1]
        if not base.lower().endswith(_IMAGE_EXTENSIONS):
            continue
        if "." in _strip_icon_suffix(base):
            out.append(name)
    return out


def validate_name_based_pack(names) -> None:
    """Reject a zip that is not shaped like an icon pack (Fix Audit 88).

    The name-based importer names themes after files, so a pack whose
    images are not named by bundle ID (``<bundleID>.png`` etc.) would
    only invent bogus themes — refuse it before extraction instead.
    """
    if not bundle_id_icon_names(names):
        raise IconPackImportError(
            "That archive does not look like an icon pack: it has no "
            "icons named by bundle ID (for example "
            "com.apple.camera.png). Nothing was imported.")


def import_local_pack_zip(tweak, archive_path: str, hash_index: dict) -> dict:
    """Guarded local-file import for the Icon Themes page (Fix Audit 4).

    Size limit first, structure/encryption probe second, then the
    frozen hash-matched importer. Any zipfile ``RuntimeError`` still
    escaping the importer (an encrypted member the probe could not
    see) is converted to a readable :class:`IconPackImportError`.
    """
    ensure_pack_zip_within_limit(os.path.getsize(archive_path))
    probe_pack_zip(archive_path)
    try:
        return tweak.import_pack_zip_matched(archive_path, hash_index)
    except RuntimeError as exc:
        if "password" in str(exc).lower():
            raise IconPackImportError(
                "That icon pack is password-protected (encrypted), so "
                "it cannot be imported. Remove the password protection "
                "and try again.") from exc
        raise IconPackImportError(
            f"That icon pack could not be imported: {exc}") from exc


def import_downloaded_pack(tweak, data: bytes, theme_name,
                           hash_index: dict) -> PackImportOutcome:
    """Import one downloaded pack with honest verification (Fix Audit 88).

    Packs matching the bundled catalog go through the SHA-256
    hash-matched importer and report ``hash_verified``; other packs
    must pass the bundle-ID structure check and go through the
    name-based importer, reported as name-only.
    """
    ensure_pack_zip_within_limit(len(data))
    names = probe_pack_zip(data)

    matched = None
    try:
        import tempfile
        fd, path = tempfile.mkstemp(prefix="icontheme_dl_", suffix=".zip")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            matched = tweak.import_pack_zip_matched(path, hash_index)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    except RuntimeError as exc:
        if "password" in str(exc).lower():
            raise IconPackImportError(
                "That icon pack is password-protected (encrypted), so "
                "it cannot be imported. Remove the password protection "
                "and try again.") from exc
        raise

    if matched is not None and matched.get("archive_ok") and (
            matched.get("imported") or matched.get("already_present")):
        return PackImportOutcome(
            added=len(matched["imported"]),
            skipped=list(matched.get("unmatched") or []),
            already_present=len(matched.get("already_present") or []),
            hash_verified=True)

    # No catalog match: only a genuinely pack-shaped archive may go
    # through the name-based importer, and the outcome must say the
    # icons were NOT hash-verified.
    validate_name_based_pack(names)
    import tempfile
    fd, path = tempfile.mkstemp(prefix="icontheme_dl_", suffix=".zip")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        try:
            added, skipped = tweak.import_pack_zip(
                path, theme_name=theme_name)
        except RuntimeError as exc:
            if "password" in str(exc).lower():
                raise IconPackImportError(
                    "That icon pack is password-protected (encrypted), "
                    "so it cannot be imported. Remove the password "
                    "protection and try again.") from exc
            raise
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return PackImportOutcome(
        added=added, skipped=list(skipped or []), hash_verified=False)
