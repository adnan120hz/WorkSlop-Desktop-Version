#!/usr/bin/env python3
"""Round-13 audit: update checker parsing/selection + CLI surface.

* version parsing strips exactly one leading v, ignores +build,
  rejects garbage (the "always says update available" class);
* release parsing skips drafts, flags invalid tags, marks prereleases;
* selection is deterministic (highest version wins);
* the CLI builds its full subcommand surface (--help exits clean).

Run: python tools/test_audit_updates_cli.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from packaging.version import Version

from src.controllers import web_request_handler as wrh

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-13: updates + CLI")
    check("v-prefix stripped once", wrh._public_version("v12") == Version("12"))
    check("build suffix ignored", wrh._public_version("12+0") == Version("12"))
    check("garbage rejected", wrh._public_version("beta-one") is None)
    check("empty rejected", wrh._public_version("") is None)

    info, invalid = wrh._parse_release(
        {"tag_name": "v12", "prerelease": True, "draft": False,
         "assets": [{"name": "a.zip", "size": 3}]}, "beta")
    check("release parses with assets", info is not None
          and info.version == "12" and info.assets[0]["size"] == 3
          and not invalid)
    check("prerelease flagged", info.prerelease is True)
    info, invalid = wrh._parse_release({"tag_name": "v9", "draft": True},
                                       "stable")
    check("drafts skipped", info is None and not invalid)
    info, invalid = wrh._parse_release({"tag_name": "nightly"}, "stable")
    check("non-version tag flagged invalid", info is None and invalid)
    info, invalid = wrh._parse_release({"tag_name": "vv12"}, "stable")
    check("double-v tag stays invalid", info is None and invalid)
    info, invalid = wrh._parse_release({"name": "no tag"}, "stable")
    check("missing tag flagged invalid", info is None and invalid)

    a, _ = wrh._parse_release({"tag_name": "v11", "published_at": "2026-01-02"},
                              "stable")
    b, _ = wrh._parse_release({"tag_name": "v12", "published_at": "2026-01-01"},
                              "stable")
    check("highest version wins selection", wrh._select([a, b]) is b)
    check("empty selection is None", wrh._select([]) is None)
    check("channel normalized", wrh.normalize_channel("junk") == "stable"
          and wrh.normalize_channel("beta") == "beta")

    proc = subprocess.run(
        [sys.executable, "-m", "src.cli.main", "--help"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        capture_output=True, text=True, timeout=120)
    check("CLI --help exits clean", proc.returncode == 0,
          proc.stderr[-200:] if proc.returncode else "")
    for cmd in ("apply", "reset", "tweaks", "preset", "devices", "daemons", "hotload"):
        check(f"CLI exposes {cmd}", cmd in proc.stdout)

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
