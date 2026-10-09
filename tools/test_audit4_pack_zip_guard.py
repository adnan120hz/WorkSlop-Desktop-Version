#!/usr/bin/env python3
"""Fix Audit 4: local icon-pack zip import leaked raw zip errors.

The Icon Themes page called the (frozen) hash-matched importer
directly: an encrypted zip escaped as zipfile's raw
``RuntimeError: ... password ...`` into the UI, and nothing limited
the archive size before extraction. The caller side now goes through
``src.controllers.icon_pack_import``: size is rejected before the
file is opened, encryption is probed up front, and any escaping
RuntimeError is converted to a readable IconPackImportError. The
frozen tweak model is untouched.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit4_pack_zip_guard.py
"""
import os
import struct
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import src.tweaks.icon_themes.icon_themes_tweak as itt  # noqa: E402
from src.controllers.icon_pack_import import (  # noqa: E402
    MAX_ICON_PACK_ZIP_BYTES, IconPackImportError,
    ensure_pack_zip_within_limit, import_local_pack_zip, probe_pack_zip)
from src.gui.ios.icon_themes import IOS18_ICONS  # noqa: E402
from src.tweaks.icon_themes.icon_themes_tweak import (  # noqa: E402
    IconThemesTweak, build_pack_hash_index)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TMP = tempfile.mkdtemp(prefix="workslop-a4-")
_STORE = os.path.join(TMP, "store")
os.makedirs(_STORE, exist_ok=True)  # real persistent_themes_dir() creates it
itt.persistent_themes_dir = lambda: _STORE

catalog = [
    (bundle_id, name,
     os.path.join(ROOT, "files", "ios18_icons", "Light", f"{slug}.png"),
     os.path.join(ROOT, "files", "ios18_icons", "Dark", f"{slug}.png"))
    for name, bundle_id, slug in IOS18_ICONS
]
index = build_pack_hash_index(catalog)


def expect_guard(name, fn, *needles):
    try:
        fn()
    except IconPackImportError as exc:
        check(name, all(n.lower() in str(exc).lower() for n in needles),
              str(exc))
        return
    except Exception as exc:  # raw leak = the bug coming back
        check(name, False, f"raw {type(exc).__name__} escaped: {exc}")
        return
    check(name, False, "no error raised")


print("\n(a) oversized pack rejected BEFORE it is opened")
huge = os.path.join(TMP, "huge.zip")
with open(huge, "wb") as f:
    f.truncate(MAX_ICON_PACK_ZIP_BYTES + 1)  # sparse: size only, no content
expect_guard("size limit fires on file size alone",
             lambda: import_local_pack_zip(IconThemesTweak(), huge, index),
             "over", "safety limit")
expect_guard("size helper rejects limit+1",
             lambda: ensure_pack_zip_within_limit(MAX_ICON_PACK_ZIP_BYTES + 1),
             "safety limit")
ensure_pack_zip_within_limit(MAX_ICON_PACK_ZIP_BYTES)
check("size helper accepts exactly the limit", True)

print("\n(b) encrypted pack -> readable error, never a raw RuntimeError")
plain = os.path.join(TMP, "plain.zip")
with zipfile.ZipFile(plain, "w") as zf:
    zf.writestr("com.apple.camera.png", b"\x89PNG\r\n\x1a\nfake")
with open(plain, "rb") as f:
    blob = bytearray(f.read())
# Set the encryption flag (bit 0) in the local + central headers.
assert blob[:4] == b"PK\x03\x04"
struct.pack_into("<H", blob, 6, struct.unpack_from("<H", blob, 6)[0] | 0x1)
central = blob.find(b"PK\x01\x02")
assert central > 0
struct.pack_into("<H", blob, central + 8,
                 struct.unpack_from("<H", blob, central + 8)[0] | 0x1)
encrypted = os.path.join(TMP, "encrypted.zip")
with open(encrypted, "wb") as f:
    f.write(blob)
expect_guard("probe names the pack password-protected",
             lambda: probe_pack_zip(encrypted), "password-protected")
expect_guard("guarded import names the pack password-protected",
             lambda: import_local_pack_zip(IconThemesTweak(), encrypted, index),
             "password-protected")

print("\n(c) a RuntimeError still escaping the importer is converted")


class _ExplodingTweak:
    def import_pack_zip_matched(self, path, hash_index):
        raise RuntimeError("File <ZipInfo> is encrypted, password required")


expect_guard("raw 'password required' RuntimeError never reaches the UI",
             lambda: import_local_pack_zip(
                 _ExplodingTweak(), plain, index),
             "password-protected")

print("\n(d) non-zip + valid pack behave as before")
junk = os.path.join(TMP, "junk.zip")
with open(junk, "wb") as f:
    f.write(b"definitely not a zip")
expect_guard("non-zip rejected with a readable message",
             lambda: import_local_pack_zip(IconThemesTweak(), junk, index),
             "could not be read as an icon pack")

camera_light = os.path.join(ROOT, "files", "ios18_icons", "Light", "camera.png")
good = os.path.join(TMP, "good.zip")
with zipfile.ZipFile(good, "w") as zf:
    zf.write(camera_light, "App Icon-37.png")
result = import_local_pack_zip(IconThemesTweak(), good, index)
check("valid catalog pack still imports by hash",
      result["archive_ok"] and len(result["imported"]) == 1
      and result["imported"][0][0] == "com.apple.camera",
      repr(result["imported"]))

print(f"\nALL {PASS} CHECKS PASSED")
