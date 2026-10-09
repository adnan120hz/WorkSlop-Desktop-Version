import logging
import os
import traceback
import uuid

logger = logging.getLogger("WorkSlop.templates_tweak")

from PySide6 import QtWidgets
from PySide6.QtCore import QCoreApplication

from ...tweak_classes import Tweak
from ..template_file import TemplateFile

from src.utils.file_to_restore import FileToRestore
from src.utils.zip_safe import assert_device_path_safe

class TemplatesTweak(Tweak):
    def __init__(self):
        super().__init__(key=None)
        self.templates: list[TemplateFile] = []
        # per-file record of templates skipped by the last apply_tweak()
        # (name, error) — a corrupt template must never read as applied
        self.skipped_templates: list = []

    def uses_domains(self):
        # TODO: figure out which templates use sparse restore
        for template in self.templates:
            if not template.domain.startswith("Sparserestore-"):
                return True
        return False
    
    def is_empty(self) -> bool:
        return len(self.templates) == 0

    def add_template(self, file: str, version: str = None):
        try:
            new_template = TemplateFile(path=file, device_version=version)
            self.templates.append(new_template)
        except Exception as e:
            logger.error(traceback.format_exc())
            detailsBox = QtWidgets.QMessageBox()
            detailsBox.setIcon(QtWidgets.QMessageBox.Critical)
            detailsBox.setWindowTitle(QCoreApplication.tr("Error"))
            detailsBox.setText(QCoreApplication.tr("Failed to load template") + f" {file}\n\n{str(e)}")
            detailsBox.exec()

    def parse_path_string(self, path: str, old_domain: str, new_domain: str) -> str:
        result_path = path.replace("/hiddendot", "/.").replace("//", "/")
        if old_domain.startswith("AppDomain-"):
            result_path = result_path.replace(old_domain.removeprefix("AppDomain-"), new_domain.removeprefix("AppDomain-"))
        return result_path
        
    def recursive_add(self, old_bundle: str, domain: str,
                      files_to_restore: list[FileToRestore],
                      curr_path: str, restore_path: str = "",
                      isAdding: bool = False
        ):
        if not os.path.isdir(curr_path):
            return
        for folder in sorted(os.listdir(curr_path)):
            if folder.startswith('.') or folder == "__MACOSX":
                continue
            if isAdding:
                # randomize uuid
                # if file then add it, otherwise recursively call again
                if os.path.isfile(os.path.join(curr_path, folder)):
                    try:
                        # update plist ids if needed
                        contents_path = os.path.join(curr_path, folder)
                        with open(contents_path, "rb") as in_file:
                            contents = in_file.read()
                        # handle for sparserestore
                        full_path = f"{restore_path}/{folder}"
                        restore_domain = domain
                        if domain.startswith("Sparserestore-"):
                            full_path = f"{domain.removeprefix('Sparserestore-')}{full_path}"
                            restore_domain = None
                        full_path = self.parse_path_string(full_path, old_bundle, domain)
                        # device-side traversal guard: a ".." segment here
                        # (e.g. via a crafted bundle id) would escape the
                        # target domain on the device
                        assert_device_path_safe(full_path)
                        files_to_restore.append(FileToRestore(
                            contents=contents,
                            restore_path=full_path,
                            domain=restore_domain
                        ))
                    except IOError:
                        logger.error(f"Failed to open file: {folder}")
                else:
                    self.recursive_add(old_bundle, domain, files_to_restore, os.path.join(curr_path, folder), f"{restore_path}/{folder}", isAdding)
            else:
                # look for container folder
                if folder.lower() == "container":
                    self.recursive_add(old_bundle, domain, files_to_restore, os.path.join(curr_path, folder), restore_path="/", isAdding=True)
                else:
                    self.recursive_add(old_bundle, domain, files_to_restore, os.path.join(curr_path, folder), isAdding=False)

    def apply_tweak(self,
                    files_to_restore: list[FileToRestore], output_dir: str,
                    templates: list,
                    version: str, force_pb_refresh: bool,
                    update_label=lambda x: None):
        if len(self.templates) == 0:
            return
        update_label("Extracting templates...")
        self.skipped_templates = []
        # extract templates
        for template in self.templates:
            # ignore PosterBoard templates since that is handled in PosterBoard tweaks
            if template.domain != 'com.apple.PosterBoard' and template.domain != 'AppDomain-com.apple.PosterBoard':
                temp_dir = os.path.join(output_dir, str(uuid.uuid4()))
                os.makedirs(temp_dir)
                # one corrupt .batter must not kill the whole apply: stage
                # this template's files separately, skip + report it per
                # file on failure, and keep going with the valid ones
                staged: list[FileToRestore] = []
                try:
                    template.extract(output_dir=temp_dir)
                    domain = template.domain
                    if template.change_bundle_id:
                        domain = f"AppDomain-{template.bundle_id}"
                    self.recursive_add(old_bundle=template.domain, domain=domain, files_to_restore=staged, curr_path=temp_dir)
                except Exception as e:
                    template_name = getattr(template, "name", None) or getattr(template, "path", "unknown template")
                    self.skipped_templates.append((template_name, str(e)))
                    logger.error(f"Skipping corrupt template {template_name}: {e}")
                    update_label(QCoreApplication.tr("Skipped corrupt template: {0}").format(template_name))
                    continue
                files_to_restore.extend(staged)
        if self.skipped_templates:
            skipped_names = ", ".join(name for name, _ in self.skipped_templates)
            update_label(QCoreApplication.tr("Skipped corrupt template(s): {0}").format(skipped_names))
        update_label("Adding other tweaks...")