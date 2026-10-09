#!/usr/bin/env python3
"""Audit 48: PosterBoard tendie thumbnails decode at card size.

The card shows an 80x80 center-crop. The old code decoded the full
image on the main thread and scaled down; the fixed code reads only
the header for dimensions and lets the decoder scale to the cover
size via QImageReader.setScaledSize. This test spies on the reader to
prove the scaled-decode path is used and the card still gets its
80x80 pixmap, and prints the decode timing both ways for the record.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit48_tendie_thumbnail.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402
from PySide6.QtGui import QImage, QImageReader  # noqa: E402
from PySide6.QtCore import QSize, Qt  # noqa: E402

app = QApplication.instance() or QApplication([])

import src.gui.ios.posterboard as pb  # noqa: E402

# Big synthetic "wallpaper preview": 3000x2000 solid PNG.
tmp = tempfile.mkdtemp(prefix="workslop-a48-")
path = os.path.join(tmp, "preview.png")
img = QImage(3000, 2000, QImage.Format_RGB32)
img.fill(Qt.GlobalColor.darkCyan)
assert img.save(path)

scaled_sizes = []
RealReader = pb.QImageReader


class SpyReader(RealReader):
    def setScaledSize(self, size):
        scaled_sizes.append((size.width(), size.height()))
        super().setScaledSize(size)


pb.QImageReader = SpyReader
try:
    page = pb.IOSPosterboardPage.__new__(pb.IOSPosterboardPage)
    label = QLabel()
    page._set_tendie_thumbnail(label, path)
finally:
    pb.QImageReader = RealReader

check("card pixmap present", not label.pixmap().isNull())
check("card pixmap is 80x80", label.pixmap().size() == QSize(80, 80),
      str(label.pixmap().size()))
check("decoder scaled while decoding", len(scaled_sizes) == 1,
      str(scaled_sizes))
if scaled_sizes:
    w, h = scaled_sizes[0]
    # Cover 80x80 from 3000x2000: factor max(80/3000, 80/2000)=0.04.
    check("scaled size is the cover size", (w, h) == (120, 80),
          f"{w}x{h}")

# Printed evidence (not a gate): old full-res decode vs scaled decode.
t0 = time.perf_counter()
full = QImageReader(path).read()
full_ms = (time.perf_counter() - t0) * 1000.0
t0 = time.perf_counter()
r = QImageReader(path)
r.setScaledSize(QSize(120, 80))
small = r.read()
scaled_ms = (time.perf_counter() - t0) * 1000.0
check("both decodes produced images", not full.isNull()
      and not small.isNull())
print(f"  info: full-res decode 3000x2000: {full_ms:.1f} ms; "
      f"scaled decode ->120x80: {scaled_ms:.1f} ms")

print(f"\nALL {PASS} CHECKS PASSED")
