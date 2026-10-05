#!/usr/bin/env python3
"""Offline integration tests: DeviceManager LGD gate → divert (iOS 26.6.x).

Round-3 audit coverage: the LGD glue inside DeviceManager had no direct
test — the gate, the full-route window check and the sparse/record
split were only exercised indirectly. This builds a DeviceManager
without a device (``__new__`` + monkeypatched device getters) and the
real registry tweak instances, then walks:

* gate passes for honest staged G1+G2 records built through the real
  ``concat_file`` domain mapping;
* gate cancels (NuggetException) when the G1 record drops a device key;
* the full-route window is exact (26.6.1/23G82|23G83 only);
* the divert splits LGD records out of the sparse list.

Run: python tools/test_lgd_device_manager_integration.py
"""
import os
import plistlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.devicemanagement import device_manager as dm_mod
from src.devicemanagement.device_manager import DeviceManager
from src.exceptions.nugget_exception import NuggetException
from src.tweaks import lg_disable
from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.tweak_names import TweakID
from src.restore.lgd_full import payloads_from_staged_files

PASS = 0
KEY = lg_disable.GP_KEY
BASE = {"AppleLocale": "en_US", "AppleLanguages": ["en-US"], "Existing": 7}


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def _dm(version="26.6.1", build="23G83"):
    dm = object.__new__(DeviceManager)
    dm.get_current_device_version = lambda: version
    dm.get_current_device_build = lambda: build
    dm.get_current_device_udid = lambda: "TESTUDID"
    dm._lgd_g1_base = None
    return dm


def _stage(dm, g1_bytes=None, g2_bytes=None):
    files = []
    if g2_bytes is not None:
        dm.concat_file(contents=g2_bytes,
                       path=FileLocation.globalPreferences.value,
                       files_to_restore=files)
    if g1_bytes is not None:
        dm.concat_file(contents=g1_bytes,
                       path=FileLocation.globalPreferencesHomeDomain.value,
                       files_to_restore=files)
    return files


def main():
    print("\nDeviceManager LGD integration (offline)")
    # The live tweaks dict gains registry instances via tweak_loader at
    # runtime; here we instantiate the two LGD specs through their real
    # factories, exactly as the loader does.
    from src.tweaks.registry import SPECS_BY_ID
    g1 = SPECS_BY_ID[TweakID.LGDisableG1].factory()
    g2 = SPECS_BY_ID[TweakID.LGDisableG2].factory()
    dm_mod.tweaks[TweakID.LGDisableG1] = g1
    dm_mod.tweaks[TweakID.LGDisableG2] = g2
    g1.set_enabled(True)
    g2.set_enabled(True)
    g1.staged = True
    g2.staged = True

    dm = _dm()
    dm._lgd_g1_base = dict(BASE)
    g1_bytes = lg_disable.build_g1_payload(BASE, {KEY: True})
    g2_bytes = lg_disable.build_g2_payload({KEY: True})
    files = _stage(dm, g1_bytes, g2_bytes)
    check("concat_file maps both records to the LGD domains",
          {(f.domain, f.restore_path) for f in files} == {
              (lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH),
              (lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH)},
          str([(f.domain, f.restore_path) for f in files]))
    try:
        dm._lgd_verify_gate(files)
        gate_ok = True
    except NuggetException as exc:
        gate_ok = False
        print("   gate said:", exc)
    check("honest staged G1+G2 passes the DeviceManager gate", gate_ok)

    bad = _stage(dm, lg_disable.build_g1_payload(
        {"AppleLocale": "en_US"}, {KEY: True}), None)
    try:
        dm._lgd_verify_gate(bad)
        gate_ok = True
    except NuggetException:
        gate_ok = False
    check("gate cancels when the G1 record drops device keys", not gate_ok)

    check("full-route window: 26.6.1/23G83 active",
          dm._lgd_full_route_active())
    dm26 = _dm(build="23G90")
    check("full-route window: unknown build inactive",
          not dm26._lgd_full_route_active())
    dm27 = _dm(version="27.0", build="24A100")
    check("full-route window: iOS 27 inactive (own flow)",
          not dm27._lgd_full_route_active())

    remaining, payloads = payloads_from_staged_files(
        files, g1_active=True, g2_active=True)
    check("divert removes both LGD records from the sparse list",
          remaining == [] and len(payloads) == 2)
    parsed = {p[0]: plistlib.loads(p[2]) for p in payloads}
    check("diverted G1 payload still carries every base key",
          all(parsed[lg_disable.G1_DOMAIN].get(k) == v
              for k, v in BASE.items()))

    g1.set_enabled(False)
    g2.set_enabled(False)
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
