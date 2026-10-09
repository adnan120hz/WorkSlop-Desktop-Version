#!/usr/bin/env python3
"""Audit 42: Messages data must not depend on the photo toggle.

Before the fix, ``_is_protective_file`` kept MessagesDomain only when
``include_photos`` was set (it shared PROTECTIVE_DOMAINS with the photo
domains), so a prune with photos off silently dropped every message.
Photos are a separate axis: CameraRollDomain/MediaDomain stay gated by
``include_photos``; MessagesDomain is always protective.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit42_messages_always_protective.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.restore.protective import (
    PHOTO_DOMAINS,
    _is_protective_file,
    _keep_protective_entry,
    is_protective_device_file,
)

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nAudit 42: Messages always protective, photos stay gated")

    check("photo gate no longer contains MessagesDomain",
          "MessagesDomain" not in PHOTO_DOMAINS
          and PHOTO_DOMAINS == {"CameraRollDomain", "MediaDomain"})

    for rel in ("Messages/sms.db", "Messages/Attachments/a/img.jpg",
                "sms.db"):
        check(f"Messages kept with photos OFF ({rel})",
              _is_protective_file("MessagesDomain", rel, include_photos=False))
        check(f"Messages kept with photos ON ({rel})",
              _is_protective_file("MessagesDomain", rel, include_photos=True))
        check(f"Messages kept when AFC trees excluded ({rel})",
              _is_protective_file("MessagesDomain", rel, include_photos=False,
                                  exclude_afc_media_trees=True))
        check(f"prune keep-set keeps Messages, photos OFF ({rel})",
              _keep_protective_entry("MessagesDomain", rel,
                                     include_photos=False))

    for domain, rel in (("CameraRollDomain", "DCIM/100APPLE/IMG_0001.JPG"),
                        ("MediaDomain", "PhotoData/Photos.sqlite")):
        check(f"{domain} dropped with photos OFF",
              not _is_protective_file(domain, rel, include_photos=False))
        check(f"{domain} kept with photos ON",
              _is_protective_file(domain, rel, include_photos=True))
        check(f"prune keep-set drops {domain} with photos OFF",
              not _keep_protective_entry(domain, rel, include_photos=False))

    check("AFC-handed photo tree still excluded when photos ON",
          not _is_protective_file("CameraRollDomain", "Media/DCIM/IMG_1.JPG",
                                  include_photos=True,
                                  exclude_afc_media_trees=True))
    check("same photo tree kept when AFC exclusion off",
          _is_protective_file("CameraRollDomain", "Media/DCIM/IMG_1.JPG",
                              include_photos=True,
                              exclude_afc_media_trees=False))

    check("mid-stream filter keeps Messages with photos OFF",
          is_protective_device_file("MessagesDomain/Messages/sms.db",
                                    include_photos=False))
    check("mid-stream filter drops CameraRoll with photos OFF",
          not is_protective_device_file("CameraRollDomain/DCIM/IMG_1.JPG",
                                        include_photos=False))

    check("HomeDomain settings unaffected by photo toggle (OFF)",
          _is_protective_file("HomeDomain",
                              "Library/Preferences/com.apple.test.plist",
                              include_photos=False))
    check("HomeDomain junk still dropped",
          not _is_protective_file("HomeDomain",
                                  "Library/Caches/com.apple.junk.plist",
                                  include_photos=True))
    check("Keychain still gated by include_keychain only",
          not _is_protective_file("KeychainDomain", "keychain.db",
                                  include_photos=True)
          and _is_protective_file("KeychainDomain", "keychain.db",
                                  include_photos=False,
                                  include_keychain=True))

    print(f"\nPASS {PASS} checks")


if __name__ == "__main__":
    main()
