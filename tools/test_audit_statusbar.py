#!/usr/bin/env python3
"""Round-11 audit: Status Bar archive bridge.

* build_archive -> carrier_names round-trips both carriers;
* reset archive is recognized as a reset (never as data);
* UTF-8 truncation never splits a code point;
* the iOS 27 build gate helper separates 24-train builds.

Run: python tools/test_audit_statusbar.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.devicemanagement.constants import is_ios27_build
from src.tweaks.status_bar.status_bar_tweak import _truncate_utf8
from src.tweaks.status_bar.statusbar_archive import (
    build_archive, build_reset_archive, carrier_names, is_reset_archive,
    status_bar_data)

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-11: Status Bar")
    payload = build_archive(primary_carrier="Telkomsel",
                            secondary_carrier="XL")
    names = carrier_names(payload)
    check("carriers round-trip", names == ("Telkomsel", "XL"), str(names))
    check("archive carries status data", status_bar_data(payload) is not None)
    check("data archive is not a reset", not is_reset_archive(payload))

    reset = build_reset_archive()
    check("reset archive recognized", is_reset_archive(reset))
    check("reset archive has no carriers",
          carrier_names(reset) == (None, None))

    long_name = "é" * 40  # 2 bytes each in UTF-8
    out = _truncate_utf8(long_name, 31)
    check("utf8 truncation stays decodable and within budget",
          len(out) <= 31 and out.decode("utf-8") != "")

    check("24-train builds are iOS 27", is_ios27_build("24A340"))
    check("23G83 is not iOS 27", not is_ios27_build("23G83"))
    check("empty build is not iOS 27", not is_ios27_build(""))

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
