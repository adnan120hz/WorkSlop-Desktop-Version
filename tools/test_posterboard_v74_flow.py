#!/usr/bin/env python3
"""Offline test for the Nugget v7.4 PosterBoard delivery (no device needed).

Adopted 2026-10-03 from leminlimez/Nugget v7.4 (tag v7.4, commit
26097697f5527f42c13ebd2e90ef0e1e5958da41): descriptors-first delivery.
Guards:

1. Default descriptors mode stages plain descriptor FILES under
   PRBPosterExtensionDataStore/61/Extensions/.../descriptors/ and ships
   NO sqlite, NO 0-byte -wal/-shm companions, and never calls the config
   manager's DB staging.
2. Opt-in configurations mode (use_configs) stages the DB + companions
   through the (stubbed) config manager.
3. Reset modes stage zero-byte folder records only — no database, ever.
4. Failure paths stay clean: a corrupt .tendies raises at import and a
   broken apply leaves nothing staged; disabled stages nothing.
5. apply-time structure_version comes from the OS version (61 on 26.x,
   59 on 16.x) without a fetched DB.

Run: python tools/test_posterboard_v74_flow.py
"""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tweaks.posterboard.posterboard_tweak import PosterboardTweak

PASS = 0
TMP = tempfile.mkdtemp(prefix="gn_pb_v74_")


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def make_tendie(name="test.tendies", payload=b"fake-wallpaper-payload"):
    """Minimal valid tendie: one descriptor folder with one payload file."""
    path = os.path.join(TMP, name)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("descriptor/TestWallpaper/", "")
        z.writestr("descriptor/TestWallpaper/payload.bin", payload)
    return path


def db_like(files):
    return [f for f in files
            if "PBFPosterExtensionDataStoreSQLiteDatabase" in f.restore_path
            or f.restore_path.endswith(("-wal", "-shm"))]


def test_descriptors_mode_stages_files_not_db():
    print("\nDescriptors mode (default): files staged, no database anywhere")
    tweak = PosterboardTweak()
    check("descriptors is the default mode", tweak.use_configs is False)
    calls = []
    tweak.config_manager.update_sqlite = lambda: calls.append("db") or "unused"
    tweak.config_manager.start_staging = lambda: calls.append("staging")
    assert tweak.add_tendie(make_tendie())
    files = []
    tweak.apply_tweak(files_to_restore=files,
                       output_dir=os.path.join(TMP, "out_desc"),
                       templates=[], version="26.6.1",
                       force_pb_refresh=False)
    check("descriptor payload was staged", len(files) >= 1, f"staged={len(files)}")
    paths = [f.restore_path for f in files]
    check("staged under the 61 descriptor store",
          all("/61/Extensions/" in p and "/descriptors/" in p for p in paths),
          str(paths))
    check("no sqlite/-wal/-shm staged in descriptors mode", not db_like(files))
    check("config manager DB staging never ran", not calls, str(calls))
    check("all staged into the PosterBoard app domain",
          all(f.domain == "AppDomain-com.apple.PosterBoard" for f in files))


def test_reset_modes_stage_zero_folders_only():
    print("\nReset: zero-byte folder records, no database")
    tweak = PosterboardTweak()
    tweak.resetModes = ["Collections", "Gallery Cache"]
    files = []
    tweak.apply_tweak(files_to_restore=files,
                       output_dir=os.path.join(TMP, "out_reset"),
                       templates=[], version="26.6.1",
                       force_pb_refresh=False)
    check("reset staged records", len(files) == 3, f"staged={len(files)}")
    check("all reset records are zero-byte",
          all(f.contents == b"" for f in files))
    check("reset touches no database", not db_like(files))


def test_configurations_mode_stages_db_with_companions():
    print("\nConfigurations mode (opt-in): DB + 0-byte companions staged")
    tweak = PosterboardTweak()
    tweak.use_configs = True
    staged = os.path.join(TMP, "staged.sqlite3")
    with open(staged, "wb") as fp:
        fp.write(b"sqlite-stub")
    tweak.config_manager.start_staging = lambda: None
    tweak.config_manager.update_sqlite = lambda: staged
    assert tweak.add_tendie(make_tendie("cfg.tendies"))
    files = []
    tweak.apply_tweak(files_to_restore=files,
                       output_dir=os.path.join(TMP, "out_cfg"),
                       templates=[], version="26.6.1",
                       force_pb_refresh=False)
    dbs = db_like(files)
    mains = [f for f in dbs if f.restore_path.endswith(".sqlite3")]
    check("DB main file staged exactly once", len(mains) == 1,
          str([f.restore_path for f in dbs]))
    walls = [f for f in dbs if f.restore_path.endswith("-wal")]
    shms = [f for f in dbs if f.restore_path.endswith("-shm")]
    check("main DB from the staged copy", len(mains) == 1
          and mains[0].contents_path == staged)
    check("0-byte -wal companion", len(walls) == 1 and walls[0].contents == b"")
    check("0-byte -shm companion", len(shms) == 1 and shms[0].contents == b"")
    check("descriptors go to configurations/ in this mode",
          any("/configurations/" in f.restore_path for f in files
              if "/Extensions/" in f.restore_path))


def test_failure_paths_stage_nothing():
    print("\nFailure paths: corrupt input fails clean, nothing staged")
    corrupt = os.path.join(TMP, "broken.tendies")
    with open(corrupt, "wb") as fp:
        fp.write(b"this is not a zip archive")
    tweak = PosterboardTweak()
    raised = False
    try:
        tweak.add_tendie(corrupt)
    except Exception:
        raised = True
    check("corrupt tendie rejected at import", raised)
    check("rejected tendie not queued", tweak.tendies == [])

    # A tendie that breaks during apply: nothing may reach the restore list.
    tweak2 = PosterboardTweak()
    assert tweak2.add_tendie(make_tendie("boom.tendies"))
    boom_out = os.path.join(TMP, "boom_out")

    def explode(output_dir):
        raise RuntimeError("stubbed extract failure")
    tweak2.tendies[0].extract = explode
    files = []
    raised = False
    try:
        tweak2.apply_tweak(files_to_restore=files, output_dir=boom_out,
                           templates=[], version="26.6.1",
                           force_pb_refresh=False)
    except RuntimeError:
        raised = True
    check("apply surfaces the extract failure", raised)
    check("nothing staged after the failure", files == [])

    tweak3 = PosterboardTweak()
    tweak3.disabled = True
    assert tweak3.add_tendie(make_tendie("off.tendies"))
    files = []
    tweak3.apply_tweak(files_to_restore=files,
                        output_dir=os.path.join(TMP, "out_off"),
                        templates=[], version="26.6.1",
                        force_pb_refresh=False)
    check("disabled stages nothing", files == [])


def test_structure_version_from_os_not_db():
    print("\nStructure version comes from the OS version (no DB fetch)")
    for ver, expect in (("26.6.1", 61), ("16.7", 59)):
        tweak = PosterboardTweak()
        assert tweak.add_tendie(make_tendie(f"v{expect}.tendies"))
        files = []
        tweak.apply_tweak(files_to_restore=files,
                           output_dir=os.path.join(TMP, f"out_v{expect}"),
                           templates=[], version=ver,
                           force_pb_refresh=False)
        check(f"iOS {ver} uses store version {expect}",
              all(f"/{expect}/Extensions/" in f.restore_path for f in files))


if __name__ == "__main__":
    test_descriptors_mode_stages_files_not_db()
    test_reset_modes_stage_zero_folders_only()
    test_configurations_mode_stages_db_with_companions()
    test_failure_paths_stage_nothing()
    test_structure_version_from_os_not_db()
    print(f"\nALL {PASS} CHECKS PASSED")
