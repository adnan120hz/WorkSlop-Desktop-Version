#!/usr/bin/env python3
"""Audit 29: DisableOTAFile hilang dari preset (no device needed).

Jalur GUI vs preset manager (bukti dari kode):
* GUI memuat tweak Risky dengan ``load_risky()`` —
  ``RiskySection.refresh()`` (src/gui/ios/risky.py) dan ringkasan apply
  (``_build_apply_summary`` di src/gui/main_window_mixins.py) sama-sama
  memanggilnya tanpa syarat, jadi ``tweaks`` selalu punya
  ``DisableOTAFile``/``CustomResolution`` saat UI hidup.
* ``PresetManager`` tidak pernah memanggilnya: ``_load_all_tweaks()``
  hanya memuat plist/daemons/MobileGestalt/eligibility, dan
  ``_serialize()`` hanya mengiterasi isi ``tweaks`` apa adanya. Akibatnya
  preset yang dimuat headless/CLI menemukan ``target is None`` dan
  terlewat diam-diam (``last_skipped`` kosong), lalu save/AutoSave
  berikutnya menimpa file tanpa Risky selamanya.

Fix yang dipin test ini: ``PresetManager`` memanggil ``load_risky()``
pada jalur load (``_load_all_tweaks``) dan jalur simpan
(``_serialize``/``_serialize_subset``) — jalur yang sama seperti GUI.
Registrasi hanya membuat instance (default nonaktif); gerbang Risky
yang ada tidak dilemahkan: ``_apply`` tetap menjalankan
``tweak_deliverability`` + cek HotLoad-hidden sebelum state dipasang.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit29_preset_risky_roundtrip.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

from src.controllers.preset_manager import PresetManager  # noqa: E402
from src.tweaks import tweak_loader  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402
from src.tweaks.tweaks import tweaks  # noqa: E402

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def make_manager(tmpdir):
    pm = PresetManager()
    pm.presets_dir = tmpdir
    return pm


def forget_risky():
    """Simulate a headless/CLI start that never opened the Risky page."""
    for tid in (TweakID.DisableOTAFile, TweakID.CustomResolution):
        tweaks.pop(tid, None)


def disable_risky():
    for tid in (TweakID.DisableOTAFile, TweakID.CustomResolution):
        tw = tweaks.get(tid)
        if tw is not None:
            tw.set_enabled(False)


def read_preset(pm, name):
    with open(pm.get_preset_path(name), encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
def test_code_paths():
    print("\njulur kode: GUI memuat Risky, preset manager sekarang ikut")
    root = os.path.join(os.path.dirname(__file__), "..")
    risky_src = open(os.path.join(root, "src/gui/ios/risky.py"),
                     encoding="utf-8").read()
    check("GUI Risky section calls load_risky()", "load_risky()" in risky_src)
    mixins_src = open(os.path.join(root, "src/gui/main_window_mixins.py"),
                      encoding="utf-8").read()
    check("GUI apply summary calls load_risky()", "load_risky()" in mixins_src)
    pm_src = open(os.path.join(root, "src/controllers/preset_manager.py"),
                  encoding="utf-8").read()
    check("preset manager calls load_risky()", "load_risky()" in pm_src)
    # CLI AutoSave and GUI AutoSave both delegate to PresetManager, so the
    # manager fix is the shared CLI/AutoSave path (no second copy to drift).
    cli_src = open(os.path.join(root, "src/cli/common.py"),
                   encoding="utf-8").read()
    check("CLI autosave delegates to PresetManager.save_preset",
          "PresetManager().save_preset(" in cli_src)


# =============================================================================
def test_round_trip(tmpdir):
    print("\nround-trip: DisableOTAFile tersimpan & termuat kembali")
    # Baseline seperti caller nyata (GUI pages / CLI load_core_tweaks).
    tweak_loader.load_plist_tweaks()
    tweak_loader.load_daemons()
    forget_risky()
    check("headless start has no Risky instance",
          TweakID.DisableOTAFile not in tweaks)

    pm = make_manager(tmpdir)

    # Simpan dari keadaan fresh: serialize wajib mendaftarkan Risky dulu,
    # jadi entrinya ada di file (nonaktif), bukan hilang senyap.
    check("fresh save succeeds", pm.save_preset("Fresh") is True)
    fresh = read_preset(pm, "Fresh")
    check("fresh preset contains DisableOTAFile",
          "DisableOTAFile" in fresh.get("tweaks", {}))
    check("fresh preset contains CustomResolution",
          "CustomResolution" in fresh.get("tweaks", {}))
    check("fresh DisableOTAFile is stored disabled",
          fresh["tweaks"]["DisableOTAFile"].get("enabled") is False)

    # Jalur GUI: Risky page memuat family, user menyalakan OTA file +
    # custom resolution, lalu preset disimpan (== AutoSave/CLI save).
    tweak_loader.load_risky()
    tweaks[TweakID.DisableOTAFile].set_enabled(True)
    tweaks[TweakID.CustomResolution].set_enabled(True)
    tweaks[TweakID.CustomResolution].value = {
        "canvas_width": 1179, "canvas_height": 2556}
    check("save with Risky on succeeds", pm.save_preset("Audit29") is True)
    saved = read_preset(pm, "Audit29")
    ota = saved.get("tweaks", {}).get("DisableOTAFile", {})
    check("saved preset contains DisableOTAFile", bool(ota))
    check("saved DisableOTAFile is enabled", ota.get("enabled") is True)
    check("saved DisableOTAFile keeps its OTA payload",
          (ota.get("value") or {}).get(
              "MobileAssetSUAllowOSVersionChange") is False,
          str(ota.get("value")))
    res = saved.get("tweaks", {}).get("CustomResolution", {})
    check("saved CustomResolution keeps canvas values",
          (res.get("value") or {}).get("canvas_width") == 1179
          and (res.get("value") or {}).get("canvas_height") == 2556,
          str(res.get("value")))

    # Muat kembali dari keadaan headless (instance Risky dibuang dulu):
    # inilah jalur yang dulu target-nya None lalu terlewat diam-diam.
    forget_risky()
    check("pre-load headless state has no OTA instance",
          TweakID.DisableOTAFile not in tweaks)
    check("load succeeds", pm.load_preset("Audit29") is True)
    check("load re-registers DisableOTAFile",
          TweakID.DisableOTAFile in tweaks)
    check("loaded DisableOTAFile is enabled again",
          tweaks[TweakID.DisableOTAFile].enabled is True)
    check("loaded DisableOTAFile was not recorded as skipped",
          all(s.get("tweak_id") != "DisableOTAFile"
              for s in pm.last_skipped), str(pm.last_skipped))
    check("loaded CustomResolution is enabled with its values",
          tweaks[TweakID.CustomResolution].enabled is True
          and tweaks[TweakID.CustomResolution].value.get(
              "canvas_width") == 1179)

    # AutoSave memakai save_preset/load_preset yang sama (GUI & CLI).
    disable_risky()
    forget_risky()
    tweak_loader.load_risky()
    tweaks[TweakID.DisableOTAFile].set_enabled(True)
    check("AutoSave save succeeds", pm.save_preset("AutoSave") is True)
    forget_risky()
    check("AutoSave load succeeds", pm.load_preset("AutoSave") is True)
    check("AutoSave round-trip restores DisableOTAFile enabled",
          tweaks.get(TweakID.DisableOTAFile) is not None
          and tweaks[TweakID.DisableOTAFile].enabled is True)
    disable_risky()


# =============================================================================
def test_gate_preserved(tmpdir):
    print("\ngerbang yang ada tidak dilemahkan oleh registrasi Risky")
    from src.tweaks.capabilities import tweak_deliverability
    ok_ota, code_ota, _ = tweak_deliverability(
        TweakID.DisableOTAFile, device_version="26.6.1",
        device_build="23G83")
    check("DisableOTAFile stays deliverable on the audited target",
          ok_ota and code_ota == "OK", code_ota)
    ok_eu, code_eu, _ = tweak_deliverability(
        TweakID.EUEnabler, device_version="26.6.1", device_build="23G83")
    check("a locked family is still locked on the same target",
          not ok_eu and code_eu != "OK", code_eu)

    pm = make_manager(tmpdir)
    # Preset jahat/campuran: OTA boleh masuk, EUEnabler (terkunci di
    # 26.6.1/23G83) harus ditolak tercatat, bukan menyala diam-diam.
    path = pm.get_preset_path("GateMix")
    with open(path, "w", encoding="utf-8") as f:
        # Format preset saat ini (v2) — Audit 43 menolak file tanpa
        # metadata.version; fixture ini menguji gate, bukan format lama.
        json.dump({"metadata": {"version": 2}, "tweaks": {
            "DisableOTAFile": {"type": "AdvancedPlistTweak",
                               "enabled": True, "value": {}},
            "EUEnabler": {"type": "EligibilityTweak", "enabled": True},
        }}, f)
    forget_risky()
    check("mixed preset loads",
          pm.load_preset("GateMix", device_build="23G83",
                         device_version="26.6.1",
                         device_model="iPhone15,3") is True)
    check("deliverable Risky tweak still applies under the gate",
          tweaks[TweakID.DisableOTAFile].enabled is True)
    eu = tweaks.get(TweakID.EUEnabler)
    check("locked tweak does not end up enabled",
          eu is None or eu.enabled is False)
    check("locked tweak is reported in last_skipped, not silent",
          any(s.get("tweak_id") == "EUEnabler" for s in pm.last_skipped),
          str(pm.last_skipped))
    disable_risky()


def main():
    tmpdir = tempfile.mkdtemp(prefix="audit29-presets-")
    test_code_paths()
    test_round_trip(tmpdir)
    test_gate_preserved(tmpdir)
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
