#!/usr/bin/env python3
"""Headless test: import the real catwithabaloon ZIP by content hash.

The pack ("iOS 18 App Icons by catwithabaloon") ships generic file
names (``App Icon-37.png``) with no bundle id in them, so the old
name-based importer could only invent bogus themes. The matched
importer (IconThemesTweak.import_pack_zip_matched) sha256-matches
every file against the bundled 68-app catalog instead.

The 2.0 pack holds 206 files: Light ``App Icon-1..68``, Dark
``App Icon-69..136`` (18 of them byte-identical to their Light
twin), Tinted ``App Icon-137..203``, plus ``App Icon.png`` (a
duplicate of #136), ``itunes-store-2017-09-26 (1).png`` and
``my-shortcuts.png``. The hash index covers Light+Dark only, so the
67 Tinted files and the 2 extras come back unmatched — by name, never
as invented bundle ids.

Locks, against the user's actual ZIP:
* all 68 catalog apps are imported, one theme each, stored on disk;
* Light wins when both variants match;
* NO theme is ever created from a file name ("App Icon-*" bundle ids);
* the files that match nothing are counted as unmatched, by name —
  69 of them (67 Tinted + 2 extras);
* re-import skips already-present apps instead of clobbering them;
* a synthetic renamed icon still maps by content, and a corrupt zip
  reports archive_ok=False.

Run: python tools/test_icon_pack_zip_import.py
"""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

PASS = 0
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REAL_ZIP = os.path.expanduser(
    "~/workspace/user/files/iOS.18.App.Icons.by.catwithabaloon.zip")


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("WorkSlop Desktop")

    import src.tweaks.icon_themes.icon_themes_tweak as itt
    from src.gui.ios.icon_themes import IOS18_ICONS
    from src.tweaks.icon_themes.icon_themes_tweak import (
        IconThemesTweak, build_pack_hash_index)

    store_dir = tempfile.mkdtemp(prefix="workslop-icon-store-")
    itt.persistent_themes_dir = lambda: store_dir

    catalog = [
        (bundle_id, name,
         os.path.join(ROOT, "files", "ios18_icons", "Light", f"{slug}.png"),
         os.path.join(ROOT, "files", "ios18_icons", "Dark", f"{slug}.png"))
        for name, bundle_id, slug in IOS18_ICONS
    ]
    index = build_pack_hash_index(catalog)
    print("\nhash index over the bundled catalog files")
    check("136 bundled files hash to 118 unique digests", len(index) == 118,
          str(len(index)))

    if os.path.isfile(REAL_ZIP):
        pack_zip = REAL_ZIP
        expected_unmatched = 69  # 67 Tinted + 2 extras (iTunes Store, my-shortcuts)
        print(f"\nusing the user's real ZIP: {REAL_ZIP}")
    else:
        # CI has no user files: synthesize an equivalent pack from the
        # bundled catalog itself (every bundled PNG under a nonsense
        # name, Light first) plus 105 junk PNGs. Content-hash matching
        # then faces exactly the same semantics as the real pack:
        # 68 apps imported, 136 catalog files matched, 105 unmatched.
        pack_zip = os.path.join(
            tempfile.mkdtemp(prefix="workslop-icon-pack-"), "synthetic.zip")
        with zipfile.ZipFile(pack_zip, "w") as zf:
            for _name, _bid, slug in IOS18_ICONS:
                zf.write(os.path.join(
                    ROOT, "files", "ios18_icons", "Light", f"{slug}.png"),
                    f"Synthetic Light {slug}.png")
            for _name, _bid, slug in IOS18_ICONS:
                dark_path = os.path.join(
                    ROOT, "files", "ios18_icons", "Dark", f"{slug}.png")
                if os.path.isfile(dark_path):
                    zf.write(dark_path, f"Synthetic Dark {slug}.png")
            for i in range(105):
                zf.writestr(f"junk-{i:03d}.png",
                            b"\x89PNG\r\n\x1a\n" + bytes([i]) * 32)
        expected_unmatched = 105
        print(f"\nreal ZIP absent; using synthetic equivalent: {pack_zip}")

    print(f"\npack ZIP: 68 apps by content, {expected_unmatched} files unmatched")
    tweak = IconThemesTweak()
    result = tweak.import_pack_zip_matched(pack_zip, index)
    check("archive read ok", result["archive_ok"])
    imported = result["imported"]
    check("68 apps imported", len(imported) == 68, str(len(imported)))
    check("imported bundle ids are exactly the catalog",
          {b for b, _, _ in imported}
          == {bid for _, bid, _ in IOS18_ICONS})
    check("68 themes on the tweak", len(tweak.themes) == 68)
    check("no theme was invented from a file name",
          not any(t.bundle_id.startswith("App Icon")
                  for t in tweak.themes))
    check("nothing was already present on a fresh tweak",
          result["already_present"] == [])
    check("no icon failed to store", result["store_failed"] == [],
          repr(result["store_failed"]))
    check(f"{expected_unmatched} unmatched files, counted and named",
          len(result["unmatched"]) == expected_unmatched,
          str(len(result["unmatched"])))
    check("unmatched entries are named pack files",
          all(n.endswith(".png") for n in result["unmatched"]),
          repr(result["unmatched"][:2]))
    check("every imported icon was stored in the persistent folder",
          all(t.icon_path and os.path.isfile(t.icon_path)
              and os.path.realpath(t.icon_path).startswith(
                  os.path.realpath(store_dir))
              for t in tweak.themes))
    by_bundle = {b: dark for b, _, dark in imported}
    check("Shortcuts imported from its Light artwork",
          by_bundle.get("com.apple.shortcuts") is False)
    check("Camera prefers Light when both variants match",
          by_bundle.get("com.apple.camera") is False)

    print("\nre-import: present apps skipped, never clobbered")
    again = tweak.import_pack_zip_matched(pack_zip, index)
    check("second import adds nothing", again["imported"] == [])
    check("all 68 reported already present",
          len(again["already_present"]) == 68,
          str(len(again["already_present"])))
    check("unmatched still counted",
          len(again["unmatched"]) == expected_unmatched)
    check("theme count unchanged", len(tweak.themes) == 68)

    print("\nsynthetic zip: content wins over nonsense names")
    tmp = tempfile.mkdtemp(prefix="workslop-icon-syn-")
    syn_zip = os.path.join(tmp, "synthetic.zip")
    camera_light = os.path.join(
        ROOT, "files", "ios18_icons", "Light", "camera.png")
    with zipfile.ZipFile(syn_zip, "w") as zf:
        zf.write(camera_light, "Totally Made Up Name 12345.png")
        zf.writestr("Mystery.png", b"\x89PNG\r\n\x1a\nnot a real icon")
    fresh = IconThemesTweak()
    syn = fresh.import_pack_zip_matched(syn_zip, index)
    check("renamed Camera icon maps to com.apple.camera",
          [b for b, _, _ in syn["imported"]] == ["com.apple.camera"],
          repr(syn["imported"]))
    check("no theme named after the nonsense file name",
          not any("Made Up" in t.bundle_id for t in fresh.themes))
    check("unknown file reported by name",
          syn["unmatched"] == ["Mystery.png"], repr(syn["unmatched"]))

    print("\ncorrupt archive: reported, not raised")
    bad_zip = os.path.join(tmp, "bad.zip")
    with open(bad_zip, "wb") as f:
        f.write(b"this is not a zip")
    bad = IconThemesTweak().import_pack_zip_matched(bad_zip, index)
    check("archive_ok is False", bad["archive_ok"] is False)
    check("nothing imported from a corrupt zip", bad["imported"] == [])

    print(f"\nALL {PASS} CHECKS PASSED")


main()
