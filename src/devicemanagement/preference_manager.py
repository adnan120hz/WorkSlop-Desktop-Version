from PySide6.QtCore import QSettings, QStandardPaths
from os import path, makedirs
from os import remove as rmfile
from shutil import copyfile
from typing import Optional

from src.tweaks.posterboard.pb_config_item import PBConfigItem
from src.controllers.settings import Settings

class PreferenceManager:
    def __init__(self, settings: QSettings):
        self.settings = settings
        self.auto_reboot = True
        self.disable_tendies_limit = False
        self.auto_refresh_posterboard = True
        self.use_backup_cache = True
        self.use_encrypted_backup = False
        self.use_afc_media = True
        self.skip_setup = True
        self.supervised = False
        self.organization_name = ""
        # Write the "AutoSave" preset on every tweak change and load it back on
        # startup. Turning it off stops both halves; the preset file itself is
        # left alone so an existing one can still be loaded by hand.
        self.tweak_autosave = True

    # PosterBoard Configuration Database Saving
    def get_pbconfigs_prefs() -> QSettings:
        return Settings("PB Configs")
    def get_pbconfigs_db_save_path(udid: Optional[str]=None) -> str:
        app_data_path = path.join(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation), "PB_Saved_Databases")
        if not path.exists(app_data_path):
            makedirs(app_data_path)
        if udid is not None:
            app_data_path = path.join(app_data_path, f'{udid}.sqlite3')
        return app_data_path
    
    def save_pbconfig_file(filepath: str, udid: str):
        pbdb_path = PreferenceManager.get_pbconfigs_db_save_path(udid)
        copyfile(filepath, pbdb_path)
    def save_pbconfig_ids(ids: list[PBConfigItem], udid: str):
        pbc_settings = PreferenceManager.get_pbconfigs_prefs()
        # convert it to serializable data
        serialized_ids: list[dict] = []
        for id in ids:
            serialized_ids.append(id.to_dict())
        pbc_settings.setValue(udid, serialized_ids)

    def remove_pbconfig_data(udid: str):
        pbdb_path = PreferenceManager.get_pbconfigs_db_save_path(udid)
        if path.exists(pbdb_path):
            rmfile(pbdb_path)
            PreferenceManager.remove_pbconfig_ids(udid)
    def remove_pbconfig_ids(udid: str):
        pbc_settings = PreferenceManager.get_pbconfigs_prefs()
        if pbc_settings.contains(udid):
            pbc_settings.remove(udid)

    def has_pbconfig_data(udid: str) -> bool:
        return path.exists(PreferenceManager.get_pbconfigs_db_save_path(udid))

    def get_pbconfig_path(udid: str) -> Optional[str]:
        pbdb_path = PreferenceManager.get_pbconfigs_db_save_path(udid)
        if path.exists(pbdb_path):
            return pbdb_path
        return None
    def get_pbconfig_ids(udid: str) -> list[PBConfigItem]:
        pbc_settings = PreferenceManager.get_pbconfigs_prefs()
        if not pbc_settings.contains(udid):
            return []
        serialized_ids = pbc_settings.value(udid)
        if serialized_ids is None:
            return []
        ids: list[PBConfigItem] = []
        for id in serialized_ids:
            ids.append(PBConfigItem.from_dict(id))
        return ids
    # MobileGestalt file storage — logic ported from leminlimez/Nugget
    # (src/devicemanagement/preference_manager.py). The device-specific
    # com.apple.MobileGestalt.plist is kept per-UDID so the user only picks
    # the file once; it is re-validated against build/model on every use.
    def get_mga_prefs() -> QSettings:
        return Settings("MobileGestalt")

    def save_mga_file(filepath: str, udid: str):
        mga_settings = PreferenceManager.get_mga_prefs()
        with open(filepath, 'rb') as mga_file:
            mga_settings.setValue(udid, mga_file.read())

    def remove_mga_data(udid: str):
        mga_settings = PreferenceManager.get_mga_prefs()
        if mga_settings.contains(udid):
            mga_settings.remove(udid)

    # REAUDIT FIX: has_mga_data() was dead code — zero callers. The real
    # check used by the apply flow is has_valid_mga_data() below (which
    # also validates build/model). Removed the unused helper.

    def has_valid_mga_data(self, udid: str, build: str, model: str) -> bool:
        # makes sure that it matches the build/model as well as existing
        # also removes it if the build/model don't match
        data = self.get_mga_data(udid)
        if data == None:
            return False
        if not self.is_valid_mga_plist(data, build, model):
            self.remove_mga_data(udid)
            return False
        return True

    def get_mga_data(self, udid: str) -> dict:
        import plistlib
        mga_settings = PreferenceManager.get_mga_prefs()
        if not mga_settings.contains(udid):
            return None
        data = mga_settings.value(udid)
        return plistlib.loads(data)

    def is_valid_mga_plist(self, plist: dict, device_build: str, device_model: str) -> bool:
        return ("CacheVersion" in plist
                and "0+nc/Udy4WNG8S+Q7a/s1A" in plist["CacheExtra"]
                and plist["CacheVersion"] == device_build
                and plist["CacheExtra"]["0+nc/Udy4WNG8S+Q7a/s1A"] == device_model)
