"""Final 50-agent audit (rounds 21-25, 2026-10-05): regression checks for
the verified fix batch.

Pins:
- HotLoad FEATURE_TWEAKS merges sections that share one feature name
  (the "Liquid Glass" dict-overwrite dropped the whole v4 set).
- G2 rollback refuses honestly when a captured managed original is
  unreadable, and the empty-overlay fallback is a BINARY plist.
- verify_injected_payloads enforces the G1 candidate key on disk.
- Device-path mapping rejects '..' segments.
- CLI value coercion writes real types (bool/number), never raw strings.
- Protective helpers: session-root upload names and env edge values.
- LGD pool prune drops stale incomplete runs but keeps fresh ones.
- version.txt (Windows exe metadata) tracks App_Version.

Run:  python tools/test_audit_final50.py
"""
import os
import plistlib
import sys
import tempfile
import time
from pathlib import Path

for _k in ("WORKSLOP_APP_DATA", "XDG_DATA_HOME"):
    os.environ.pop(_k, None)
_TMP = tempfile.mkdtemp(prefix="final50-")
os.environ["GOLDENNUGGET_BACKUP_DIR"] = _TMP
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CHECKS = [0]


def check(label, cond):
    CHECKS[0] += 1
    if not cond:
        print(f"FAIL: {label}")
        sys.exit(1)
    print(f"  ok: {label}")


print("[1] HotLoad feature membership (round 21/24 HIGH)")
from src.controllers.hotload import FEATURE_TWEAKS
from src.tweaks.registry import SPECS_BY_SECTION, Section

lg = FEATURE_TWEAKS["Liquid Glass"]
v4 = [s.id.name for s in SPECS_BY_SECTION[Section.LIQUID_GLASS]]
check("all 32 Liquid Glass v4 specs are members", all(n in lg for n in v4))
check("Squair/Latest are members; removed G1/G2 are not",
      "LGDisableSquairTest" in lg and "LGDisableLatest" not in lg
      and "LGDisableG1" not in lg and "LGDisableG2" not in lg)
check("no duplicate members", len(lg) == len(set(lg)))

print("[2] LGD rollback planning (v14.0: fresh-capture planners)")
# The G1/G2 rollback planners left the product with the Beta 1 tweaks
# in v14.0; rollback planning for the surviving payloads is covered by
# tools/test_lg_squair_protocol.py and tools/test_lg_latest_protocol.py.
from src.tweaks import lg_latest

payloads, _note = lg_latest.plan_latest_rollback_payloads(
    {"SBDisallowGlassTime": True, "KeepMe": 1})
check("Latest rollback keeps non-payload keys",
      plistlib.loads(payloads[0][2]).get("KeepMe") == 1)
check("Latest rollback strips exactly its own keys",
      "SBDisallowGlassTime" not in plistlib.loads(payloads[0][2]))

print("[3] disk gate enforces the candidate key when asked (round 21 LOW)")
import sqlite3

from src.restore import lgd_full as lf
from src.restore.inject import inject_files_into_backup
from src.tweaks import lg_disable

backup_root = Path(_TMP) / "bkup"
udid = "UDID1"
dev_dir = backup_root / udid
dev_dir.mkdir(parents=True)
conn = sqlite3.connect(dev_dir / "Manifest.db")
conn.execute("CREATE TABLE Files (fileID TEXT, domain TEXT, "
             "relativePath TEXT, flags INTEGER, file BLOB)")
conn.commit()
conn.close()


def _payload(content):
    import stat as _stat
    return [(lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH, content,
             _stat.S_IFREG | 0o644, 501, 501)]


base = {"Existing": 1, "SolariumForceFallback": False}

# payload WITHOUT the candidate key must fail the disk gate now
no_key = plistlib.dumps({"Existing": 1}, fmt=plistlib.FMT_BINARY)
problems = lf.verify_injected_payloads(
    str(backup_root), udid, _payload(no_key), g1_base=base,
    expect_candidate_key=True)
# write the payload disk file the gate expects
inject_files_into_backup(str(backup_root), udid, _payload(no_key))
problems = lf.verify_injected_payloads(
    str(backup_root), udid, _payload(no_key), g1_base=base,
    expect_candidate_key=True)
check("G1 payload without candidate key fails disk gate",
      any("G1" in p and "SolariumForceFallback" in p for p in problems))

with_key = plistlib.dumps({"Existing": 1, "SolariumForceFallback": True},
                          fmt=plistlib.FMT_BINARY)
inject_files_into_backup(str(backup_root), udid, _payload(with_key))
problems = lf.verify_injected_payloads(
    str(backup_root), udid, _payload(with_key), g1_base=base,
    g1_allowed_new=(), expect_candidate_key=True)
check("G1 payload with real bool true passes disk gate", problems == [])

print("[4] path mapping rejects '..' (round 22 LOW)")
from src.restore.path_mapping import split_path_into_domain

try:
    split_path_into_domain("/var/mobile/../../etc/passwd")
    check("'..' segment rejected", False)
except ValueError:
    check("'..' segment rejected", True)
check("normal path still maps",
      split_path_into_domain("/var/mobile/Library/x.plist") == (
          "HomeDomain", "Library/x.plist"))

print("[5] CLI value coercion (round 23)")
from src.cli.cmd_tweaks import _coerce_cli_value
from src.tweaks.registry import SPECS_BY_ID
from src.tweaks.tweak_names import TweakID

spec = SPECS_BY_ID[TweakID.LGDisableSquairTest]
v, err = _coerce_cli_value(spec, "false")
check('switch "false" -> real False', v is False and err is None)
v, err = _coerce_cli_value(spec, "banana")
check("switch garbage -> error", v is None and err)
num_spec = next(s for s in SPECS_BY_ID.values()
                if str(s.kind) == "Kind.NUMBER" or s.kind.name == "NUMBER")
v, err = _coerce_cli_value(num_spec, "5")
check("number coerced to numeric type", isinstance(v, (int, float)))
v, err = _coerce_cli_value(num_spec, "abc")
check("number garbage -> error", v is None and err)

print("[6] protective helpers (round 22)")
from src.restore import protective as prot

check("session-root upload name does not crash",
      prot._device_tree_name("/.b/1") in ("1", ""))
os.environ["GOLDENNUGGET_MIN_FREE_GB"] = "inf"
check("env 'inf' falls back to default threshold",
      prot._min_free_disk_bytes() == int(prot.MIN_FREE_DISK_GB * (1024 ** 3)))
del os.environ["GOLDENNUGGET_MIN_FREE_GB"]

print("[7] LGD pool stale-incomplete prune (round 21 LOW)")
base = lf.lgd_backup_base(udid)
base.mkdir(parents=True, exist_ok=True)
stale = base / "20000101-000000-1-stale"
stale.mkdir()
fresh = base / "20990101-000000-1-fresh"
fresh.mkdir()
old_ts = time.time() - 8 * 24 * 3600
os.utime(stale, (old_ts, old_ts))
removed = lf.prune_lgd_backups(udid)
check("stale incomplete run pruned", removed >= 1 and not stale.exists())
check("fresh incomplete run kept", fresh.exists())

print("[8] version.txt tracks App_Version (round 25)")
from src.version import App_Version

text = (REPO / "version.txt").read_text()
check("FileVersion is current", f"u'{App_Version}.0'" in text)
check("tuple starts with current major",
      f"filevers=({App_Version.split('.')[0]}," in text)

print(f"\nALL {CHECKS[0]} CHECKS PASSED (final 50-agent fix regression)")
