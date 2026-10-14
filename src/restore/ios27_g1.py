"""iOS 27 apply route: full backup -> inject -> restore.

Pipeline (user order 2026-10-11): full backup of ALL device data to this
computer -> build a payload adapted to the tweaks the user enabled ->
modify (inject the payload into the backup) -> full restore of the
backup. No wipe, no sparse-restore phase, no selective/drained backup:
the backup taken here IS the user's data protection.

Honesty note: this route is NOT yet device-proven on a real iOS 27
iPhone. The underlying full-backup -> modify -> restore truck was proven
on 2x iOS 26.6.1 RC devices (the lgd_full.py route), but everything
iOS-27-specific in this module — the eligibility gate, the stall
watchdog, the payload merge, the dedicated backup pool — has never run
against a real iOS 27 device.

Watchdog: stall-based (user order 2026-10-11). The watchdog fires only
when the route goes quiet — no progress from the device for
``WATCHDOG_STALL_SECONDS`` (10 minutes). A healthy backup/restore that
keeps moving is never interrupted, no matter how long the full backup
takes. A new phase is never STARTED after a stall is detected; the
backup itself is aborted on a stall (it writes nothing to the device,
so aborting it is safe). A restore already in flight is NEVER
interrupted — cutting a restore mid-flight is exactly the unsafe
action this watchdog exists to prevent.

Eligibility: iOS 27.0 Developer Beta 1-9, 27.0 RC, 27.0 official
stable, and 27.0.1 only. Anything else (other 27.x, non-26.x below
27) is rejected with "Not supported" before anything runs. Beta/RC
builds report ProductVersion "27.0" over the cable, so the version
gate covers every 27.0 variant including dev beta 9 (whose build
number is not in our verified list); the build allowlist gives
build-level precision for the user-verified 27.0 builds.

The payload is NOT hardcoded: it is built from the staged
``FileToRestore`` list the normal tweak pass produced, so every
enabled tweak contributes its own target files (multi-tweak
adaptation is structural, not a special case). The per-tweak -> file
attribution is derived from the Apply Journal entries (registry spec
``location`` joined to the payload's (domain, path)), never from a
hardcoded file list.

The iOS 26 partial-restore route is untouched by this module.
"""

import asyncio
import os
import sqlite3
import time
from pathlib import Path

from packaging.version import Version
from PySide6.QtCore import QCoreApplication

from src.exceptions.nugget_exception import NuggetException
from src.restore.protective import (
    backup_file_id,
    device_dir_for,
    inject_accounting_ok,
    payload_disk_path,
)
from src.utils.log_util import log_info, log_warn
from src.utils.udid_sanitize import sanitize_udid


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

#: Stall watchdog for the iOS 27 route (user order 2026-10-11): the
#: route is aborted only when the device goes quiet — no progress for
#: this long. A healthy full backup that keeps moving is never cut
#: off, however long it takes. 10 minutes: longer than the inner 300s
#: device-I/O stall watchdog, so this one acts as the route-level
#: backstop for phases with no progress ticks of their own (staging,
#: payload planning, injection, verification).
WATCHDOG_STALL_SECONDS = 10 * 60

#: File owner/group used when a staged file does not say otherwise:
#: the ``mobile`` user (uid/gid 501), the standard owner of user-data
#: files in an iOS backup. (lgd_full.py names the same value ``_OWNER``.)
_FILE_OWNER_MOBILE = 501

#: iOS 27.0 builds verified by the user (2026-09-30): dev betas 1-8,
#: then the 27.0 RC + official stable. Dev beta 9's build number is not
#: in the verified list — it is covered by the "27.0" version gate
#: below (all 27.0 variants report ProductVersion "27.0" over the cable).
IOS27_G1_SUPPORTED_BUILDS = frozenset({
    "24A5355q", "24A5370h", "24A5380h", "24A5390f",
    "24A5408d", "24A5418b", "24A5424a", "24A5430a",
    "24A435", "24A437",
})

#: Supported ProductVersion values. "27.0" covers Developer Beta 1-9,
#: the RC, and the official stable (all report "27.0"); "27.0.1" is the
#: only other supported release.
IOS27_G1_SUPPORTED_VERSIONS = (Version("27.0"), Version("27.0.1"))

NOT_SUPPORTED_MESSAGE = (
    "Not supported: this device runs an iOS version outside the "
    "supported list (iOS 27.0 Developer Beta 1-9, 27.0 RC, 27.0 "
    "official, 27.0.1). Nothing was applied."
)


def is_ios27_g1_supported(version, build) -> bool:
    """True only for the supported iOS 27 set (see module docstring)."""
    try:
        parsed = Version(str(version or ""))
    except Exception:
        parsed = None
    if parsed is not None and parsed in IOS27_G1_SUPPORTED_VERSIONS:
        return True
    if str(build or "") in IOS27_G1_SUPPORTED_BUILDS:
        return True
    return False


# ---------------------------------------------------------------------------
# Pre-apply warning (English, blunt; shown and confirmed before the route)
# ---------------------------------------------------------------------------

IOS27_WARNING_TITLE = "iOS 27 — Risk Warning"

IOS27_WARNING_TEXT = (
    "WARNING: applying tweaks on iOS 27 is experimental and risky.\n\n"
    "iOS 27 can put your iPhone into a BOOTLOOP (the phone gets stuck "
    "on the Apple logo and will not start). A full backup of ALL your "
    "data is taken to this computer before anything is written, but a "
    "backup cannot undo every kind of damage.\n\n"
    "The owner of this software (Adnan.120hz) is NOT responsible for "
    "any damage, bootloop, or data loss caused by using it on iOS 27.\n\n"
    "Your device backup must NOT be encrypted for this route "
    "(Finder/iTunes: uncheck 'Encrypt local backup'), otherwise the "
    "apply is refused before anything is written.\n\n"
    "Press Resume ONLY if you have a backup and accept the full risk. "
    "Press Abort to stop now — nothing will be written."
)


# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------

class G1WatchdogExpired(NuggetException):
    """Raised when the iOS 27 route stalls (no progress for the stall limit)."""


class G1Watchdog:
    """Stall-based watchdog for the iOS 27 G1 route.

    ``note_progress()`` is called on every progress tick and at every
    phase boundary; ``check()`` raises :class:`G1WatchdogExpired` only
    when nothing has moved for ``stall_seconds``. A device that keeps
    reporting progress is never interrupted — there is no wall-clock
    deadline (user order 2026-10-11).
    """

    def __init__(self, stall_seconds: float = WATCHDOG_STALL_SECONDS):
        self.stall_seconds = float(stall_seconds)
        self.started_at = time.monotonic()
        self.last_progress_at = self.started_at

    def note_progress(self) -> None:
        """Record activity: a progress tick or entering a new phase."""
        self.last_progress_at = time.monotonic()

    def stalled_for(self) -> float:
        """Seconds since the last recorded progress."""
        return time.monotonic() - self.last_progress_at

    def check(self, phase: str = "") -> None:
        stalled = self.stalled_for()
        if stalled > self.stall_seconds:
            minutes = max(1, int(stalled // 60))
            base = QCoreApplication.translate(
                "Nugget",
                "iOS 27 apply timed out: no progress for %1 minute(s) — "
                "the device stopped responding. The operation was stopped "
                "before any further step could start. If the backup had "
                "already finished it is kept on this computer; your "
                "device was not left half-written.").replace(
                    "%1", str(minutes))
            if phase:
                # phase name is developer-facing; appended outside the
                # translatable string (no f-string inside translate).
                base += " [phase: " + str(phase) + "]"
            raise G1WatchdogExpired(base)


# ---------------------------------------------------------------------------
# Payload planning (pure core + optional backup-merge I/O, unit-tested)
# ---------------------------------------------------------------------------

_FILE_MODE = 0o100644  # S_IFREG | 0644, as the LGD injection batch uses


def _coerce_bytes(contents) -> bytes:
    if isinstance(contents, str):
        return contents.encode("utf-8")
    if contents is None:
        return b""
    if isinstance(contents, bool) or isinstance(contents, int):
        # A staging bug passing an int/bool must fail LOUDLY — the old
        # code silently produced null bytes (bytes(5) == b'\x00'*5),
        # which would have shipped a zero-filled file to the device.
        raise TypeError(
            f"payload contents must be str/bytes/None, not {type(contents).__name__}")
    return bytes(contents)


def _try_parse_plist_dict(data: bytes):
    """Parse ``data`` as a plist; return the dict, or None."""
    try:
        import plistlib as _plistlib
        parsed = _plistlib.loads(bytes(data))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _deep_merge_dict(base: dict, staged: dict) -> dict:
    """Recursively merge ``staged`` onto ``base`` (staged wins on scalars).

    Unlike ``dict.update``, nested dicts are merged key-by-key: a tweak
    staging ``{"A": {"x": 1}}`` never drops the backup's (or another
    tweak's) existing ``{"A": {"y": 2}}``. Neither input is mutated.
    """
    out = dict(base)
    for key, value in staged.items():
        if (key in out and isinstance(out[key], dict)
                and isinstance(value, dict)):
            out[key] = _deep_merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def _preserve_backup_original(backup_root, domain: str, rel_path: str,
                              src_path) -> "Path | None":
    """Copy the backup's original file to a ``.bak`` next to the backup root.

    Called before a merge-or-replace decision: if the plist merge below
    fails, the staged file REPLACES the backup's copy wholesale at
    inject time, so the original is preserved first and the path is
    logged — never silently clobbered. Returns the ``.bak`` path, or
    None when preservation itself failed.
    """
    import shutil as _shutil
    try:
        bak_dir = Path(backup_root).parent / "g1-merge-fallback-bak"
        bak_dir.mkdir(parents=True, exist_ok=True)
        stem = "".join(
            c for c in f"{domain}__{rel_path}".replace("/", "__")
            if c.isalnum() or c in "._-")[:120] or "payload"
        bak_path = bak_dir / f"{time.strftime('%Y%m%d-%H%M%S')}_{stem}.bak"
        _shutil.copy2(src_path, bak_path)
        log_info(f"iOS27-G1: preserved the backup's original "
                 f"{domain}/{rel_path} at {bak_path}")
        return bak_path
    except Exception as e:
        log_warn(f"iOS27-G1: could not preserve a .bak of the backup's "
                 f"{domain}/{rel_path} ({type(e).__name__}: {e})")
        return None


def _merge_staged_onto_backup_plist(contents: bytes, domain: str,
                                    rel_path: str, backup_merge) -> tuple:
    """Merge staged plist bytes onto the backup's own copy (deep merge).

    ``backup_merge`` is ``(backup_root, udid, extract_fn)`` or None.
    Returns ``(new_contents, merged)``.

    The backup's original is preserved as a ``.bak`` BEFORE any
    merge/replace decision (see :func:`_preserve_backup_original`): on a
    merge failure the staged file is kept as-is and will REPLACE the
    backup's copy at inject time — destructive, so it is logged LOUDLY
    with the .bak path instead of happening silently.
    """
    import plistlib as _plistlib
    import tempfile as _tempfile

    staged_dict = _try_parse_plist_dict(contents)
    if staged_dict is None or backup_merge is None:
        return contents, False
    backup_root, udid, extract_fn = backup_merge
    try:
        with _tempfile.TemporaryDirectory(
                prefix="workslop_ios27_g1_merge_") as tmp:
            dest = os.path.join(tmp, "base.plist")
            pulled = extract_fn(backup_root, udid, domain, rel_path, dest)
            if not (pulled and os.path.exists(pulled)):
                # File absent from the backup: inject the staged file
                # new, byte-identical. Nothing to preserve.
                return contents, False
            _preserve_backup_original(backup_root, domain, rel_path, pulled)
            with open(pulled, "rb") as fh:
                existing = _try_parse_plist_dict(fh.read())
            if not isinstance(existing, dict):
                log_warn(
                    f"iOS27-G1: WARNING — the backup's {domain}/{rel_path} "
                    f"is not a plist dict, so the staged file will REPLACE "
                    f"it wholesale at inject time (original preserved as "
                    f".bak next to the backup).")
                return contents, False
            final = _deep_merge_dict(existing, staged_dict)
            log_info(
                f"iOS27-G1: merged {len(staged_dict)} staged key(s) "
                f"onto the backup's {domain}/{rel_path} "
                f"({len(existing)} existing top-level key(s) kept)")
            return _plistlib.dumps(final, fmt=_plistlib.FMT_BINARY,
                                   sort_keys=True), True
    except Exception as e:
        log_warn(
            f"iOS27-G1: WARNING — merge FAILED for {domain}/{rel_path} "
            f"({type(e).__name__}: {e}); the staged file will REPLACE the "
            f"backup's copy wholesale at inject time (the original was "
            f"preserved as .bak next to the backup).")
        return contents, False


def plan_g1_payloads(files_to_restore, backup_root=None, udid=None):
    """Build the G1 injection payload from the staged FileToRestore list.

    Every enabled tweak already contributed its target files to
    ``files_to_restore`` via the normal tweak pass — this function only
    translates them into ``(domain, rel_path, bytes, mode, owner,
    group)`` injection tuples and records a per-file audit manifest.
    Files that cannot ride a backup manifest are SKIPPED with an audit
    note, never silently dropped:

    * empty domain → skip + warn (cannot be injected into a manifest);
    * directory-only records → skip;
    * empty ``rel_path`` → skip + warn (downstream inject behavior for
      an empty path is undefined);
    * ``..`` segments in ``rel_path`` → skip + warn (path traversal);
    * empty contents → skip + warn (a zero-byte payload must never be
      planned — the codebase treats zero-byte files as dangerous);
    * leading slashes are stripped from ``rel_path`` so entries like
      ``/FeatureFlags/Placeholder`` do not become malformed manifest
      rows that the restore agent silently skips.

    Duplicate targets are resolved here, not downstream: when two
    tweaks stage the same ``(domain, rel_path)``, their plist dicts are
    deep-merged (staged keys win); non-plist duplicates cannot merge,
    so last-wins with a LOUD warning (the earlier payload is dropped).

    When ``backup_root``/``udid`` are given, each plist-dict payload is
    merged onto the file already in the backup ("pulled from the
    backup and modified"): pre-existing keys the user (or a previous
    apply) put there are never dropped by a whole-file replace — the
    merge is recursive (nested dicts merge key-by-key), and the staged
    tweak keys win for their own keys. Files absent from the backup,
    or payloads that are not plist dicts, are injected as new files,
    byte-identical to what staging produced.

    NOTE: the planning core is pure, but the optional merge step reads
    files from the backup on disk — it is NOT pure when
    ``backup_root``/``udid`` are given.

    Returns ``(payloads, skipped, manifest)`` where ``manifest`` is a
    list of ``{"domain", "rel_path", "size", "owner", "group",
    "contents_kind", "merged"}`` dicts in the same order as
    ``payloads``.
    """
    import plistlib as _plistlib

    payloads = []
    skipped = []
    manifest = []
    # (backup_root, udid, extract_fn): the source the merge step pulls
    # the backup's own copy from. None = inject staged files as-is.
    backup_merge_source = None
    if backup_root is not None and udid is not None:
        from src.restore.protective import extract_backup_file
        backup_merge_source = (backup_root, udid, extract_backup_file)

    # ---- Stage 1: normalize + validate ---------------------------------
    staged = []
    for f in files_to_restore or []:
        domain = (getattr(f, "domain", "") or "").strip()
        # M17: strip leading slashes so "/FeatureFlags/Placeholder" does
        # not become a malformed manifest row the restore agent skips.
        rel_path = (getattr(f, "restore_path", "") or "").lstrip("/")
        if not domain:
            skipped.append({
                "rel_path": rel_path,
                "reason": "empty domain — cannot be injected into a backup manifest",
            })
            log_warn(f"iOS27-G1: skipping file with empty domain: {rel_path!r}")
            continue
        if not rel_path:
            skipped.append({
                "rel_path": rel_path,
                "reason": "empty relative path — downstream inject behavior undefined",
            })
            log_warn(f"iOS27-G1: skipping file with empty relative path "
                     f"(domain {domain!r})")
            continue
        if ".." in rel_path.split("/"):
            skipped.append({
                "rel_path": rel_path,
                "reason": "'..' segment in path — rejected as path traversal",
            })
            log_warn(f"iOS27-G1: skipping file with '..' segment in path: "
                     f"{domain}/{rel_path!r}")
            continue
        if getattr(f, "is_dir", False):
            skipped.append({
                "rel_path": rel_path,
                "reason": "directory-only record — not a file payload",
            })
            continue
        contents = _coerce_bytes(getattr(f, "contents", b""))
        if len(contents) == 0:
            skipped.append({
                "rel_path": rel_path,
                "reason": "empty contents — zero-byte payloads are never planned",
            })
            log_warn(f"iOS27-G1: skipping zero-byte payload: "
                     f"{domain}/{rel_path!r}")
            continue
        mode = getattr(f, "mode", None) or _FILE_MODE
        # M1: explicit `is None` check — owner=0/group=0 (root, used by
        # the Daemons tweak) must survive; the old `or 501` coerced 0
        # to 501 silently.
        o = getattr(f, "owner", None)
        owner = _FILE_OWNER_MOBILE if o is None else int(o)
        g = getattr(f, "group", None)
        group = _FILE_OWNER_MOBILE if g is None else int(g)
        staged.append({
            "domain": domain, "rel_path": rel_path, "contents": contents,
            "mode": mode, "owner": owner, "group": group,
        })

    # ---- Stage 2: dedup by (domain, rel_path) ---------------------------
    by_target = {}
    unique = []
    for entry in staged:
        key = (entry["domain"], entry["rel_path"])
        if key not in by_target:
            by_target[key] = len(unique)
            unique.append(entry)
            continue
        prev = unique[by_target[key]]
        prev_dict = _try_parse_plist_dict(prev["contents"])
        cur_dict = _try_parse_plist_dict(entry["contents"])
        if prev_dict is not None and cur_dict is not None:
            merged = _deep_merge_dict(prev_dict, cur_dict)
            prev["contents"] = _plistlib.dumps(
                merged, fmt=_plistlib.FMT_BINARY, sort_keys=True)
            log_info(f"iOS27-G1: two tweaks staged {key[0]}/{key[1]} — "
                     f"plist keys deep-merged (later staged keys win)")
        else:
            unique[by_target[key]] = entry
            log_warn(f"iOS27-G1: WARNING — duplicate target {key[0]}/{key[1]} "
                     f"staged twice and the payloads are not both plist "
                     f"dicts, so they cannot be merged: LAST ONE WINS, the "
                     f"earlier payload is DROPPED.")

    # ---- Stage 3: merge onto the backup's own copy ----------------------
    for entry in unique:
        domain = entry["domain"]
        rel_path = entry["rel_path"]
        contents, merged = _merge_staged_onto_backup_plist(
            entry["contents"], domain, rel_path, backup_merge_source)
        payloads.append((domain, rel_path, contents, entry["mode"],
                         entry["owner"], entry["group"]))
        manifest.append({
            "domain": domain,
            "rel_path": rel_path,
            "size": len(contents),
            "owner": entry["owner"],
            "group": entry["group"],
            "contents_kind": "plist" if contents.lstrip().startswith(b"bplist")
                             or contents.lstrip().startswith(b"<?xml") else "binary",
            "merged": merged,
        })
    return payloads, skipped, manifest


def attribute_payloads_to_tweaks(payloads, journal_entries):
    """Attribute each payload file to the tweaks that staged it.

    The join key is the registry spec ``location`` (the full device
    path, e.g. ``/var/Managed Preferences/mobile/com.apple.UIKit.plist``)
    found on Apply Journal entries, mapped to ``(domain, rel_path)``
    with the same ``split_path_into_domain`` the staging used. Payloads
    with no matching entry are attributed to ``"<staging>"`` (PosterBoard,
    skip-setup, status-bar, passcode and other non-registry families)
    rather than invented.

    The ``attribution`` field distinguishes the two meanings of
    ``"<staging>"``: ``"registry"`` (exact journal match),
    ``"staging-non-registry"`` (no journal entry for that domain at
    all — genuinely a non-registry family), and
    ``"staging-join-failed"`` (a journal entry exists for the same
    domain but the exact join failed — e.g. path-normalization drift —
    which is logged as a warning because it may hide a real tweak).

    TODO (honest): the attribution is log-only. It is NOT persisted to
    the Apply Journal — this module has no handle on the journal object
    (device_manager.py owns it), so there is no write path here to
    invent. Persisting it would require threading the journal in from
    the caller.

    ``journal_entries``: iterable of dicts with ``tweak_id`` and
    ``operation`` (``{"location": <path>, ...}``). Returns a list of
    ``{"domain", "rel_path", "tweaks": [tweak_id, ...], "attribution":
    ...}`` in payload order.
    """
    from src.restore.path_mapping import split_path_into_domain

    location_to_tweaks = {}
    for entry in journal_entries or []:
        op = (entry or {}).get("operation") or {}
        loc = op.get("location")
        tid = (entry or {}).get("tweak_id") or (entry or {}).get("id") or "?"
        if not loc:
            continue
        try:
            domain, rel = split_path_into_domain(str(loc))
        except Exception as e:
            log_warn(f"iOS27-G1: attribution skipped for journal entry "
                     f"{tid!r}: cannot map location {loc!r} to a backup "
                     f"domain ({type(e).__name__}: {e})")
            continue
        if not domain:
            continue
        key = (domain, rel)
        location_to_tweaks.setdefault(key, [])
        if tid not in location_to_tweaks[key]:
            location_to_tweaks[key].append(tid)

    journal_domains = {key[0] for key in location_to_tweaks}

    attributed = []
    for p in payloads:
        domain, rel_path = p[0], p[1]
        tweaks = location_to_tweaks.get((domain, rel_path))
        if tweaks is not None:
            attribution = "registry"
        elif domain in journal_domains:
            # A registry tweak staged this domain, but the exact join
            # failed — the tweak that owns this file is being hidden
            # behind "<staging>". Say so loudly.
            tweaks = ["<staging>"]
            attribution = "staging-join-failed"
            log_warn(f"iOS27-G1: payload {domain}/{rel_path} has a journal "
                     f"entry for domain {domain!r} but no exact (domain, "
                     f"path) match — attributed as <staging> although a "
                     f"registry tweak may own it (check restore_path "
                     f"normalization).")
        else:
            tweaks = ["<staging>"]
            attribution = "staging-non-registry"
        attributed.append({
            "domain": domain,
            "rel_path": rel_path,
            "tweaks": list(tweaks),
            "attribution": attribution,
        })
    return attributed


# ---------------------------------------------------------------------------
# Backup pool (dedicated; never the iOS 27 protective-backup pool)
# ---------------------------------------------------------------------------

def ios27_g1_backup_base(udid: str) -> Path:
    from src.restore.protective import protective_persistent_base
    safe = sanitize_udid(str(udid or "unknown"))
    return protective_persistent_base() / f"{safe}-ios27-g1"


def new_ios27_g1_backup_dir(udid: str) -> str:
    """Fresh backup root: <pool>/<ts>-<pid>-<rand>/device_backup."""
    import uuid as _uuid
    base = ios27_g1_backup_base(udid)
    for _ in range(8):
        # [:8] = the first 8 hex chars of a fresh UUID: enough randomness
        # that two runs started in the same second never collide.
        run_dir = (base
                   / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{_uuid.uuid4().hex[:8]}")
        backup_root = run_dir / "device_backup"
        # No exist_ok: a name collision must be detected and retried,
        # never silently reused.
        try:
            backup_root.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            log_warn("iOS27-G1: backup run-dir name collision, retrying "
                     "with a fresh name")
            continue
        return str(backup_root)
    raise NuggetException(
        "iOS 27 apply: could not create a fresh backup directory "
        "(repeated name collisions). Nothing was written.")


def _is_usable_backup(run_dir: Path, udid: str) -> bool:
    """Fail-closed check: does this pool run hold a usable backup?

    "Manifest.db exists" is NOT enough — an interrupted backup (cable
    pulled, watchdog abort, disk full) leaves a Manifest.db behind that
    is empty or corrupt, and the old exists-check let prune() delete the
    last GOOD backup while keeping the corrupt one. A run is usable only
    if Manifest.db opens as a valid SQLite database AND its Files table
    holds at least one row. Anything less is incomplete.

    (Refused encrypted backups never reach the pool at all — they are
    removed outright in :func:`backup_ios27_full`, so they cannot occupy
    a keep slot.)
    """
    safe_udid = sanitize_udid(str(udid or "unknown"))
    for candidate in (run_dir / "device_backup" / safe_udid,
                      run_dir / "device_backup"):
        manifest_db = candidate / "Manifest.db"
        if not manifest_db.is_file():
            continue
        try:
            conn = sqlite3.connect(str(manifest_db))
        except Exception:
            continue
        try:
            count = conn.execute("SELECT COUNT(*) FROM Files").fetchone()
        except Exception:
            # Missing/corrupt Files table: not a usable backup.
            continue
        finally:
            conn.close()
        if count and count[0] and count[0] > 0:
            return True
    return False


def prune_ios27_g1_backups(udid: str, keep: int = 2) -> int:
    """Keep only the newest ``keep`` usable runs; drop stale ones.

    A run counts as usable only under :func:`_is_usable_backup`
    (fail-closed). Non-directory cruft in the pool is removed too, and
    every prune failure is logged — never silent.
    """
    import shutil
    base = ios27_g1_backup_base(udid)
    if not base.is_dir():
        return 0
    now = time.time()
    removed = 0

    def _rmtree_logged(path: Path) -> bool:
        try:
            shutil.rmtree(path)
        except Exception as e:
            log_warn(f"iOS27-G1: failed to remove old backup dir {path} "
                     f"({type(e).__name__}: {e}); leaving it in place")
            return False
        return not path.exists()

    # Non-directory cruft (stray files, partial writes) never belongs
    # in the pool: remove it, loudly on failure.
    for entry in list(base.iterdir()):
        if entry.is_dir():
            continue
        try:
            entry.unlink()
            removed += 1
        except OSError as e:
            log_warn(f"iOS27-G1: failed to remove stray pool file {entry} "
                     f"({e}); leaving it in place")

    entries = [e for e in base.iterdir() if e.is_dir()]

    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    runs = [e for e in entries if _is_usable_backup(e, udid)]
    runs.sort(key=_mtime, reverse=True)
    for old in runs[max(keep, 0):]:
        if _rmtree_logged(old):
            removed += 1
    for stale in (e for e in entries if e not in runs):
        try:
            age = now - stale.stat().st_mtime
        except OSError:
            log_warn(f"iOS27-G1: cannot stat {stale}; leaving it in place")
            continue
        if age > 7 * 24 * 3600:  # incomplete/failed runs: reclaimed after a week
            if _rmtree_logged(stale):
                removed += 1
    return removed


def _redacted_backup_root(backup_root, udid) -> str:
    """Backup root with the UDID redacted for logs (privacy).

    Full 40-char UDIDs are never written verbatim to the session log —
    only the first 8 chars plus "...".
    """
    safe = sanitize_udid(str(udid or "unknown"))
    redacted = (safe[:8] + "...") if safe else "unknown..."
    return str(backup_root).replace(safe, redacted)


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------

def _device_dir_for(backup_root, udid) -> Path:
    # Thin alias over the shared helper (audit M14): the G1 and LGD
    # routes resolve the device folder identically.
    return device_dir_for(backup_root, udid)


async def wait_for_ios27_device_online(udid: str, timeout_seconds: float = 300,
                                       poll_seconds: float = 5) -> bool:
    """Wait until the device answers lockdown again (post-reboot check).

    Opens a fresh ``lockdown_session`` on every poll — the pre-reboot
    session is dead by definition, so it is never reused. Returns True
    as soon as a session opens, False when the timeout expires. A False
    does NOT mean the device is bricked, only that it has not come back
    on the wire yet (e.g. still booting, or stuck on the Apple logo).
    """
    from src.devicemanagement.session import lockdown_session
    log_info(f"iOS27-G1: waiting up to {timeout_seconds / 60:.0f} minute(s) "
             f"for the device to come back online after reboot "
             f"(UDID {str(udid)[:8]}...)...")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            async with lockdown_session(udid):
                log_info("iOS27-G1: device is back online after reboot")
                return True
        except Exception:
            # Not back yet (or trust dialog pending) — keep polling.
            await asyncio.sleep(poll_seconds)
    log_warn("iOS27-G1: device did NOT come back online within "
             f"{timeout_seconds / 60:.0f} minute(s) after reboot — check the "
             f"device; it may still be booting or stuck on the Apple logo. "
             f"The full backup is kept on this computer.")
    return False


async def backup_ios27_full(udid: str, *,
                            update_label=lambda x: None,
                            backup_progress=lambda x: None,
                            watchdog: "G1Watchdog" = None) -> str:
    """Phase A: full backup of ALL device data to this computer.

    The stall watchdog starts here (it is created if not given).
    Encrypted backups are refused honestly. A backup that fails for
    ANY reason has its partial directory removed right here (it must
    never linger as a pool entry), so only completed backups ever sit
    in the pool. Returns the backup root.
    """
    from src.devicemanagement.session import lockdown_session
    from src.restore.inject import _is_encrypted_backup
    from src.restore.protective import check_disk_space_for_backup
    from src.restore.restore import _start_mobilebackup2
    from src.utils.stall_watchdog import run_with_stall_watchdog

    if watchdog is None:
        watchdog = G1Watchdog()
    # keep=1: the previous run's backup is the anti-bootloop safety net;
    # older runs are dropped to bound disk use (fail-closed _is_usable_backup
    # decides which runs are actually keepable).
    prune_ios27_g1_backups(udid, keep=1)
    backup_root = new_ios27_g1_backup_dir(udid)
    redacted_root = _redacted_backup_root(backup_root, udid)
    log_info(f"iOS27-G1: backup root {redacted_root} "
             f"(stall watchdog: fires after {watchdog.stall_seconds / 60:.0f} "
             f"min with no progress)")

    try:
        update_label(QCoreApplication.translate(
            "Nugget",
            "iOS 27: starting FULL backup of your device (all data)...\n"
            "Do not unplug your device."))
        watchdog.check("backup")
        watchdog.note_progress()

        def _backup_cb(value):
            # Every progress tick proves the device is alive, so the stall
            # watchdog never fires on a healthy (even very long) backup.
            # A truly stuck device is caught by the inner 300s stall
            # watchdog wrapping mb.backup() below.
            watchdog.note_progress()
            backup_progress(value)

        async with lockdown_session(udid) as lc:
            await check_disk_space_for_backup(lc, path=backup_root)
            async with _start_mobilebackup2(lc) as mb:
                try:
                    will_encrypt = await mb.get_will_encrypt()
                except Exception:
                    will_encrypt = False
                if will_encrypt:
                    raise NuggetException(QCoreApplication.translate(
                        "Nugget",
                        "iOS 27 apply: your device backup is encrypted, and "
                        "this route cannot write into an encrypted backup "
                        "safely. Turn off backup encryption (Finder/iTunes: "
                        "uncheck 'Encrypt local backup'), then try again. "
                        "Nothing was written; your device was not changed."))
                await run_with_stall_watchdog(
                    lambda tracking_cb: mb.backup(
                        full=True, backup_directory=backup_root,
                        progress_callback=tracking_cb),
                    _backup_cb,
                    operation="backup",
                )
        device_dir = _device_dir_for(backup_root, udid)
        if not (device_dir / "Manifest.db").is_file():
            raise NuggetException(QCoreApplication.translate(
                "Nugget",
                "iOS 27 apply: the full backup did not produce a usable "
                "backup, so nothing was restored. Your device was not "
                "changed."))
        if _is_encrypted_backup(device_dir):
            raise NuggetException(QCoreApplication.translate(
                "Nugget",
                "iOS 27 apply: the backup came back encrypted, so the "
                "payload cannot be written into it safely. Nothing was "
                "restored; your device was not changed."))
        return backup_root
    except Exception:
        # A failed backup must not linger as a pool entry (and must not
        # hold tens of GB): remove the partial directory right here.
        # The fail-closed _is_usable_backup would classify it as
        # incomplete anyway — this is belt-and-braces plus disk hygiene.
        import shutil as _shutil
        _shutil.rmtree(backup_root, ignore_errors=True)
        log_warn(f"iOS27-G1: removed the partial backup at {redacted_root} "
                 f"after a failed backup")
        raise


# ---------------------------------------------------------------------------
# G1 full restore — method BARU 100% untuk iOS 27 (bukan GoldenNugget).
#
# Alur: backup full -> payload per tweak aktif -> inject -> verifikasi ->
#       RESTORE FULL via mobilebackup2 -> reboot + notifikasi.
# Tidak ada fase sparse-restore, tidak ada wipe selektif, tidak ada
# protective-backup filtering. Restore memakai mobilebackup2 langsung
# dengan stall watchdog + retry untuk error koneksi transient.
# ---------------------------------------------------------------------------

async def _restore_g1_full(lc, backup_root: str, udid: str,
                           progress_callback=lambda x: None) -> None:
    """Full restore backup G1 ke device via mobilebackup2.

    Method baru khusus iOS 27 G1 — tidak memakai kode restore lama
    GoldenNugget. Stall watchdog membatalkan attempt yang macet
    (device diam terlalu lama); retry hanya untuk error koneksi
    transient dengan sesi lockdown fresh tiap percobaan ulang.
    """
    import asyncio
    import time as _time
    from pymobiledevice3.exceptions import ConnectionTerminatedError
    from src.exceptions.device_errors import is_transient_restore_error
    from src.restore.restore import _start_mobilebackup2
    from src.utils.async_retry import async_retry

    max_retries = 18
    stall_seconds = 300.0
    try:
        import os as _os
        stall_seconds = float(
            _os.environ.get("WORKSLOP_G1_RESTORE_STALL_SECONDS", "300") or 300)
        if stall_seconds <= 0:
            stall_seconds = 300.0
    except Exception:
        stall_seconds = 300.0

    _watch = {"last_progress_at": None, "last_cb": None}
    _attempt = {"n": 0}

    async def _restore_once():
        import contextlib as _cl
        _attempt["n"] += 1
        _watch["last_progress_at"] = _time.monotonic()
        _watch["last_cb"] = None

        def _tracking_callback(cb_arg):
            _watch["last_progress_at"] = _time.monotonic()
            _watch["last_cb"] = cb_arg
            progress_callback(cb_arg)

        async def _do_restore():
            if _attempt["n"] <= 1:
                session_cm = _cl.nullcontext(lc)
            else:
                from src.devicemanagement.session import lockdown_session
                session_cm = lockdown_session(udid)
            async with session_cm as attempt_lc:
                async with _start_mobilebackup2(attempt_lc) as mb:
                    await mb.restore(
                        backup_root,
                        system=True, copy=True, remove=False,
                        reboot=False, source=udid,
                        skip_apps=True,
                        progress_callback=_tracking_callback,
                    )

        task = asyncio.ensure_future(_do_restore())
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=20)
                if task.done():
                    break
                silent = _time.monotonic() - (
                    _watch["last_progress_at"] or _time.monotonic())
                if silent >= stall_seconds:
                    task.cancel()
                    log_warn(f"iOS27-G1: restore stall {silent:.0f}s tanpa "
                             f"progress (batas {stall_seconds:.0f}s) — "
                             f"coba ulang dengan koneksi fresh")
                    raise ConnectionTerminatedError(
                        "Device berhenti melaporkan progress restore; "
                        "mencoba ulang dengan koneksi fresh.")
                if _watch["last_cb"] is not None:
                    progress_callback(_watch["last_cb"])
                log_info(f"iOS27-G1: restore heartbeat — device diam "
                         f"{silent:.0f}s (batas {stall_seconds:.0f}s)")
        except asyncio.CancelledError:
            task.cancel()
            raise
        return await task

    def _on_retry(attempt: int, total: int, e: Exception, delay: float) -> None:
        progress_callback(
            f"Device belum siap, mencoba ulang ({attempt}/{max_retries})...")

    def _on_failure(e: Exception) -> None:
        if type(e).__name__ == "NotEnoughDiskSpaceError":
            raise e
        if not is_transient_restore_error(e):
            raise e

    await async_retry(
        _restore_once,
        max_retries=max_retries,
        should_retry=is_transient_restore_error,
        on_retry=_on_retry,
        on_failure=_on_failure,
    )


async def deliver_ios27_payload(backup_root: str, udid: str, payloads: list, *,
                                update_label=lambda x: None,
                                restore_progress=lambda x: None,
                                watchdog: "G1Watchdog" = None,
                                reboot: bool = False) -> tuple:
    """Phases B-D: verify backup, inject payload, verify, full restore.

    ``payloads``: list of ``(domain, rel_path, bytes, mode, owner,
    group)`` from :func:`plan_g1_payloads`. Nothing is written to the
    device before the final restore.

    Returns ``(backup_root, boot_verified)`` where ``boot_verified`` is
    True when the device came back online after the requested reboot,
    False when the reboot was requested but the device did not come
    back within the wait window, and None when no reboot was
    requested.

    The stall watchdog gates STARTING the restore (a quiet route is
    stopped before the point of no return); a restore already in
    flight is never interrupted (cutting it mid-flight is the unsafe
    action).

    Reboot note: ``DiagnosticsService.restart()`` routinely drops the
    connection mid-command — that ``ConnectionTerminatedError`` is
    EXPECTED and is not treated as a failure (the reboot was still
    sent). After a requested reboot the route waits for the device to
    come back online (see :func:`wait_for_ios27_device_online`); a
    device that stays dark is reported honestly instead of letting a
    "Success" alert land on a bootlooped phone.
    """
    from src.devicemanagement.session import lockdown_session
    from src.restore.inject import inject_files_into_backup
    from src.restore.protective import verify_backup_payloads

    if watchdog is None:
        watchdog = G1Watchdog()

    if not payloads:
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply: there is nothing to deliver (no tweak files "
            "were staged). Nothing was written."))

    # ---- Phase B/C: verify backup complete, then inject the payload ----
    # check() first: the previous phase must not have stalled; then
    # note_progress(): entering a new phase counts as activity.
    watchdog.check("payload injection")
    watchdog.note_progress()
    update_label(QCoreApplication.translate(
        "Nugget",
        "iOS 27: verifying the backup, then writing the payload into "
        "the backup on this computer (your device is not touched yet)..."))
    missing = verify_backup_payloads(backup_root, udid)
    if missing:
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply: the full backup is incomplete (%1 manifest "
            "file(s) have no data), so nothing was restored. Your "
            "device was not changed. The incomplete backup is kept on "
            "this computer for inspection.").replace("%1", str(len(missing))))

    injected, unchanged, failed = await asyncio.to_thread(
        inject_files_into_backup, backup_root, udid, payloads)
    if not inject_accounting_ok(injected, unchanged, failed, len(payloads)):
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply: the payload could not be written into the "
            "backup (%1 of %2 file(s) failed), so nothing was restored. "
            "Your device was not changed.").replace("%1", str(failed)).replace(
                "%2", str(len(payloads))))

    # Re-read the injected files from disk and confirm every payload
    # landed byte-identical (plus its Manifest.db row) before the
    # restore is allowed to start.
    watchdog.check("payload verification")
    watchdog.note_progress()
    problems = _verify_injected_files(backup_root, udid, payloads)
    if problems:
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply: the verification gate failed, so nothing was "
            "restored and your device was not changed:\n")
            + "\n".join(f"\u2022 {p}" for p in problems))

    # ---- Phase D: full restore -----------------------------------------
    try:
        watchdog.check("restore")
    except G1WatchdogExpired:
        raise G1WatchdogExpired(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply timed out: the route stalled with no progress "
            "after the payload was written into the backup but before "
            "the restore started. NOTHING was written to your device. "
            "The complete backup (with your tweaks staged inside) "
            "is kept at:\n%1").replace(
                "%1", _redacted_backup_root(backup_root, udid)))
    watchdog.note_progress()
    update_label(QCoreApplication.translate(
        "Nugget", "iOS 27: restoring the full backup to your device...\n"
        "Do not unplug your device."))

    def _restore_cb(value):
        # Heartbeat only: every tick proves the device is alive, and
        # the restore is never cancelled by the watchdog (see module
        # docstring).
        watchdog.note_progress()
        restore_progress(value)

    async with lockdown_session(udid) as lc:
        await _restore_g1_full(
            lc, backup_root, udid, progress_callback=_restore_cb)
        if reboot:
            from pymobiledevice3.exceptions import ConnectionTerminatedError
            from src.restore import reboot_device
            try:
                await reboot_device(True, lc)
            except ConnectionTerminatedError:
                # Expected: restart() routinely drops the connection
                # mid-command. The reboot was still sent; this is not
                # a failure.
                log_warn("iOS27-G1: reboot command dropped the connection "
                         "(expected — the restart was still sent); waiting "
                         "for the device to come back online...")

    # The pre-reboot session is dead by definition: verify the device
    # came back with a FRESH session, outside the old context.
    boot_verified = None
    if reboot:
        boot_verified = await wait_for_ios27_device_online(udid)

    return backup_root, boot_verified


def _verify_injected_files(backup_root, udid, payloads) -> list:
    """Re-read every payload from the backup and confirm it is deliverable.

    Checks, per payload:

    1. the payload blob exists on disk (Apple backup layout:
       ``<aa>/<fileID>``, where ``<aa>`` is the first two hex chars of
       the SHA1 file ID — ``file_id[:2]``);
    2. its bytes are identical to the planned payload;
    3. its ``Manifest.db`` row (``domain``, ``relativePath``, ``flags``)
       matches the planned target — a byte-identical blob with a
       malformed manifest row is skipped outright by the restore agent,
       so the row is verified too.

    Returns a list of problem strings (empty = all good).
    """
    problems = []
    device_dir = _device_dir_for(backup_root, udid)

    # Read the manifest rows once, read-only (plain connect: we only
    # SELECT, never write).
    rows = None
    manifest_db = device_dir / "Manifest.db"
    if not manifest_db.is_file():
        problems.append("Manifest.db is missing from the backup — "
                        "manifest rows cannot be verified")
    else:
        try:
            conn = sqlite3.connect(str(manifest_db))
            try:
                rows = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
                    "SELECT fileID, domain, relativePath, flags FROM Files")}
            finally:
                conn.close()
        except Exception as e:
            problems.append(f"Manifest.db unreadable for verification "
                            f"({type(e).__name__}: {e})")

    for domain, rel_path, data, _mode, _owner, _group in payloads:
        disk_path = payload_disk_path(backup_root, udid, domain, rel_path)
        file_id = backup_file_id(domain, rel_path)
        if not disk_path.is_file():
            problems.append(f"{domain}/{rel_path}: not found in backup after injection")
            continue
        try:
            on_disk = disk_path.read_bytes()
        except OSError as e:
            problems.append(f"{domain}/{rel_path}: unreadable after injection ({e})")
            continue
        if on_disk != bytes(data):
            problems.append(
                f"{domain}/{rel_path}: content mismatch after injection "
                f"(expected {len(data)} bytes, found {len(on_disk)})")
        if rows is not None:
            row = rows.get(file_id)
            if row is None:
                problems.append(f"{domain}/{rel_path}: no Manifest.db row "
                                f"for the injected file — the restore agent "
                                f"would skip it")
            else:
                row_domain, row_rel, row_flags = row
                if row_domain != domain or row_rel != rel_path:
                    problems.append(
                        f"{domain}/{rel_path}: Manifest.db row mismatch "
                        f"(row says {row_domain}/{row_rel}) — the restore "
                        f"agent would not deliver this file")
                if row_flags != 1:
                    problems.append(
                        f"{domain}/{rel_path}: Manifest.db flags={row_flags} "
                        f"(expected 1 for a regular file)")
    return problems
