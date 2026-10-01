# Ported verbatim from leminlimez/Nugget
# (src/tweaks/eligibility_tweak.py). Only the imports were adapted to this
# fork's layout (FileToRestore lives in src/utils/file_to_restore.py here).
# All tweak logic, paths, plist contents and the EU Enabler credit are
# Nugget's originals.
from .tweak_classes import Tweak
from src.controllers.files_handler import get_bundle_files
from src.utils.file_to_restore import FileToRestore

import plistlib
from os import path

class InvalidRegionCodeException(Exception):
    "Region code must be exactly 2 characters long!"
    pass

def replace_region_code(plist_path: str, original_code: str = "US", new_code: str = "US"):
    """Return the plist's bytes with the region code swapped.

    Only string *values* that exactly match ``original_code`` are rewritten
    (e.g. OS_ELIGIBILITY_CONTEXT_COUNTRY_BILLING); keys are never touched.
    The old implementation stringified the whole plist and ran a global
    str.replace + eval(): that corrupted the *key*
    OS_ELIGIBILITY_DOMAIN_PHOSPHORUS ("...PHOSPHORUS" ends in "US") for any
    non-US region, and eval() on a stringified plist is a code-execution
    hole. This walks the parsed structure instead — no eval at all.
    """
    if len(new_code) != 2:
        raise InvalidRegionCodeException(
            f"Region code must be exactly 2 characters long, got {new_code!r}")
    with open(plist_path, 'rb') as f:
        plist_data = plistlib.load(f)

    def _swap(node):
        if isinstance(node, dict):
            return {k: _swap(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_swap(v) for v in node]
        if isinstance(node, str) and node == original_code:
            return new_code
        return node

    return plistlib.dumps(_swap(plist_data))

class EligibilityTweak(Tweak):
    # EU Enabler (credit: lrdsnow / EUEnabler).
    #
    # B17 honesty fix: Nugget's "Method 1" / "Method 2" choice only changed
    # which /var/MobileAsset/... path the Config.plist was *generated* for —
    # but this fork has no BookRestore, so device_manager skips that file
    # entirely and it is never delivered to the device. The choice was a
    # gimmick; it is removed. This tweak now does exactly one honest thing:
    # write eligibility.plist with the region code swapped to
    # /var/db/os_eligibility/eligibility.plist (delivered via sparse restore).
    def __init__(self):
        super().__init__(key=None, value=None)
        self.code = "US"

    def set_region_code(self, new_code: str):
        if new_code == '':
            self.code = "US"
        else:
            self.code = new_code.upper()

    def apply_tweak(self) -> list[FileToRestore]:
        # credit to lrdsnow for EU Enabler
        # https://github.com/Lrdsnow/EUEnabler/blob/main/app.py
        if not self.enabled:
            return None
        print(f"Applying EU Enabler for region \'{self.code}\'...")
        # get the plists directory
        source_dir = get_bundle_files("files/eligibility")

        # eligibility.plist with the region code swapped — the only EU Enabler
        # file this fork can actually deliver (/var/db is a backup domain;
        # /var/MobileAsset needs BookRestore, which this fork does not have).
        file_path = path.join(source_dir, 'eligibility.plist')
        eligibility_data = replace_region_code(file_path, original_code="US", new_code=self.code)
        files_to_restore = [
            FileToRestore(
                contents=eligibility_data,
                restore_path="/var/db/os_eligibility/eligibility.plist",
            )
        ]

        # return the new files to restore
        return files_to_restore
    

class AITweak(Tweak):
    def __init__(self):
        super().__init__(key=None, value="")
    
    def set_language_code(self, lang: str):
        self.value = lang

    def apply_tweak(self) -> FileToRestore:
        if not self.enabled:
            return None
        langs = ["en"]
        if self.value != "":
            langs.append(self.value)
        plist = {
            "OS_ELIGIBILITY_DOMAIN_CALCIUM": {
                "os_eligibility_answer_source_t": 1,
                "os_eligibility_answer_t": 2,
                "status": {
                    "OS_ELIGIBILITY_INPUT_CHINA_CELLULAR": 2,
                }
            },
            "OS_ELIGIBILITY_DOMAIN_GREYMATTER": {
                "context": {
                    "OS_ELIGIBILITY_CONTEXT_ELIGIBLE_DEVICE_LANGUAGES": [langs]
                },
                "os_eligibility_answer_source_t": 1,
                "os_eligibility_answer_t": 4,
                "status": {
                    "OS_ELIGIBILITY_INPUT_DEVICE_LANGUAGE": 3,
                    "OS_ELIGIBILITY_INPUT_DEVICE_REGION_CODE": 3,
                    "OS_ELIGIBILITY_INPUT_EXTERNAL_BOOT_DRIVE": 3,
                    "OS_ELIGIBILITY_INPUT_GENERATIVE_MODEL_SYSTEM": 3,
                    "OS_ELIGIBILITY_INPUT_SHARED_IPAD": 3,
                    "OS_ELIGIBILITY_INPUT_SIRI_LANGUAGE": 3,
                }
            }
        }

        return FileToRestore(contents=plistlib.dumps(plist), restore_path="/var/db/eligibilityd/eligibility.plist")
    
class BookRestoreFileTweak(Tweak):
    # B31 NOTE (honest): the two 0-byte Placeholder files below are not
    # accidental litter — they ARE the mechanism. Restoring a file at these
    # paths forces iOS to create the parent folders
    # (SystemPreferencesDomain/FeatureFlags, DatabaseDomain/eligibilityd),
    # which is what "CreateBRFolders" means. This is verbatim from
    # leminlimez/Nugget. They cannot be cleaned up afterwards: the
    # sparse-restore channel can only write files, never delete them.
    def __init__(self):
        super().__init__(key=None, value=None)

    def apply_tweak(self) -> list[FileToRestore]:
        if not self.enabled:
            return None
        return [
            FileToRestore(
                contents=b"",
                restore_path="/FeatureFlags/Placeholder",
                domain="SystemPreferencesDomain"
            ),
            FileToRestore(
                contents=b"",
                restore_path="eligibilityd/Placeholder",
                domain="DatabaseDomain"
            )
        ]
