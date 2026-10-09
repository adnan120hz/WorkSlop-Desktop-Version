import logging
import os
import uuid

logger = logging.getLogger("WorkSlop.posterboard_tweak")
import plistlib
from random import randint
from shutil import copytree
from PySide6 import QtWidgets
from PySide6.QtCore import QCoreApplication

from ..tweak_classes import Tweak
from .tendie_file import TendieFile
from .template_file import TemplateFile
from .pb_config_manager import PBConfigManager
from src.utils.file_to_restore import FileToRestore
from src.controllers.plist_handler import set_plist_value
from src.controllers.files_handler import get_bundle_files
from src.controllers import video_handler
from src.controllers.aar.aar import wrap_in_aar
from src.exceptions.nugget_exception import NuggetException
from src.devicemanagement.constants import Version

# PosterBoard architecture: leminlimez/Nugget v7.4 (tag v7.4, commit
# 26097697f5527f42c13ebd2e90ef0e1e5958da41), adopted 2026-10-03 and
# adapted to this fork's layout (FileToRestore lives in src.utils; the
# config manager keeps this fork's stricter DB validation):
#   * DEFAULT mode = descriptors: tendies/templates/video are staged as
#     plain descriptor FILES under PRBPosterExtensionDataStore and
#     PosterBoard ingests them itself. No device sqlite is fetched,
#     mutated, or shipped. A broken descriptor fails alone — delete it
#     or reset wallpapers; the data store is never corrupted by us.
#   * OPTIONAL "configurations" mode (use_configs) keeps the database
#     path for users who need it; only then is the device DB fetched
#     (targeted backup) and a staged sqlite shipped.
# The fork's old always-DB system (fetch + mutate + inject on every
# apply, plus the full_reset empty-DB wipe) is retired: recovery from a
# bad wallpaper is now "remove/reset", never a database restore.


class PosterboardTweak(Tweak):
    def __init__(self):
        super().__init__(key=None)
        self.tendies: list[TendieFile] = []
        self.videoThumbnail = None
        self.videoFile = None
        self.loop_video = True
        self.reverse_video = False
        self.use_foreground = False
        # v7.4 delivery mode: False = descriptors (default, file-only),
        # True = configurations (database-backed, opt-in).
        self.use_configs = False
        self.calculationMode = 'linear'
        self.bundle_id = "com.apple.PosterBoard"
        self.resetModes = []
        # When True, PosterBoard is completely excluded from the apply.
        self.disabled = False
        self.structure_version = 61
        self.config_manager = PBConfigManager()

    def uses_domains(self):
        if self.disabled:
            return False
        return (len(self.tendies) > 0 or self.videoFile != None
                or len(self.resetModes) > 0)

    def is_empty(self) -> bool:
        return not self.uses_domains()

    def verify_tendie(self, new_tendie: TendieFile) -> bool:
        if new_tendie.descriptor_cnt + self.get_descriptor_count() <= 10:
            self.tendies.append(new_tendie)
            # alert if prb reset is needed
            if new_tendie.unsafe_container:
                detailsBox = QtWidgets.QMessageBox()
                detailsBox.setIcon(QtWidgets.QMessageBox.Critical)
                detailsBox.setWindowTitle(QCoreApplication.tr("Warning"))
                detailsBox.setText(QCoreApplication.tr("NOTE: You may need to reset all wallpapers and then re-apply for this file to work."))
                detailsBox.exec()
            return True
        return False

    def add_tendie(self, file: str):
        new_tendie = TendieFile(path=file)
        return self.verify_tendie(new_tendie)

    def get_descriptor_count(self):
        cnt = 0
        for tendie in self.tendies:
            cnt += tendie.descriptor_cnt
        return cnt

    # MercuryPoster configs keep their own textual descriptor identifier
    # (e.g. "v6x.colorB") that the userInfo.lookIdentifier and the
    # suggestionMetadata reference — rewriting it to a random number breaks
    # the lookup chain. Identifiers are preserved byte-for-byte for it.
    MERCURY_EXTENSION = "com.apple.MercuryPoster"

    @classmethod
    def is_mercury(cls, restore_path: str) -> bool:
        parts = restore_path.split('/')
        return len(parts) > 6 and parts[6] == cls.MERCURY_EXTENSION

    def update_plist_id(self, file_path: str, file_name: str, randomizedID: int):
        if file_name == "com.apple.posterkit.provider.descriptor.identifier":
            return str(randomizedID).encode()
        elif file_name == "com.apple.posterkit.provider.contents.userInfo":
            return set_plist_value(file=os.path.join(file_path, file_name), key="wallpaperRepresentingIdentifier", value=randomizedID)
        elif file_name.endswith("Wallpaper.plist"):
            return set_plist_value(file=os.path.join(file_path, file_name), key="identifier", value=randomizedID, recursive=False)
        return None


    def recursive_add(self,
                      files_to_restore: list[FileToRestore],
                      curr_path: str, restore_path: str = "",
                      isAdding: bool = False,
                      randomizeUUID: bool = False, randomizedID: int = None
        ):
        if not os.path.isdir(curr_path):
            return
        if isAdding and randomizeUUID and ("ordered-descriptor" in curr_path or "ordered-descriptors" in curr_path):
            # PosterBoard orders wallpapers by wallpaper id in reverse order
            r_id = randint(9999, 99999)
            r_id_list = sorted([r_id + i for i in range(len(os.listdir(curr_path)))], reverse=True)
        counter = 0
        for folder in sorted(os.listdir(curr_path)):
            if folder.startswith('.') or folder == "__MACOSX":
                continue
            if isAdding:
                # randomize uuid
                folder_name = folder
                curr_randomized_id = randomizedID
                if randomizeUUID:
                    if "ordered-descriptor" in curr_path or "ordered-descriptors" in curr_path:
                        folder_name = str(uuid.uuid4()).upper()
                        curr_randomized_id = r_id_list[counter]
                        counter += 1
                    else:
                        folder_name = str(uuid.uuid4()).upper()
                        curr_randomized_id = randint(9999, 99999)
                    # add it to the configuration (configurations mode only)
                    if self.use_configs:
                        ext = restore_path.split('/')[6]
                        self.config_manager.add_config(folder_name, ext)
                # if file then add it, otherwise recursively call again
                fullpath = os.path.join(curr_path, folder)
                if os.path.isfile(fullpath):
                    try:
                        # if converting to config and it is a file to be modified, then update it (don't add it here and add them later)
                        if self.use_configs and self.config_manager.file_needs_updated(folder):
                            continue
                        # update plist ids if needed
                        new_contents = None
                        contents_path = fullpath
                        # Mercury identifiers are preserved (see is_mercury);
                        # the rewrite below is Marble/Collections-specific.
                        if curr_randomized_id != None and not self.is_mercury(restore_path):
                            new_contents = self.update_plist_id(curr_path, folder, curr_randomized_id)
                            if new_contents != None:
                                contents_path = None
                        files_to_restore.append(FileToRestore(
                            contents=new_contents,
                            contents_path=contents_path,
                            restore_path=f"{restore_path}/{folder_name}".replace("//", "/"),
                            domain=f"AppDomain-{self.bundle_id}"
                        ))
                    except IOError:
                        logger.error(f"Failed to open file: {folder}")
                else:
                    # add config files if needed (configurations mode only)
                    if self.use_configs and curr_path.endswith("versions") and "descriptor" in curr_path:
                        self.config_manager.cache_config_files()
                        for config_file in self.config_manager.config_files:
                            files_to_restore.append(FileToRestore(
                                contents=None,
                                contents_path=os.path.join(self.config_manager.config_files_folder, config_file),
                                restore_path=f"{restore_path}/{folder_name}/{config_file}",
                                domain=f"AppDomain-{self.bundle_id}"
                            ))
                    self.recursive_add(files_to_restore, fullpath, f"{restore_path}/{folder_name}", isAdding, randomizedID=curr_randomized_id)
            else:
                # look for container folder
                name = folder.lower()
                if name == "container":
                    # A container is a full data-store snapshot: walk it (non-adding)
                    # so the descriptor folders inside get routed to configurations,
                    # exactly like a custom .tendie, and registered in the DB.
                    self.recursive_add(files_to_restore, os.path.join(curr_path, folder), restore_path="/", isAdding=False)
                    return
                elif "descriptor" in name:
                    # get the extension
                    parent = os.path.basename(curr_path)
                    if parent.startswith("com.apple."):
                        # container: the provider extension is the descriptor's parent folder
                        ext = parent
                    elif "video" in name or "photos" in name:
                        ext = "com.apple.PhotosUIPrivate.PhotosPosterProvider"
                    elif "mercury" in name:
                        ext = "com.apple.MercuryPoster"
                    else:
                        ext = "com.apple.WallpaperKit.CollectionsPoster"
                    if self.use_configs:
                        wpfolder = "configurations"
                    else:
                        wpfolder = "descriptors"
                    self.recursive_add(
                        files_to_restore,
                        os.path.join(curr_path, folder),
                        restore_path=f"/Library/Application Support/PRBPosterExtensionDataStore/{self.structure_version}/Extensions/{ext}/{wpfolder}",
                        isAdding=True,
                        randomizeUUID=True
                    )
                else:
                    self.recursive_add(files_to_restore, os.path.join(curr_path, folder), isAdding=False)

    def create_live_photo_files(self, output_dir: str):
        if self.videoFile != None and not self.loop_video:
            source_dir = get_bundle_files("files/posterboard/1F20C883-EA98-4CCE-9923-0C9A01359721")
            video_output_dir = os.path.join(output_dir, "video-descriptor", "1F20C883-EA98-4CCE-9923-0C9A01359721")
            copytree(source_dir, video_output_dir, dirs_exist_ok=True)
            contents_path = os.path.join(video_output_dir, "versions", "0", "contents", "0EFB6A0F-7052-4D24-8859-AB22BADF2E93")

            # convert the video first
            video_contents = None
            if self.videoFile.endswith('.mov'):
                # no need to convert
                with open(self.videoFile, "rb") as vid:
                    video_contents = vid.read()
            else:
                # convert to mov
                video_contents = video_handler.convert_to_mov(input_file=self.videoFile)
            # now replace video
            with open(os.path.join(contents_path, "output.layerStack", "portrait-layer_settling-video.MOV"), "wb") as overriding:
                overriding.write(video_contents)
            aar_path = os.path.join(contents_path, "input.segmentation", "segmentation.data.aar")
            wrap_in_aar(get_bundle_files("files/posterboard/contents.plist"), video_contents, aar_path)

            # replace the heic files
            if self.videoThumbnail != None:
                del video_contents
                with open(self.videoThumbnail, "rb") as thumb:
                    thumb_contents = thumb.read()
            else:
                raise NuggetException("No thumbnail heic selected!")
            to_override = ["input.segmentation/asset.resource/Adjusted.HEIC", "input.segmentation/asset.resource/proxy.heic", "output.layerStack/portrait-layer_background.HEIC"]
            for file in to_override:
                with open(os.path.join(contents_path, *(file.split("/"))), "wb") as overriding:
                    overriding.write(thumb_contents)
            del thumb_contents

    def create_video_loop_files(self, output_dir: str, update_label=lambda x: None):
        if self.videoFile and self.loop_video:
            source_dir = get_bundle_files("files/posterboard/VideoCAML")
            video_output_dir = os.path.join(output_dir, "descriptor", "VideoCAML")
            copytree(source_dir, video_output_dir, dirs_exist_ok=True)
            contents_path = os.path.join(video_output_dir, "versions", "1", "contents", "9183.Custom-810w-1080h@2x~ipad.wallpaper")
            if self.use_foreground:
                # rename the foreground layer to background
                bg_path = os.path.join(contents_path, "9183.Custom_Background-810w-1080h@2x~ipad.ca")
                contents_path = os.path.join(contents_path, "9183.Custom_Floating-810w-1080h@2x~ipad.ca")
                os.rename(contents_path, bg_path)
            else:
                contents_path = os.path.join(contents_path, "9183.Custom_Background-810w-1080h@2x~ipad.ca")
            logger.debug(f"path at {contents_path}, creating caml")
            video_handler.create_caml(
                video_path=self.videoFile, output_file=contents_path,
                auto_reverses=self.reverse_video, calculationMode=self.calculationMode,
                update_label=update_label
            )
            
            

    def _stage_force_refresh(self, files_to_restore, version):
        plist = {
            "PBF_LOCALE_DID_CHANGE": False,
            "PBF_RESET_FILE_PROTECTIONS": True
        }
        if Version(version) >= Version("26.4"):
            plist["PersistedPosterContainerBundleIdentifiers"] = [
                "com.apple.Posters.CollectionsPosterApp"
            ]
            plist["CompletedPosterBundleIdentifierMigrations"] = [
                "com.apple.Posters.UnityPosterApp.ExtragalacticPoster",
                "com.apple.Posters.WeatherPosterApp.WeatherPoster",
                "com.apple.Posters.UnityPosterApp.Unity2025Poster",
                "com.apple.Posters.UnityPosterApp.UnityPosterExtension",
                "com.apple.Posters.UnityPosterApp.RhizomePoster",
                "com.apple.Posters.KaleidoscopePosterApp.KaleidoscopePoster"
            ]
        files_to_restore.append(FileToRestore(
            contents=plistlib.dumps(plist, fmt=plistlib.PlistFormat.FMT_BINARY),
            restore_path="/Library/Preferences/com.apple.PosterBoard.unprotectedUserDefaults.plist",
            domain=f"AppDomain-{self.bundle_id}"
        ))

    def apply_tweak(self,
                    files_to_restore: list[FileToRestore], output_dir: str,
                    templates: list[TemplateFile],
                    version: str, force_pb_refresh: bool,
                    update_label=lambda x: None):
        # Disabled: don't touch PosterBoard at all on this apply.
        if self.disabled:
            return
        # Structure version (v7.4 rule): iOS 16 uses the 59 layout,
        # everything newer the 61 layout — learned from the OS version,
        # NOT from a fetched database (there is no database fetch in the
        # default descriptors mode). In configurations mode a fetched DB
        # may still refine it.
        if version.startswith("16"):
            self.structure_version = 59
        elif getattr(self.config_manager, "structure_version", 0):
            self.structure_version = self.config_manager.structure_version
        else:
            self.structure_version = 61
        if len(self.resetModes) > 0:
            # Reset = zero the descriptor/gallery folders ONLY (v7.4).
            # No database is created or shipped: PosterBoard rebuilds its
            # own store from whatever descriptors remain, which is what
            # makes recovery from a bad wallpaper trivial.
            file_paths = []
            for mode in self.resetModes:
                if mode == "Collections":
                    file_paths.append(f"/{self.structure_version}/Extensions/com.apple.WallpaperKit.CollectionsPoster/descriptors")
                    file_paths.append(f"/{self.structure_version}/Extensions/com.apple.MercuryPoster/descriptors")
                elif mode == "Suggested Photos":
                    file_paths.append(f"/{self.structure_version}/Extensions/com.apple.PhotosUIPrivate.PhotosPosterProvider/descriptors")
                elif mode == "Gallery Cache":
                    file_paths.append(f"/{self.structure_version}/GalleryCache")
                else:
                    file_paths.append("")
            for file_path in file_paths:
                files_to_restore.append(FileToRestore(
                    contents=b"",
                    restore_path=f"/Library/Application Support/PRBPosterExtensionDataStore{file_path}",
                    domain=f"AppDomain-{self.bundle_id}"
                ))
            if force_pb_refresh:
                self._stage_force_refresh(files_to_restore, version)
            return
        elif len(self.tendies) == 0 and len(templates) == 0 and self.videoFile == None:
            return
        update_label(QCoreApplication.tr("Generating PosterBoard Video..."))
        self.create_live_photo_files(output_dir)
        self.create_video_loop_files(output_dir, update_label=update_label)
        # extract tendies
        for tendie in self.tendies:
            update_label(QCoreApplication.tr("Extracting tendie {0}...").format(tendie.name))
            tendie.extract(output_dir=output_dir)
        # extract templates
        for template in templates:
            if template.domain == 'com.apple.PosterBoard' or template.domain == 'AppDomain-com.apple.PosterBoard':
                update_label(QCoreApplication.tr("Configuring template {0}...").format(template.name))
                template.extract(output_dir=output_dir)
        # add the files
        update_label(QCoreApplication.tr("Adding tendies..."))
        if self.use_configs:
            self.config_manager.start_staging()
        self.recursive_add(files_to_restore, curr_path=output_dir)
        if self.use_configs:
            # Configurations mode only: register the new descriptors in
            # a staged copy of the device database. The 0-byte -wal/-shm
            # companions stay mandatory HERE (a replaced WAL-mode main
            # file must not replay stale frames); descriptors mode above
            # never ships a database at all.
            staged_db_path = self.config_manager.update_sqlite()
            db_path = f"/Library/Application Support/PRBPosterExtensionDataStore/{self.structure_version}/PBFPosterExtensionDataStoreSQLiteDatabase.sqlite3"
            files_to_restore.append(FileToRestore(
                contents=None,
                contents_path=staged_db_path,
                restore_path=db_path,
                domain=f"AppDomain-{self.bundle_id}"
            ))
            for wal_suffix in ("-wal", "-shm"):
                files_to_restore.append(FileToRestore(
                    contents=b"",
                    restore_path=db_path + wal_suffix,
                    domain=f"AppDomain-{self.bundle_id}"
                ))
        # add the force refresh
        if force_pb_refresh:
            self._stage_force_refresh(files_to_restore, version)
        update_label(QCoreApplication.tr("Adding other tweaks..."))
