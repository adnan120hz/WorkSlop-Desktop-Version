import base64
import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("WorkSlop.preset_manager")

from PySide6.QtCore import QStandardPaths

from src.tweaks.tweak_names import TweakID
from src.tweaks import tweak_loader
from src.tweaks.tweaks import tweaks
from src.tweaks.tweak_classes import (
    BasicPlistTweak, AdvancedPlistTweak,
    MobileGestaltTweak, MobileGestaltPickerTweak,
)
from src.tweaks.posterboard.posterboard_tweak import PosterboardTweak
from src.tweaks.posterboard.pb_config_item import PBConfigItem
from src.tweaks.posterboard.template_options.templates_tweak import TemplatesTweak
from src.tweaks.status_bar.status_bar_tweak import StatusBarTweak
from src.tweaks.status_bar.status_setter import _deserialize_override, _serialize_override
from src.tweaks.icon_themes.icon_themes_tweak import IconThemesTweak
from src.tweaks.icon_themes.icon_theme import IconTheme
from src.controllers.hotload import HotLoad
from src.devicemanagement.constants import mobilegestalt_decision
from src.tweaks.capabilities import (
    canonical_tweak_id, tweak_deliverability,
)

PRESETS_DIR_NAME = "Presets"
PRESET_VERSION = 2


class UnsupportedPresetVersionError(ValueError):
    """A preset file uses a schema version this build cannot read.

    Raised by the load/import validation (Fix Audit 43) so callers get a
    message that names the unsupported preset version instead of the old
    silent acceptance of v1 / pre-metadata presets. ``load_preset`` catches
    it, records it in ``last_error`` and returns False, so GUI callers show
    their normal failure dialog instead of crashing."""


class PresetManager:
    def __init__(self):
        base_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        # Ensure GoldenNugget-specific folder
        if not base_dir.endswith("GoldenNugget") and not base_dir.endswith("GoldenNugget/"):
            base_dir = os.path.join(base_dir, "GoldenNugget")
        self.presets_dir = os.path.join(base_dir, PRESETS_DIR_NAME)
        os.makedirs(self.presets_dir, exist_ok=True)
        # Structured record of the tweaks the last load skipped (and why),
        # filled by _apply(); the UI can surface a concise summary from it.
        self.last_skipped: list[dict] = []
        # Human-readable reason the last load/import failed (Fix Audit 43:
        # names the unsupported preset version), for callers that only get
        # a bool back from load_preset().
        self.last_error: Optional[str] = None

    def get_preset_path(self, name: str) -> str:
        safe_name = self._sanitize_name(name)
        return os.path.join(self.presets_dir, f"{safe_name}.json")

    def _sanitize_name(self, name: str) -> str:
        safe = "".join(c for c in name if c.isalnum() or c in " _-").strip()
        return safe or "Preset"

    def list_presets(self) -> list[str]:
        presets = []
        if not os.path.isdir(self.presets_dir):
            return presets
        for file in sorted(os.listdir(self.presets_dir)):
            if file.lower().endswith(".json"):
                presets.append(os.path.splitext(file)[0])
        return presets

    def get_preset_metadata(self, name: str) -> Optional[dict]:
        """Get metadata for a preset without loading the full data."""
        file_path = self.get_preset_path(name)
        if not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("metadata", {})
        except Exception:
            return None

    def preset_has_daemon_changes(self, name: str) -> bool:
        """True if the preset enables the daemon modifications or turns on any
        individual daemon (i.e. it carries daemon tweaks that would be applied)."""
        file_path = self.get_preset_path(name)
        if not os.path.isfile(file_path):
            return False
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return False
        daemon_data = data.get("tweaks", {}).get("Daemons")
        if not isinstance(daemon_data, dict):
            return False
        if daemon_data.get("enabled"):
            return True
        values = daemon_data.get("value") or {}
        return any(values.values())

    def preset_hidden_feature_names(self, name: str, hotload: HotLoad,
                                    device_version: str = "",
                                    device_model: str = "") -> list[str]:
        """Return the names of HotLoad-hidden features that this preset would
        restore (i.e. it contains at least one enabled tweak of a feature that
        is currently hidden on this device). Loading such a preset would try to
        re-enable broken/dangerous features, so the caller should not load it."""
        file_path = self.get_preset_path(name)
        if not os.path.isfile(file_path):
            return []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []
        hidden = hotload.hidden_features(device_version=device_version,
                                         device_model=device_model)
        if not hidden:
            return []
        tweaks_data = data.get("tweaks", {})
        if not isinstance(tweaks_data, dict):
            return []
        present_features = set()
        for key in tweaks_data:
            feature = hotload.feature_for(key)
            if feature:
                present_features.add(feature)
        return sorted(hidden & present_features)

    def list_presets_with_metadata(self) -> list[dict]:
        """List all presets with their metadata."""
        result = []
        for name in self.list_presets():
            meta = self.get_preset_metadata(name)
            if meta:
                result.append({
                    "name": name,
                    "description": meta.get("description", ""),
                    "device_model": meta.get("device_model", "Unknown"),
                    "ios_version": meta.get("ios_version", "Unknown"),
                    "created_at": meta.get("created_at", 0),
                    "updated_at": meta.get("updated_at", 0),
                    "tags": meta.get("tags", []),
                    "version": meta.get("version", 1),
                })
        return sorted(result, key=lambda x: x.get("updated_at", 0), reverse=True)

    def save_preset(self, name: str, description: str = "", tags: list = None,
                    device_model: str = "", ios_version: str = "") -> bool:
        data = self._serialize()
        if data is None:
            return False
        
        # Add metadata
        now = int(time.time())
        meta = {
            "version": PRESET_VERSION,
            "description": description or "",
            "device_model": device_model or "Unknown",
            "ios_version": ios_version or "Unknown",
            "created_at": now,
            "updated_at": now,
            "tags": tags or [],
        }
        # Preserve original creation time if updating
        existing_meta = self.get_preset_metadata(name)
        if existing_meta and "created_at" in existing_meta:
            meta["created_at"] = existing_meta["created_at"]
        
        data["metadata"] = meta
        
        file_path = self.get_preset_path(name)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error("Failed to save preset: %s", e)
            return False

    @staticmethod
    def _data_preset_version(data) -> Optional[int]:
        """Schema version recorded in *data*, or None when absent/invalid."""
        if not isinstance(data, dict):
            return None
        meta = data.get("metadata")
        if not isinstance(meta, dict):
            return None
        raw = meta.get("version")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _validate_preset_version(cls, data) -> None:
        """Reject legacy preset schemas (Fix Audit 43).

        v1 / pre-metadata presets (no ``metadata.version`` field) used to be
        accepted silently; they must now fail loudly with the unsupported
        version named, while the current format (PRESET_VERSION) passes."""
        version = cls._data_preset_version(data)
        if version is None:
            raise UnsupportedPresetVersionError(
                "Unsupported preset version: the preset has no version "
                "field (missing metadata.version); this build only "
                f"supports preset version {PRESET_VERSION}. Re-save the "
                "preset with this version of WorkSlop Desktop.")
        if version != PRESET_VERSION:
            raise UnsupportedPresetVersionError(
                f"Unsupported preset version {version}: this build only "
                f"supports preset version {PRESET_VERSION}. Re-save the "
                "preset with this version of WorkSlop Desktop.")

    def load_preset(self, name: str, device_build: str = "",
                    device_version: str = "", device_model: str = "") -> bool:
        self.last_error = None
        file_path = self.get_preset_path(name)
        if not os.path.isfile(file_path):
            self.last_error = f"Preset not found: {name}"
            return False
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.last_error = str(e)
            logger.error("Failed to read preset: %s", e)
            return False
        try:
            self._validate_preset_version(data)
        except UnsupportedPresetVersionError as e:
            # Surface the version message to the caller via last_error and
            # the log; returning False keeps every existing GUI caller on
            # its normal failure dialog instead of crashing (Fix Audit 43).
            self.last_error = str(e)
            logger.error("Failed to load preset: %s", e)
            return False
        return self._apply(data, device_build=device_build,
                           device_version=device_version,
                           device_model=device_model)

    def delete_preset(self, name: str) -> bool:
        file_path = self.get_preset_path(name)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
                return True
        except Exception as e:
            logger.error("Failed to delete preset: %s", e)
        return False

    ## EXPORT / IMPORT
    def export_preset(self, name: str, export_path: str,
                      include: Optional[list] = None) -> bool:
        """Export a preset to a shareable JSON file.

        ``include`` optionally limits the export to a subset of tweaks, given
        as a list of ``TweakID`` members (or their ``.name`` strings). When
        omitted, the whole preset is exported. ``None``/empty means full.
        """
        file_path = self.get_preset_path(name)
        if not os.path.isfile(file_path):
            return False
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Add export marker
            data["exported"] = True
            data["exported_at"] = int(time.time())

            if include:
                data = self._filter_export(data, include)

            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error("Failed to export preset: %s", e)
            return False

    def build_export_data(self, include: Optional[list] = None) -> Optional[dict]:
        """Serialize the *current* tweak state, optionally limited to a subset.

        ``include`` is a list of ``TweakID`` members (or ``.name`` strings).
        Returns ``None`` if nothing was serialized.
        """
        data = self._serialize_subset(include)
        if data is None:
            return None
        # Stamp the current schema version so an export built from live
        # state is loadable again (Fix Audit 43 rejects version-less files).
        metadata = data.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata["version"] = PRESET_VERSION
        data["exported"] = True
        data["exported_at"] = int(time.time())
        return data

    @staticmethod
    def _filter_export(data: dict, include: list) -> dict:
        """Return a copy of *data* with ``tweaks`` reduced to ``include``
        and metadata annotated as a partial export."""
        include_names = set()
        for item in include:
            include_names.add(item.name if hasattr(item, "name") else str(item))
        tweaks_data = data.get("tweaks", {})
        filtered = {key: val for key, val in tweaks_data.items()
                    if key in include_names}
        out = dict(data)
        out["tweaks"] = filtered
        out["metadata"] = dict(data.get("metadata", {}))
        out["metadata"]["partial"] = True
        out["metadata"]["included"] = sorted(include_names)
        return out

    def _serialize_subset(self, include: Optional[list] = None) -> Optional[dict]:
        """Serialize the current tweaks filtered to ``include`` (TweakIDs/names)."""
        # Audit 29: same Risky registration as _serialize(), so a partial
        # export that names DisableOTAFile/CustomResolution (or a full
        # export with include=None) cannot silently drop them.
        tweak_loader.load_risky()
        if include is None:
            include = list(tweaks.keys())
        include_names = set()
        for item in include:
            include_names.add(item.name if hasattr(item, "name") else str(item))

        tweak_data = {}
        for key, tweak in tweaks.items():
            if key.name not in include_names:
                continue
            try:
                tweak_data[key.name] = self._serialize_tweak(tweak)
            except Exception as e:
                logger.error("Failed to serialize tweak %s: %s", key, e)

        if not tweak_data:
            return None
        return {"tweaks": tweak_data}

    def import_preset(self, import_path: str, new_name: str = None) -> tuple[bool, str]:
        """Import a preset from a JSON file. Returns (success, actual_name)."""
        if not os.path.isfile(import_path):
            return False, "File not found"
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Validate structure
            if "tweaks" not in data and "metadata" not in data:
                return False, "Invalid preset format"
            # Fix Audit 43: legacy (v1 / pre-metadata) files are rejected
            # with the unsupported version named, never imported silently.
            try:
                self._validate_preset_version(data)
            except UnsupportedPresetVersionError as e:
                return False, str(e)

            # Determine name
            if new_name is None:
                meta = data.get("metadata", {})
                new_name = meta.get("description", "Imported Preset")
                # Fallback to filename
                if not new_name or new_name == "Imported Preset":
                    new_name = os.path.splitext(os.path.basename(import_path))[0]
            
            # Sanitize and ensure unique
            base_name = self._sanitize_name(new_name)
            name = base_name
            counter = 1
            while os.path.isfile(self.get_preset_path(name)):
                name = f"{base_name} ({counter})"
                counter += 1
            
            # Update metadata
            now = int(time.time())
            if "metadata" not in data:
                data["metadata"] = {}
            data["metadata"]["imported_at"] = now
            data["metadata"]["updated_at"] = now
            if "created_at" not in data["metadata"]:
                data["metadata"]["created_at"] = now
            
            file_path = self.get_preset_path(name)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True, name
        except Exception as e:
            logger.error("Failed to import preset: %s", e)
            return False, str(e)

    ## SERIALIZATION
    def _serialize(self) -> dict:
        # Audit 29: ensure the Risky family exists before serializing, on
        # the same basis the GUI loads it (load_risky() in
        # RiskySection.refresh()). Without this, a save/AutoSave/CLI save
        # from a session that never opened the Risky page omits
        # DisableOTAFile/CustomResolution entirely, so they can never
        # round-trip. This only registers the instances; it does not
        # enable anything or bypass any deliverability gate.
        tweak_loader.load_risky()
        tweak_data = {}
        for key, tweak in tweaks.items():
            # Fix Audit 36/18: PosterBoard (selected tendies/templates/video)
            # and the MobileGestalt picker choices ride the same preset
            # serializer as every other tweak — only file *paths* are
            # stored, so presets stay light and device-independent.
            try:
                tweak_data[key.name] = self._serialize_tweak(tweak)
            except Exception as e:
                logger.error("Failed to serialize tweak %s: %s", key, e)

        return {
            "tweaks": tweak_data
        }

    def _serialize_tweak(self, tweak) -> dict:
        data = {"type": type(tweak).__name__, "enabled": tweak.enabled}
        if isinstance(tweak, AdvancedPlistTweak):
            # Store only what the UI exposes / what would actually apply.
            data["value"] = tweak._filter_keys(tweak.value)
        elif isinstance(tweak, BasicPlistTweak):
            data["value"] = tweak.value
            # RdarFixTweak (a BasicPlistTweak) keeps its real choice in
            # di_type, which follows the Dynamic Island picker (Audit 18).
            if hasattr(tweak, "di_type"):
                data["di_type"] = tweak.di_type
        elif isinstance(tweak, PosterboardTweak):
            # Fix Audit 36: the PosterBoard selection (tendies, video
            # wallpaper, delivery mode, saved configuration IDs) persists
            # through this same serializer. Paths only — the payload files
            # themselves never travel with a preset.
            data["tendies"] = [t.path for t in tweak.tendies]
            data["video_thumbnail"] = tweak.videoThumbnail
            data["video_file"] = tweak.videoFile
            data["loop_video"] = bool(tweak.loop_video)
            data["reverse_video"] = bool(tweak.reverse_video)
            data["use_foreground"] = bool(tweak.use_foreground)
            data["use_configs"] = bool(tweak.use_configs)
            data["calculation_mode"] = tweak.calculationMode
            data["disabled"] = bool(tweak.disabled)
            data["saved_config_ids"] = [
                {"uuid": item.uuid, "extension": item.extension,
                 "set_selected": bool(getattr(item, "set_selected", False))}
                for item in tweak.config_manager.saved_items
            ]
        elif isinstance(tweak, MobileGestaltPickerTweak):
            # Fix Audit 18: a picker choice is an index into the tweak's
            # value list; without it only "enabled" survived a restart and
            # the dropdown silently fell back to the first option.
            data["selected_option"] = int(tweak.selected_option)
        elif isinstance(tweak, MobileGestaltTweak):
            # Fix Audit 18: plain MobileGestalt tweaks (e.g. ModelName)
            # keep their user value here; key/subkey are definitions.
            data["value"] = tweak.value
        elif isinstance(tweak, TemplatesTweak):
            data["templates"] = [t.path for t in tweak.templates]
        elif isinstance(tweak, StatusBarTweak):
            data["enabled"] = tweak.enabled
            data["silly_mode"] = tweak.setter.silly_mode
            # Fixed-table serialization (clang/gcc layout, 3944 bytes), not a
            # raw ffi.buffer() dump: the host compiler's bitfield layout
            # differs on Windows (MSVC), which would corrupt presets there and
            # break cross-platform preset sharing. Pairs with
            # _deserialize_override() on load.
            data["override_data"] = base64.b64encode(
                _serialize_override(tweak.setter.current_overrides)).decode("ascii")
        elif isinstance(tweak, IconThemesTweak):
            # Icons live in the persistent IconThemes store (see
            # icon_themes_tweak.store_icon), so paths are stable across loads.
            data["themes"] = [
                {"bundle_id": t.bundle_id, "display_name": t.display_name,
                 "icon_path": t.icon_path}
                for t in tweak.themes
            ]
        # NullifyFileTweak only needs "enabled"
        return data

    ## DESERIALIZATION
    def _apply(self, data: dict, device_build: str = "",
               device_version: str = "", device_model: str = "") -> bool:
        try:
            # Fix Audit 43: never apply a legacy-schema preset, even when
            # _apply is reached without load_preset's validation.
            self._validate_preset_version(data)
            self.last_skipped = []
            decision = mobilegestalt_decision(device_build, device_version)
            # make sure every tweak exists before applying
            self._load_all_tweaks(decision)

            # never re-enable HotLoad-hidden features: loading a preset must not
            # resurrect broken/dangerous tweaks (defense-in-depth on top of the
            # warning shown before loading)
            from src.tweaks.hidden import current_hidden_tweak_names
            hidden_names = current_hidden_tweak_names()
            is_iphone = device_model.startswith("iPhone") if device_model else True

            if "tweaks" in data:
                for name, tweak_data in data["tweaks"].items():
                    raw_key = None
                    try:
                        raw_key = TweakID[name]
                    except KeyError:
                        continue
                    # Removed tombstone IDs (e.g. K1 / LGLPMGestalt) stay
                    # parseable here, then the central deliverability filter
                    # below records them as REMOVED_TWEAK and never assigns
                    # their state.
                    key = canonical_tweak_id(raw_key)
                    if name in hidden_names or key.name in hidden_names:
                        self.last_skipped.append({
                            "tweak_id": key.name,
                            "requested_enabled": bool(
                                tweak_data.get("enabled", False))
                            if isinstance(tweak_data, dict) else False,
                            "reason_code": "HOTLOAD_HIDDEN",
                            "reason": "Hidden by HotLoad safety rules.",
                        })
                        target = tweaks.get(key)
                        if target is not None:
                            target.set_enabled(False)
                        continue
                    target = tweaks.get(key)
                    # Central filter BEFORE state assignment: registry
                    # version/device-class constraints plus the shared
                    # MobileGestalt decision. Unsupported entries are forced
                    # off (never restored as ON) and reported in last_skipped.
                    deliverable, reason_code, reason = tweak_deliverability(
                        key, device_version=device_version,
                        device_build=device_build, is_iphone=is_iphone,
                        tweak=target)
                    if not deliverable:
                        if target is not None:
                            target.set_enabled(False)
                        self.last_skipped.append({
                            "tweak_id": key.name,
                            "requested_enabled": bool(
                                tweak_data.get("enabled", False))
                            if isinstance(tweak_data, dict) else False,
                            "reason_code": reason_code,
                            "reason": reason,
                        })
                        continue
                    if target is None:
                        continue
                    try:
                        self._apply_tweak(target, tweak_data, tweak_id=key)
                    except Exception as e:
                        logger.error("Failed to apply tweak %s: %s", name, e)

            return True
        except Exception as e:
            logger.error("Failed to apply preset: %s", e)
            return False

    def _load_all_tweaks(self, decision=None):
        # idempotent: the loaders return early if the tweaks already exist
        tweak_loader.load_plist_tweaks()
        tweak_loader.load_daemons()
        # Audit 29: the GUI registers the Risky family via load_risky()
        # (RiskySection.refresh() and the apply summary do this
        # unconditionally); the preset loader must do the same, otherwise
        # DisableOTAFile/CustomResolution have no instance here, _apply
        # finds target is None and silently drops them, and a later save
        # rewrites the preset without them. Registration only creates the
        # (disabled-by-default) instances — the Risky gate is untouched:
        # _apply still runs tweak_deliverability + the HotLoad-hidden
        # check before any state is assigned, exactly as before.
        tweak_loader.load_risky()
        if decision is not None and decision.supported:
            tweak_loader.load_mobilegestalt(decision=decision)
        # Loads the non-gestalt eligibility tweaks on any device; the
        # MobileGestalt-backed members only register when supported, and
        # stale gestalt state is cleared otherwise.
        tweak_loader.load_eligibility(None, decision)

    def _apply_tweak(self, tweak, data: dict, tweak_id=None):
        # Fix Audit 12: a preset that asks to disable Voice Control is
        # neutralised here — _filter_keys() below already drops the
        # blocked keys (never_enable), so they can never reach the tweak
        # value or the apply payload; record the skip honestly instead
        # of silently pretending the whole preset applied as stored.
        if isinstance(tweak, AdvancedPlistTweak) and isinstance(data.get("value"), dict):
            from src.tweaks.daemons_tweak import (
                BLOCKED_DAEMON_KEYS, VOICE_CONTROL_BLOCK_REASON)
            if any(data["value"].get(k) for k in BLOCKED_DAEMON_KEYS):
                self.last_skipped.append({
                    "tweak_id": tweak_id.name if tweak_id is not None else "Daemons",
                    "requested_enabled": True,
                    "reason_code": "VOICE_CONTROL_BLOCKED",
                    "reason": VOICE_CONTROL_BLOCK_REASON,
                })
        if "enabled" in data:
            enabled = bool(data["enabled"])
            if tweak_id is not None:
                # Route through the model helper so mutual-exclusion pairs
                # (spec.excludes + _EXTRA_EXCLUSIONS) are enforced and the
                # change notification fires; direct attribute assignment
                # could leave both sides of a pair ON (audit round 23).
                from src.tweaks.tweaks import set_tweak_enabled
                set_tweak_enabled(tweak_id, enabled)
            else:
                tweak.set_enabled(enabled)

        if isinstance(tweak, AdvancedPlistTweak):
            if "value" in data:
                # Drop keys not available in the UI (e.g. unknown daemons), so
                # a stored preset can never re-enable hidden ones.
                tweak.value = tweak._filter_keys(data["value"])
        elif isinstance(tweak, BasicPlistTweak):
            if "value" in data:
                tweak.value = data["value"]
            # RdarFixTweak: restore the picker-driven di_type (Audit 18).
            if "di_type" in data and hasattr(tweak, "di_type"):
                try:
                    tweak.di_type = int(data["di_type"])
                except (TypeError, ValueError):
                    pass
        elif isinstance(tweak, PosterboardTweak):
            self._apply_posterboard(tweak, data)
        elif isinstance(tweak, MobileGestaltPickerTweak):
            # Fix Audit 18: restore the picker index through the tweak's own
            # setter so enabled state and selection stay consistent.
            if "selected_option" in data:
                try:
                    idx = int(data["selected_option"])
                except (TypeError, ValueError):
                    idx = 0
                if tweak.value:
                    idx = max(0, min(idx, len(tweak.value) - 1))
                tweak.set_selected_option(
                    idx, is_enabled=bool(data.get("enabled", tweak.enabled)))
        elif isinstance(tweak, MobileGestaltTweak):
            if "value" in data:
                tweak.value = data["value"]
        elif isinstance(tweak, TemplatesTweak):
            self._apply_templates(tweak, data)
        elif isinstance(tweak, StatusBarTweak):
            self._apply_status_bar(tweak, data)
        elif isinstance(tweak, IconThemesTweak):
            self._apply_icon_themes(tweak, data)

    def _apply_posterboard(self, tweak: PosterboardTweak, data: dict):
        """Restore the PosterBoard selection saved by _serialize_tweak
        (Fix Audit 36). Files that disappeared since the save are skipped,
        never restored as dangling paths."""
        if "tendies" in data:
            tweak.tendies = []
            for path in data.get("tendies") or []:
                if path and os.path.isfile(path):
                    try:
                        tweak.add_tendie(path)
                    except Exception as e:
                        logger.error("Failed to restore tendie %s: %s", path, e)
        for attr, key in (("videoThumbnail", "video_thumbnail"),
                          ("videoFile", "video_file")):
            if key in data:
                path = data.get(key)
                setattr(tweak, attr,
                        path if path and os.path.isfile(path) else None)
        for attr, key in (("loop_video", "loop_video"),
                          ("reverse_video", "reverse_video"),
                          ("use_foreground", "use_foreground"),
                          ("use_configs", "use_configs"),
                          ("disabled", "disabled")):
            if key in data:
                setattr(tweak, attr, bool(data.get(key)))
        if data.get("calculation_mode") in ("linear", "discrete"):
            tweak.calculationMode = data["calculation_mode"]
        if "saved_config_ids" in data:
            items = []
            for entry in data.get("saved_config_ids") or []:
                if isinstance(entry, dict) and entry.get("uuid"):
                    items.append(PBConfigItem(
                        entry["uuid"], entry.get("extension", ""),
                        set_selected=bool(entry.get("set_selected", False))))
            tweak.config_manager.saved_items = items

    def _apply_templates(self, tweak: TemplatesTweak, data: dict):
        if "templates" in data:
            tweak.templates = []
            for path in data["templates"]:
                if os.path.isfile(path):
                    try:
                        tweak.add_template(path)
                    except Exception as e:
                        logger.error("Failed to add template: %s", e)

    def _apply_status_bar(self, tweak: StatusBarTweak, data: dict):
        tweak.set_enabled(bool(data.get("enabled", False)))
        tweak.setter.silly_mode = data.get("silly_mode", False)
        if "override_data" in data:
            try:
                raw = base64.b64decode(data["override_data"])
                # Parse through the fixed offset table, not memmove(): the blob
                # uses the clang/gcc layout, but cffi models the host compiler's
                # layout, so on Windows (MSVC) a raw copy decodes bitfields at
                # the wrong offsets. See _deserialize_override().
                new_overrides = _deserialize_override(raw)
                tweak.setter.apply_changes(new_overrides)
            except Exception as e:
                logger.error("Failed to restore status bar: %s", e)

    def _apply_icon_themes(self, tweak: IconThemesTweak, data: dict):
        tweak.themes = []
        for entry in data.get("themes", []):
            if not isinstance(entry, dict) or not entry.get("bundle_id"):
                continue
            path = entry.get("icon_path", "")
            if path and os.path.isfile(path):
                # Stick to the persistent store copy so the restored theme
                # stays loadable even if the original file disappeared.
                theme = IconTheme(bundle_id=entry["bundle_id"],
                                  display_name=entry.get("display_name", ""),
                                  icon_path=path)
                if tweak.store_icon(theme):
                    tweak.add_theme(theme)

