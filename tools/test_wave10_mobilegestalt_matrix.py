#!/usr/bin/env python3
"""MobileGestalt support boundary matrix + UI wording (user confirmation
2026-10-03).

Supported ONLY up to iOS 26.2 beta 1 (build 23C5027f inclusive); locked
from 26.2 beta 2 (23C5035e) onward — in the shared decision AND in every
user-facing text. No surface may claim "supported up to 26.2" without
the words "beta 1".

Run: QT_QPA_PLATFORM=offscreen ~/wsui-venv/bin/python \
    tools/test_wave10_mobilegestalt_matrix.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from src.devicemanagement.constants import mobilegestalt_decision  # noqa: E402

print("\ndecision matrix: boundary builds")
cases = [
    ("23C5027f", "26.2", True),    # 26.2 beta 1 — last supported (inclusive)
    ("23C5035e", "26.2", False),   # 26.2 beta 2 — lock starts here
    ("23C52", "26.2", False),      # 26.2 final
    ("23G82", "26.6.1", False),    # 26.6.1 RC
    ("23G83", "26.6.1", False),    # 26.6.1 final
    ("23A345", "26.0", True),      # older iOS still supported
    ("", "", False),               # unknown evidence: fail-closed
]
for build, version, supported in cases:
    decision = mobilegestalt_decision(build, version)
    check(f"{build or '(none)'} supported={supported}",
          decision.supported is supported,
          f"{decision.supported} {decision.reason_code}")

print("\nUI wording: 'beta 1' is never dropped")
root = os.path.join(os.path.dirname(__file__), "..", "src")
offenders = []
for dirpath, _dirs, files in os.walk(root):
    for fname in files:
        if not fname.endswith(".py") or fname == "resources_rc.py":
            continue
        path = os.path.join(dirpath, fname)
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for lineno, line in enumerate(fh, 1):
                if re.search(r"16\.0\s*[–—-]\s*26\.2(?!\s*beta)(?!b1)", line) or \
                        re.search(r"through iOS 26\.2(?!\s*beta)(?!b1)", line) or \
                        re.search(r"up to (iOS )?26\.2(?!\s*beta)(?!b1)", line):
                    offenders.append(f"{path}:{lineno}: {line.strip()}")
check("no 'supported to 26.2' text without 'beta 1'", not offenders,
      "; ".join(offenders))

print(f"\nALL {PASS} CHECKS PASSED")
