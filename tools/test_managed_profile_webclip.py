#!/usr/bin/env python3
"""Offscreen checks for the WorkSlop bookmark WebClip profile.

Design (user order 2026-10-11): profile #2 (WebClip bookmark) has NO
button/tab of its own — it is auto-generated at the end of every
successful apply, with no toggle. Profile #1 (FeatureFlags,
com.apple.system.featureflags, targeting /var/preferences/FeatureFlags)
is untouched and stays separate.

Covers:
- no identifier collision with the FeatureFlags profile (both can be
  installed side by side on one iPhone),
- the WebClip payload structure uses only standard Apple payload keys,
- Label/URL/icon content is correct,
- plist round-trip works,
- the auto-generate hook fires only on the success alert (mock level,
  no device), never on aborts/errors, and never blocks an apply.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QCoreApplication

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    app = QApplication.instance() or QApplication([])

    from src.devicemanagement import managed_profile as ff
    from src.devicemanagement import managed_profile_webclip as wc

    # --- no collision between the two profiles ---------------------------
    check("WebClip PayloadType is the standard Apple string",
          wc.WEBCLIP_PAYLOAD_TYPE == "com.apple.webClip.managed")
    check("WebClip profile identifier differs from FeatureFlags default",
          wc.WEBCLIP_PROFILE_IDENTIFIER != "com.workslop.featureflags.experimental")
    check("identifiers share no namespace that could merge them",
          not wc.WEBCLIP_PROFILE_IDENTIFIER.startswith("com.workslop.featureflags")
          and "featureflags" not in wc.WEBCLIP_PROFILE_IDENTIFIER)
    check("website URL is the live WorkSlop site",
          wc.WORKSLP_WEBSITE_URL == "https://workslop-nu.vercel.app")
    check("repo icon file exists",
          os.path.isfile(wc.WORKSLP_ICON_PATH), wc.WORKSLP_ICON_PATH)

    profile = wc.build_webclip_profile("WorkSlop Bookmark", "TestOrg")
    inner = profile["PayloadContent"][0]

    check("top-level identifier is the WebClip namespace",
          profile["PayloadIdentifier"] == "com.workslop.webclip.bookmark")
    check("inner identifier is a distinct payload identifier",
          inner["PayloadIdentifier"] == "com.workslop.webclip.bookmark.payload"
          and inner["PayloadIdentifier"] != profile["PayloadIdentifier"])
    check("UUIDs are unique per level",
          profile["PayloadUUID"] != inner["PayloadUUID"])
    check("two builds get different UUIDs",
          wc.build_webclip_profile()["PayloadUUID"] != profile["PayloadUUID"])

    # --- payload structure: standard Apple WebClip keys only -------------
    check("inner PayloadType is com.apple.webClip.managed",
          inner["PayloadType"] == wc.WEBCLIP_PAYLOAD_TYPE)
    allowed = {"PayloadType", "PayloadVersion", "PayloadIdentifier",
               "PayloadUUID", "PayloadDisplayName", "PayloadDescription",
               "Label", "URL", "IsRemovable", "Precomposed", "Icon"}
    check("no invented payload keys", set(inner) <= allowed, str(sorted(set(inner) - allowed)))
    check("Label is WorkSlop", inner["Label"] == "WorkSlop")
    check("URL is the WorkSlop site", inner["URL"] == "https://workslop-nu.vercel.app")
    check("IsRemovable is true", inner["IsRemovable"] is True)
    check("Precomposed is true", inner["Precomposed"] is True)
    check("Icon is embedded PNG bytes",
          isinstance(inner.get("Icon"), (bytes, bytearray))
          and inner["Icon"][:8] == b"\x89PNG\r\n\x1a\n")

    noicon = wc.build_webclip_profile(include_icon=False)
    check("icon can be omitted", "Icon" not in noicon["PayloadContent"][0])

    # --- validation ------------------------------------------------------
    for kwargs, why in [
        ({"display_name": "  "}, "empty display name"),
        ({"label": ""}, "empty label"),
        ({"url": "ftp://x"}, "non-http URL"),
        ({"url": ""}, "empty URL"),
    ]:
        try:
            wc.build_webclip_profile(**kwargs)
            raise SystemExit(f"should have raised: {why}")
        except ValueError:
            check(f"rejects {why}", True)

    # --- plist round-trip -------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "ws-bookmark.mobileconfig")
        wc.write_mobileconfig(profile, path)
        check("file written", os.path.isfile(path))
        back = wc.read_mobileconfig(path)
        bi = back["PayloadContent"][0]
        check("round-trip preserves PayloadType",
              bi["PayloadType"] == "com.apple.webClip.managed")
        check("round-trip preserves Label/URL",
              bi["Label"] == "WorkSlop"
              and bi["URL"] == "https://workslop-nu.vercel.app")
        check("round-trip preserves identifier",
              back["PayloadIdentifier"] == "com.workslop.webclip.bookmark")
        check("round-trip preserves Icon bytes",
              bytes(bi["Icon"])[:8] == b"\x89PNG\r\n\x1a\n")

    # --- the two profiles stay separate (identifier proof) ---------------
    ff_profile = ff.build_feature_flags_profile(
        "FF Test", "o", [{"Domain": "d", "FeatureName": "n", "Enabled": True}])
    check("profile identifiers differ",
          ff_profile["PayloadIdentifier"] != profile["PayloadIdentifier"])
    check("payload identifiers differ",
          ff_profile["PayloadContent"][0]["PayloadIdentifier"]
          != inner["PayloadIdentifier"])
    check("payload types differ",
          ff_profile["PayloadContent"][0]["PayloadType"]
          != inner["PayloadType"])
    check("FeatureFlags profile untouched: still targets FF payload type",
          ff_profile["PayloadContent"][0]["PayloadType"]
          == "com.apple.system.featureflags")

    # --- auto-generate hook on the apply path (mock level, no device) ----
    from src.devicemanagement.device_manager import DeviceManager
    from src.utils.alerts import ApplyAlertMessage

    dm = DeviceManager.__new__(DeviceManager)

    success_alert = ApplyAlertMessage(
        txt="All done! Please restart.",
        title=QCoreApplication.tr("Success!"),
        icon=QMessageBox.Information)
    check("success alert is detected",
          dm._is_success_alert(success_alert) is True)

    error_alert = ApplyAlertMessage(
        txt="boom", title="Error!", icon=QMessageBox.Critical)
    check("error alert is NOT treated as success",
          dm._is_success_alert(error_alert) is False)
    check("abort alert is NOT treated as success",
          dm._is_success_alert(ApplyAlertMessage(
              txt="aborted", title=QCoreApplication.tr("Apply Aborted"),
              icon=QMessageBox.Warning)) is False)
    check("None alert is NOT treated as success",
          dm._is_success_alert(None) is False)

    with tempfile.TemporaryDirectory() as td:
        # 1) the writer works at mock level
        written = dm._write_webclip_bookmark(output_dir=td)
        check("writer returns the written path",
              written is not None and os.path.isfile(written))
        check("written file is the WebClip profile",
              wc.read_mobileconfig(written)["PayloadIdentifier"]
              == "com.workslop.webclip.bookmark")

        # 2) the hook fires on success: generates + appends the note
        calls = []
        real_writer = dm._write_webclip_bookmark

        def fake_writer(output_dir=None):
            calls.append(output_dir)
            return real_writer(output_dir=td)

        dm._write_webclip_bookmark = fake_writer
        before = success_alert.txt
        dm._maybe_write_webclip_bookmark(success_alert)
        check("hook generated on success", len(calls) == 1)
        check("hook appended install note to the alert",
              len(success_alert.txt) > len(before)
              and "Profile Downloaded" in success_alert.txt
              and td in success_alert.txt)

        # 3) the hook stays silent on failure — and never raises
        dm._maybe_write_webclip_bookmark(error_alert)
        dm._maybe_write_webclip_bookmark(None)
        check("hook did not fire on non-success alerts", len(calls) == 1)

        # 4) a generation failure never blocks the apply path: break the
        #    builder internals (the writer's try/except must catch it)
        import src.devicemanagement.managed_profile_webclip as _wcmod
        real_build = _wcmod.build_webclip_profile

        def boom_build(*a, **k):
            raise RuntimeError("disk gone")

        _wcmod.build_webclip_profile = boom_build
        try:
            check("writer failure returns None (never raises)",
                  dm._write_webclip_bookmark(output_dir=td) is None)
        finally:
            _wcmod.build_webclip_profile = real_build

        # 5) the hook itself never raises, even if the writer is hostile
        def boom2(output_dir=None):
            raise RuntimeError("disk gone")

        dm._write_webclip_bookmark = boom2
        alert2 = ApplyAlertMessage(
            txt="ok", title=QCoreApplication.tr("Success!"),
            icon=QMessageBox.Information)
        try:
            dm._maybe_write_webclip_bookmark(alert2)
            check("hook failure does not raise and leaves alert intact",
                  alert2.txt == "ok")
        except Exception:
            raise SystemExit("hook must never raise")

    print(f"\nALL {PASS} CHECKS PASSED")


main()
