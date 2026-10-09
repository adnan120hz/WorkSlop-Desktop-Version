#!/usr/bin/env python3
"""Fix Audit 15: an empty .tendies produced a false "Success!".

``load_tendie`` used to return ``None`` for an unreadable file and an
all-``None`` bundle for an empty / scene-less archive, so a caller
checking "did I get something back" could report success for a file
with nothing in it. Empty, non-zip and scene-less archives now raise
``TendieError`` naming the actual problem; a real scene archive still
loads, and MercuryPoster containers keep their documented ``None``
fallback.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit15_tendie_empty_honest.py
"""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from src.controllers.ca.tendie import TendieError, load_tendie  # noqa: E402

TMP = tempfile.mkdtemp(prefix="workslop-a15-")


def expect_error(name, path, *needles):
    try:
        result = load_tendie(path)
    except TendieError as exc:
        message = str(exc)
        check(name, all(n.lower() in message.lower() for n in needles),
              message)
        return
    check(name, False, f"returned {result!r} instead of raising")


print("\nempty / invalid archives are honest errors, never success")
zero = os.path.join(TMP, "zero.tendies")
open(zero, "wb").close()
expect_error("0-byte file raises, naming it empty", zero, "empty")

garbage = os.path.join(TMP, "garbage.tendies")
with open(garbage, "wb") as f:
    f.write(b"this is not a zip archive at all")
expect_error("non-zip file raises, naming it invalid", garbage,
             "not a valid")

empty_zip = os.path.join(TMP, "empty.tendies")
with zipfile.ZipFile(empty_zip, "w"):
    pass
expect_error("zip with no entries raises, naming it empty", empty_zip,
             "empty archive")

sceneless = os.path.join(TMP, "sceneless.tendies")
with zipfile.ZipFile(sceneless, "w") as zf:
    zf.writestr("readme.txt", "no scenes here")
    zf.writestr("poster/descriptor/info.plist", b"junk")
expect_error("zip with files but no valid scene raises", sceneless,
             "no valid scene")

print("\nthe documented fallbacks still behave")
mercury = os.path.join(TMP, "mercury.tendies")
with zipfile.ZipFile(mercury, "w") as zf:
    zf.writestr("com.apple.mercuryposter/thing.ca/main.caml", "<caml/>")
check("MercuryPoster container still returns None (preview fallback)",
      load_tendie(mercury) is None)

print("\nTendieError cannot be mistaken for a success value")
check("TendieError is an exception type, not a bundle",
      isinstance(TendieError, type) and issubclass(TendieError, Exception))

print(f"\nALL {PASS} CHECKS PASSED")
