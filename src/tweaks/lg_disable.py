"""Liquid Glass Disable (Beta 1) — payload core, verification gate, rollback store.

Beta 1 writes ONE candidate key, ``SolariumForceFallback`` = true, through
two delivery routes:

* **G2** — the managed overlay: ``FileLocation.globalPreferences``
  (``/var/Managed Preferences/mobile/.GlobalPreferences.plist``,
  ManagedPreferencesDomain). Small payload: just the key.
* **G1** — the device's own global preferences file:
  ``FileLocation.globalPreferencesHomeDomain``
  (``/var/mobile/Library/Preferences/.GlobalPreferences.plist``,
  HomeDomain). A restore of that path REPLACES the whole file, so the
  payload is built at apply time from the connected device's live file
  (parsed dict + our key inserted) and must pass a fail-hard diff gate:
  100% of the original keys intact, or the apply is cancelled.

Evidence grades (see ~/workspace/riset/lg-global-plist/):
* The key string ``SolariumForceFallback`` is attested in the iOS 26.6.1
  (build 23G83) DesignLibrary binary cluster next to
  ``GlassMaterialProvider``, and the same key/value/domain was already
  shipped by the frozen v4 Liquid Glass set (``TweakID.SolariumForceFallback``).
* Whether iOS 26.6.1 actually READS this key from either file is NOT
  proven — that is exactly why the feature is labelled Beta 1 / hypothesis
  in the UI and must be judged by an isolated device test. Nothing in this
  module claims the glass is disabled.

The payload/verify logic here is adapted from the offline payload-lab
(``~/workspace/riset/lg-global-plist/payload-lab/``: g1_payload.py,
g2_payload.py, restore_map.py, rollback.py, verify_gate.py — 14/14 tests
+ 11/11 gate checks green) to this repo's registry / apply-pass
architecture. Delivery has two channels: the default sparse-restore
records (the repo's existing restore machinery — the same machinery every
other ManagedPreferencesDomain / HomeDomain tweak already rides), and,
on iOS 26.6.x builds 23G82/23G83 only, a full-backup route
(``src/restore/lgd_full.py``) that injects these exact payloads into a
complete device backup and restores it. The ``build_*_payload`` helpers
below are the canonical payload constructors: the sparse path stages the
equivalent plist dicts through the generic BasicPlistTweak merge (and the
verification gate re-checks the final records), while the full-backup
route and the offline tests consume the builders directly. Whether
restored (23G83) accepts these records — by either channel — is NOT
device-proven yet; the uncertainty is inherent to the Beta 1 label, not
hidden.

This module stays free of the device stack (no pymobiledevice3): the
targeted backup that reads the live device file lives in
``src/restore/lgd_backup.py``.
"""

import hashlib
import json
import os
import plistlib
from typing import Optional

from PySide6.QtCore import QStandardPaths

from src.exceptions.nugget_exception import NuggetException
from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.tweak_classes import BasicPlistTweak

FEATURE_NAME = "Liquid Glass Disable (Beta 1)"

# The single Beta 1 candidate key. The value MUST stay a real bool: plist
# readers distinguish <true/> from the integer 1 and from the string
# "true", and the verification gate enforces the exact type.
GP_KEY = "SolariumForceFallback"
GP_KEY_VALUE = True

G2_LOCATION = FileLocation.globalPreferences
# Backup-domain mapping for the two locations, identical to what
# src.restore.path_mapping.split_path_into_domain returns for them (the
# offline test asserts the two never drift). Kept literal here because
# tweak modules must not import the src.restore package (it pulls in the
# device stack) — src/tweaks/lg_disable.py has to stay importable in the
# stub-based offline tests.
G2_DOMAIN = "ManagedPreferencesDomain"
G2_REL_PATH = "mobile/.GlobalPreferences.plist"

G1_LOCATION = FileLocation.globalPreferencesHomeDomain
G1_DOMAIN = "HomeDomain"
G1_REL_PATH = "Library/Preferences/.GlobalPreferences.plist"


# --- payload building (adapted from payload-lab g2_payload/g1_payload) ----

ALLOWED_VALUE_TYPES = (bool, int, float, str)


def validate_entries(entries, expected_types=None) -> list:
    """Return rejection reasons for candidate plist entries ([] = valid).

    ``expected_types``: optional {key: type} — the value's exact type must
    match, so a candidate declared bool rejects the string 'true'.
    """
    reasons = []
    if not isinstance(entries, dict):
        return ["entries must be a dict of key -> value"]
    expected_types = expected_types or {}
    for key, value in entries.items():
        if not isinstance(key, str) or not key:
            reasons.append(f"key {key!r}: keys must be non-empty str")
            continue
        if key in expected_types and type(value) is not expected_types[key]:
            reasons.append(
                f"key {key!r}: expected {expected_types[key].__name__}, "
                f"got {type(value).__name__} ({value!r})")
            continue
        if isinstance(value, ALLOWED_VALUE_TYPES):
            continue
        reasons.append(
            f"key {key!r}: value type {type(value).__name__} not allowed "
            "(bool/int/float/str — flat prefs only)")
    return reasons


def build_g2_payload(entries) -> bytes:
    """Build the G2 managed-overlay plist bytes. Raises ValueError."""
    expected = {GP_KEY: bool} if GP_KEY in entries else None
    reasons = validate_entries(entries, expected_types=expected)
    if reasons:
        raise ValueError("invalid G2 payload entries: " + "; ".join(reasons))
    return plistlib.dumps(dict(entries), fmt=plistlib.FMT_BINARY,
                          sort_keys=True)


def load_plist_dict(data) -> dict:
    """Parse plist bytes into a dict; raises ValueError otherwise."""
    result = plistlib.loads(bytes(data))
    if not isinstance(result, dict):
        raise ValueError("plist root is not a dict")
    return result


def insert_keys(original: dict, inserts: dict) -> dict:
    """Return ``original`` + ``inserts``. Raises ValueError on bad types."""
    reasons = validate_entries(inserts, expected_types={GP_KEY: bool}
                               if GP_KEY in inserts else None)
    if reasons:
        raise ValueError("invalid insert entries: " + "; ".join(reasons))
    merged = dict(original)
    merged.update(inserts)
    return merged


def build_g1_payload(original: dict, inserts: dict) -> bytes:
    """Build the G1 whole-file payload and self-check it against the gate.

    Raises ValueError when the built payload would lose or alter any
    original key — the same fail-hard rule the apply pass enforces on the
    final restore records.
    """
    merged = insert_keys(original, inserts)
    payload = plistlib.dumps(merged, fmt=plistlib.FMT_BINARY, sort_keys=True)
    problems = diff_gate(original, load_plist_dict(payload),
                         allowed_new=set(inserts))
    if problems:
        raise ValueError("diff gate failed on built payload: "
                         + "; ".join(problems))
    return payload


def diff_gate(original: dict, payload: dict, allowed_new=None,
              allowed_override=None) -> list:
    """Fail-hard diff of a candidate payload against the device original.

    Returns the list of violations ([] = clean):

    * every original key must still be present with an identical value AND
      type, unless the key is in ``allowed_override`` (keys another enabled
      tweak deliberately staged into the same file this pass);
    * no key may appear that is neither original nor in ``allowed_new``.
    """
    allowed_new = set(allowed_new or ())
    allowed_override = set(allowed_override or ())
    violations = []
    for key, value in original.items():
        if key not in payload:
            violations.append(f"original key LOST: {key!r}")
        elif key not in allowed_override:
            got = payload[key]
            if type(got) is not type(value) or got != value:
                violations.append(
                    f"original key CHANGED: {key!r}: {value!r} -> {got!r}")
    for key in payload:
        if key not in original and key not in allowed_new:
            violations.append(f"unexpected NEW key: {key!r}")
    return violations


# --- restore record verification (adapted from payload-lab restore_map) --

def content_hash(data: bytes) -> str:
    """SHA-1 hex of content bytes (the hash family MBDB manifests use)."""
    return hashlib.sha1(data).hexdigest()


def _record_bytes(file) -> bytes:
    data = getattr(file, "contents", None)
    if data is None:
        src = getattr(file, "contents_path", None)
        if src:
            try:
                with open(src, "rb") as fh:
                    data = fh.read()
            except OSError:
                data = None
    if data is None:
        return b""
    if isinstance(data, str):
        return data.encode("utf-8")
    return bytes(data)


def restore_records(files) -> list:
    """Structured restore map for a FileToRestore list (domain/path/hash).

    Same fields the payload-lab restore_map records; the MBDB byte layout
    itself is produced by the repo's restore engine, not by this map.
    """
    records = []
    for f in files:
        raw = _record_bytes(f)
        records.append({
            "domain": getattr(f, "domain", "") or "",
            "relative_path": (getattr(f, "restore_path", "") or "").lstrip("/"),
            "sha1": content_hash(raw),
            "size": len(raw),
        })
    return records


def _effective_plist(files, domain: str, rel_path: str):
    """Fold every record for (domain, rel_path) into one effective dict.

    Mirrors ``restore.merge_duplicates`` exactly: later duplicate records'
    dicts update the first record's dict. Returns
    ``(found, effective_dict_or_None, problems)``.
    """
    matched = [
        f for f in files
        if (getattr(f, "domain", "") or "") == domain
        and (getattr(f, "restore_path", "") or "").lstrip("/") == rel_path
    ]
    if not matched:
        return False, None, []
    problems = []
    effective = None
    empty_records = 0
    for f in matched:
        raw = _record_bytes(f)
        if not raw:
            # An empty duplicate record folds into nothing; it only becomes
            # a problem when NO record carries a real payload (the device
            # would receive an empty file).
            empty_records += 1
            continue
        try:
            parsed = plistlib.loads(raw)
        except Exception as exc:
            problems.append(
                f"{domain}/{rel_path}: payload does not parse: {exc}")
            continue
        if not isinstance(parsed, dict):
            problems.append(
                f"{domain}/{rel_path}: payload root is not a dict")
            continue
        if effective is None:
            effective = dict(parsed)
        else:
            effective.update(parsed)
    if effective is None and empty_records:
        problems.append(f"{domain}/{rel_path}: restore record is empty")
    return True, effective, problems


def _check_candidate_key(effective: dict, route: str) -> list:
    if GP_KEY not in effective:
        return [f"{route}: key {GP_KEY!r} is missing from the payload"]
    value = effective[GP_KEY]
    if type(value) is not bool:
        return [f"{route}: key {GP_KEY!r} must be a real bool, got "
                f"{type(value).__name__} ({value!r})"]
    if value is not GP_KEY_VALUE:
        return [f"{route}: key {GP_KEY!r} must be true, got {value!r}"]
    return []


def verify_apply_gate(files, *, g2_active: bool, g1_active: bool,
                      g1_base: Optional[dict] = None,
                      g1_allowed_new=()) -> list:
    """The Beta 1 verification gate, run on EVERY apply that stages us.

    ``files`` is the pass's final FileToRestore list (before restore).
    Returns a list of problems; empty = the apply may proceed. Checks:

    * G2 (when staged): a record exists for ManagedPreferencesDomain /
      mobile/.GlobalPreferences.plist, parses, and carries
      SolariumForceFallback as a real bool true.
    * G1 (when staged): a record exists for HomeDomain /
      Library/Preferences/.GlobalPreferences.plist, parses, carries the
      key as a real bool true, and passes the fail-hard diff gate against
      the live device base captured this run — 100% of the original keys
      intact. Without a captured base the gate refuses outright: a
      whole-file overwrite is never verified against nothing.
    """
    problems = []
    if g2_active:
        found, effective, sub = _effective_plist(files, G2_DOMAIN, G2_REL_PATH)
        problems.extend(sub)
        if not found:
            problems.append(
                f"G2: no restore record for {G2_DOMAIN}/{G2_REL_PATH}")
        elif effective is not None:
            problems.extend(_check_candidate_key(effective, "G2"))
    if g1_active:
        found, effective, sub = _effective_plist(files, G1_DOMAIN, G1_REL_PATH)
        problems.extend(sub)
        if not found:
            problems.append(
                f"G1: no restore record for {G1_DOMAIN}/{G1_REL_PATH}")
        elif effective is not None:
            problems.extend(_check_candidate_key(effective, "G1"))
            if not isinstance(g1_base, dict):
                problems.append(
                    "G1: no live device base was captured this run, so the "
                    "whole-file payload cannot be verified — refusing to "
                    "write it")
            else:
                allowed = set(g1_allowed_new) | {GP_KEY}
                problems.extend(diff_gate(
                    g1_base, effective,
                    allowed_new=allowed, allowed_override=allowed))
    return problems


# --- saved device original (rollback source for G1) -----------------------
# Per-device store in the app-data dir, following the LastApply pattern in
# src/restore/lastapply.py. The FIRST capture wins and is never overwritten:
# a later apply's base may already contain our key, and the rollback source
# must stay the pristine file from before the first apply.
_STORE_ENV = "LGD_STORE_DIR"
_STORE_SUBDIRS = ("GoldenNugget", "LiquidGlassDisable")


def _store_dir() -> str:
    override = os.environ.get(_STORE_ENV, "").strip()
    base = override or QStandardPaths.writableLocation(
        QStandardPaths.AppDataLocation)
    folder = os.path.join(base, *_STORE_SUBDIRS)
    os.makedirs(folder, exist_ok=True)
    return folder


def _safe_udid(udid) -> str:
    return "".join(c for c in str(udid) if c.isalnum() or c in "._-")


def original_plist_path(udid) -> str:
    return os.path.join(_store_dir(), f"{_safe_udid(udid)}.original.plist")


def original_meta_path(udid) -> str:
    return os.path.join(_store_dir(), f"{_safe_udid(udid)}.original.json")


def save_original_if_absent(udid, base_bytes: bytes, meta: dict) -> bool:
    """Persist the device's pristine .GlobalPreferences.plist (first wins).

    Returns True when this call saved the original, False when one was
    already on record. Raises OSError on a real write failure — the apply
    pass treats that as fatal, because applying G1 without a rollback
    copy would leave the user no way back.
    """
    plist_path = original_plist_path(udid)
    if os.path.exists(plist_path):
        return False
    tmp_path = plist_path + ".tmp"
    with open(tmp_path, "wb") as fh:
        fh.write(bytes(base_bytes))
    os.replace(tmp_path, plist_path)
    record = dict(meta or {})
    record.setdefault("sha1", content_hash(bytes(base_bytes)))
    record.setdefault("size", len(base_bytes))
    from datetime import datetime, timezone
    record.setdefault("saved_at", datetime.now(timezone.utc).isoformat(
        timespec="seconds"))
    meta_path = original_meta_path(udid)
    meta_tmp = meta_path + ".tmp"
    with open(meta_tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, sort_keys=True, indent=2)
    os.replace(meta_tmp, meta_path)
    return True


def load_original(udid) -> Optional[bytes]:
    """The saved original's raw bytes, or None when never captured."""
    try:
        with open(original_plist_path(udid), "rb") as fh:
            data = fh.read()
        return data or None
    except OSError:
        return None


def load_original_meta(udid) -> Optional[dict]:
    """Metadata recorded with the saved original (capture time/source).

    Falls back to facts derived from the saved plist itself when the JSON
    sidecar is missing (e.g. a crash between the two writes): the saved
    original must never look absent while its bytes are on disk, or the
    UI would refuse a rollback the backend can still perform.
    """
    try:
        with open(original_meta_path(udid), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    plist_path = original_plist_path(udid)
    if not os.path.exists(plist_path):
        return None
    from datetime import datetime, timezone
    derived = {"source": "saved original (metadata sidecar missing)"}
    try:
        mtime = os.path.getmtime(plist_path)
        derived["saved_at"] = datetime.fromtimestamp(
            mtime, timezone.utc).isoformat(timespec="seconds")
    except OSError:
        pass
    try:
        with open(plist_path, "rb") as fh:
            parsed = load_plist_dict(fh.read())
        derived["key_count"] = len(parsed)
    except Exception:
        pass
    return derived


def original_saved(udid) -> bool:
    return bool(udid) and os.path.exists(original_plist_path(udid))


# --- tweak classes ---------------------------------------------------------

class LGDG2Tweak(BasicPlistTweak):
    """G2 route: stage SolariumForceFallback into the managed overlay.

    The staging itself is the plain BasicPlistTweak merge (the same dict
    every other GlobalPreferences tweak writes); this subclass only
    records that it actually staged, so the apply pass's verification gate
    can insist on the resulting restore record.
    """

    def __init__(self):
        super().__init__(G2_LOCATION, GP_KEY, GP_KEY_VALUE)
        self.staged = False

    def apply_tweak(self, other_tweaks: dict) -> dict:
        self.staged = False
        result = super().apply_tweak(other_tweaks)
        if self.enabled:
            self.staged = True
        return result


class LGDG1Tweak(BasicPlistTweak):
    """G1 route: merge the candidate key into the device's own file.

    A plain BasicPlistTweak here would stage a tweak-only dict over the
    live user file (HIGH bug B1's failure mode — it wiped
    language/region/keyboard). Instead the apply pass captures the
    device's live .GlobalPreferences.plist first
    (``DeviceManager._lgd_prepare_g1``) and hands the parsed dict to this
    tweak via ``_lgd_base``; staging then writes base + any keys other
    tweaks staged into the same file + our key. Without a base the tweak
    stages NOTHING and the pass's verification gate cancels the apply —
    fail closed, never a blind whole-file write.
    """

    def __init__(self):
        super().__init__(G1_LOCATION, GP_KEY, GP_KEY_VALUE)
        self.staged = False
        self._lgd_base: Optional[dict] = None

    def apply_tweak(self, other_tweaks: dict) -> dict:
        self.staged = False
        if not self.enabled:
            return other_tweaks
        base = self._lgd_base
        if not isinstance(base, dict):
            return other_tweaks
        merged = dict(base)
        staged = other_tweaks.get(self.file_location)
        if isinstance(staged, dict):
            merged.update(staged)
        if type(self.value) is not bool:
            raise NuggetException(
                "Liquid Glass Disable (Beta 1): the G1 candidate value is "
                f"not a real bool ({self.value!r}); refusing to stage it.")
        merged[self.key] = self.value
        other_tweaks[self.file_location] = merged
        self.staged = True
        return other_tweaks
