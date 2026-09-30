"""Animated terminal-style background for WorkSlop Desktop.

A lightweight, non-interactive backdrop: dim green terminal lines scroll
upward forever, with a very faint ASCII-art apple watermark in the center.
Only two QLabel widgets + one QTimer are used no matter how long it runs,
so it stays cheap.

Usage example (wiring is up to the caller)::

    from src.gui.ios.terminal_bg import TerminalBackground

    bg = TerminalBackground(self)          # any QWidget parent
    bg.set_opacity(0.6)                    # 0.0 .. 1.0 master opacity
    bg.lower()                             # sit behind the real content
    bg.start()                             # begin scrolling
    ...
    bg.stop()                              # pause when the page hides

Notes:
- The widget is transparent to mouse events (WA_TransparentForMouseEvents),
  so clicks pass straight through to whatever is on top of it.
- Background color follows the app theme (bg_primary); text stays a dim
  terminal green at low alpha so it never fights the foreground content.
"""

import random
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

try:
    from src.gui.theme import ColorThemeManager
except Exception:  # pragma: no cover - theme is optional for standalone use
    ColorThemeManager = None


# ~44 realistic terminal-ish lines; picked at random each tick.
SCROLL_LINES = (
    "$ workslop --apply --device auto",
    "$ workslop backup --full /mnt/iphone",
    "$ workslop --status => partially supported",
    "$ ideviceinstaller -i WorkSlop.ipa",
    ">>> connecting iphone... found (usb)",
    ">>> tweak engine ready (27 hooks)",
    ">>> gestalt query: ArtworkDeviceSubType = 2436",
    "[ok] lockdown handshake",
    "[ok] sparse restore done in 41.2s",
    "[ok] installed com.example.app (1/3)",
    "[ok] reboot issued, waiting for reconnect...",
    "[..] uploading manifest (3/12)",
    "[..] staging payload -> /tmp/staged/",
    "[!!] retrying AFC write (1/3)",
    "0x1a2b3c4d  0x55aa00ff  0xdeadbeef",
    "0xfffffff00761a2b0: patch applied",
    "sha256: 9f2c41be...a41b verified",
    "recv 1048576 bytes [████████░░] 82%",
    "recv 2097152 bytes [██████████] 100%",
    "mobilebackup2: session 7f3a started",
    "lockdownd: pairing record ok",
    "amfi: signature valid (adhoc)",
    "dyld: mapped 312 images",
    "SpringBoard: relaunching...",
    "backboardd: display link ok",
    "assertiond: job com.apple.frontboard alive",
    "plist: wrote 1842 bytes -> com.apple.UIKit.plist",
    "sqlite3 devices.db 'select * from backup'",
    "rsync -a --progress ./payload/ /tmp/staged/",
    "zsign: signing 42 mach-o slices",
    "openssl req -new -key dev.key -out dev.csr",
    "anisette: machine data provisioned",
    "grand slam: srp handshake ok (2048-bit)",
    "provisioning: fetched 3 profiles",
    "installation_proxy: 60% - VerifyingApplication",
    "misagent: installed provisioning profile",
    "com.apple.mobile.installation_proxy: Complete",
    "afc: wrote /var/mobile/Media/icon.png (12 KiB)",
    "house_arrest: vend container ok",
    "mobilegestalt: cache rebuilt",
    "nvram: boot-args updated",
    "usbmuxd: connected UDID 00008110-001A2B3C3D4E5F6",
    "reconnect: device back after 23s",
    "heartbeat: 12ms",
    "gc: freed 2048 objects",
    "watchdog: all threads nominal",
)

# Apple silhouette drawn from text characters only (no emoji).
# Rendered at very low opacity as a center watermark.
APPLE_ART = (
    r"                  #",
    r"                 ###",
    r"                #####",
    r"           #############",
    r"         #################",
    r"       #####################",
    r"      #######################",
    r"      #######################",
    r"      #######################",
    r"       #####################",
    r"       #####################",
    r"        ###################",
    r"         #################",
    r"          ###############",
    r"           #############",
    r"             #########",
    r"               #####",
)

MAX_LINES = 80          # hard cap: the deque never grows past this
TICK_MIN_MS = 60        # scroll speed range (ms per new line)
TICK_MAX_MS = 100
APPLE_TICK_MS = 50      # apple drift animation frame interval


class TerminalBackground(QWidget):
    """Dim scrolling terminal backdrop with a faint ASCII apple watermark."""

    def __init__(self, parent=None, opacity: float = 1.0):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._opacity = 1.0
        self._lines: deque = deque(maxlen=MAX_LINES)

        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(9)

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scrolling code: ONE label, multiline text. Cheap by design.
        self._scroll_lbl = QLabel(self)
        self._scroll_lbl.setFont(mono)
        self._scroll_lbl.setWordWrap(False)
        self._scroll_lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._scroll_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self._scroll_lbl, 0, 0)

        # Apple watermark: free-floating label (NOT in layout) so we can
        # animate its position. Centered manually, drifts slowly.
        self._apple_lbl = QLabel("\n".join(APPLE_ART), self)
        self._apple_lbl.setFont(mono)
        self._apple_lbl.setAlignment(Qt.AlignCenter)
        self._apple_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._apple_lbl.adjustSize()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        # Apple drift animation: slow floating movement.
        self._apple_phase = 0.0
        self._apple_timer = QTimer(self)
        self._apple_timer.timeout.connect(self._on_apple_tick)

        if ColorThemeManager is not None:
            try:
                ColorThemeManager.instance().theme_changed.connect(self._retheme)
            except Exception:
                pass
        self._retheme()
        self.set_opacity(opacity)
        # Pre-fill so the background never starts empty.
        for _ in range(24):
            self._lines.append(random.choice(SCROLL_LINES))
        self._render()

    # -- public API ------------------------------------------------------
    def start(self) -> None:
        """Begin (or resume) the scrolling animation."""
        if not self._timer.isActive():
            self._timer.start(random.randint(TICK_MIN_MS, TICK_MAX_MS))
        if not self._apple_timer.isActive():
            self._apple_timer.start(APPLE_TICK_MS)

    def stop(self) -> None:
        """Pause the scrolling animation."""
        self._timer.stop()
        self._apple_timer.stop()

    def is_running(self) -> bool:
        return self._timer.isActive()

    def set_opacity(self, value: float) -> None:
        """Master opacity multiplier, 0.0 (invisible) .. 1.0 (full dim)."""
        self._opacity = max(0.0, min(1.0, float(value)))
        self._apply_style()

    # -- internals -------------------------------------------------------
    def _on_tick(self) -> None:
        self._lines.append(random.choice(SCROLL_LINES))
        self._render()
        # Slightly varied pacing feels more like a real terminal.
        self._timer.setInterval(random.randint(TICK_MIN_MS, TICK_MAX_MS))

    def _on_apple_tick(self) -> None:
        """Slow drift: apple logo floats in a gentle Lissajous pattern."""
        import math
        self._apple_phase += 0.02
        dx = int(30 * math.sin(self._apple_phase))
        dy = int(20 * math.sin(self._apple_phase * 0.7))
        # Move via margin offset on the layout cell
        self._apple_lbl.move(
            (self.width() - self._apple_lbl.width()) // 2 + dx,
            (self.height() - self._apple_lbl.height()) // 2 + dy,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Keep apple centered (drift offset applied on next tick).
        self._apple_lbl.move(
            (self.width() - self._apple_lbl.width()) // 2,
            (self.height() - self._apple_lbl.height()) // 2,
        )

    def _render(self) -> None:
        self._scroll_lbl.setText("\n".join(self._lines))

    def _retheme(self) -> None:
        bg = "#000000"
        if ColorThemeManager is not None:
            try:
                bg = ColorThemeManager.instance().colors.bg_primary
            except Exception:
                pass
        self._bg = bg
        self._apply_style()

    def _apply_style(self) -> None:
        o = self._opacity
        # Terminal green for the scrolling text; faint for the
        # apple watermark. Both scale with the master opacity.
        text_alpha = int(110 * o)
        apple_alpha = int(32 * o)
        bg = getattr(self, "_bg", "#000000")
        self.setStyleSheet(f"background-color: {bg}; border: none;")
        self._scroll_lbl.setStyleSheet(
            f"color: rgba(0, 255, 120, {text_alpha});"
            " background-color: transparent; border: none;"
        )
        self._apple_lbl.setStyleSheet(
            f"color: rgba(0, 255, 120, {apple_alpha});"
            " background-color: transparent; border: none;"
        )
