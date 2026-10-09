#!/usr/bin/env python3
"""Fix Audit 88: downloaded icon packs claimed unverified success.

The online pack downloader imported every download through the
name-based importer with no verification at all. Now
(``src.controllers.icon_pack_import.import_downloaded_pack``, called
from the downloader):

* a pack matching the bundled catalog is imported through the
  existing SHA-256 hash-matched path and its outcome says so;
* any other pack must at least be shaped like an icon pack (icons
  named by bundle ID — the naming rule the pack importer consumes),
  and its outcome states the icons were imported by name only, NOT
  hash-verified;
* a zip that is neither is rejected before extraction.

URLs/TLS are untouched. Run:
QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit88_download_verification.py
"""
import io
import os
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
    IconPackImportError, import_downloaded_pack)
from src.gui.ios.icon_themes import IOS18_ICONS  # noqa: E402
from src.tweaks.icon_themes.icon_themes_tweak import (  # noqa: E402
    IconThemesTweak, build_pack_hash_index)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TMP = tempfile.mkdtemp(prefix="workslop-a88-")
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


def zip_bytes(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


print("\n(a) catalog-matching download takes the SHA-256 matched path")
camera_light = os.path.join(ROOT, "files", "ios18_icons", "Light", "camera.png")
with open(camera_light, "rb") as f:
    camera_bytes = f.read()
data = zip_bytes({"App Icon-37.png": camera_bytes,
                  "Some Other Icon.png": b"\x89PNG\r\n\x1a\nunknown"})
tweak = IconThemesTweak()
outcome = import_downloaded_pack(tweak, data, "iOS 18 App Icons", index)
check("one catalog icon imported", outcome.added == 1, repr(outcome))
check("outcome declares hash verification", outcome.hash_verified is True)
check("note names SHA-256 verification",
      "SHA-256" in outcome.verification_note, outcome.verification_note)
check("the imported theme is the real catalog bundle id",
      [t.bundle_id for t in tweak.themes] == ["com.apple.camera"],
      repr([t.bundle_id for t in tweak.themes]))
check("unmatched file reported as skipped, not silently dropped",
      outcome.skipped == ["Some Other Icon.png"], repr(outcome.skipped))

print("\n(b) non-catalog pack: structure-gated, honestly name-only")
fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
data = zip_bytes({"com.example.fakeapp.png": fake_png})
tweak = IconThemesTweak()
outcome = import_downloaded_pack(tweak, data, "Example Pack", index)
check("bundle-ID-shaped pack imports by name", outcome.added == 1, repr(outcome))
check("outcome declares NO hash verification",
      outcome.hash_verified is False)
check("note says name-only, not verified",
      "NOT hash-verified" in outcome.verification_note,
      outcome.verification_note)

print("\n(c) zip that is neither catalog nor pack-shaped is rejected")
data = zip_bytes({"Mystery.png": b"\x89PNG\r\n\x1a\nunknown",
                  "notes.txt": "hello"})
try:
    import_downloaded_pack(IconThemesTweak(), data, "Bogus", index)
    check("structure-less zip rejected", False, "no error raised")
except IconPackImportError as exc:
    check("structure-less zip rejected", "does not look like an icon pack"
          in str(exc), str(exc))

print("\n(d) re-download of a present catalog pack is honest too")
data = zip_bytes({"App Icon-37.png": camera_bytes})
tweak2 = IconThemesTweak()
first = import_downloaded_pack(tweak2, data, "iOS 18 App Icons", index)
second = import_downloaded_pack(tweak2, data, "iOS 18 App Icons", index)
check("first download imports", first.added == 1 and first.hash_verified)
check("second download adds nothing but reports already-present",
      second.added == 0 and second.already_present == 1, repr(second))

print(f"\nALL {PASS} CHECKS PASSED")
