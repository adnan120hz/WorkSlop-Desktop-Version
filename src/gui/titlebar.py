"""OS window title-bar theming.

The window's own title bar belongs to the OS, not to Qt, so it cannot be
reached with stylesheets. On Windows it can be flipped between the light
and dark immersive title bar through DWM
(``DwmSetWindowAttribute`` with ``DWMWA_USE_IMMERSIVE_DARK_MODE``); the
app uses that so the third interface (Full Nugget, dark) gets a dark
title bar and the other two interfaces restore the light one.

Other platforms have no supported per-window title-bar color API from
here (macOS ties it to the system appearance, Linux to the window
manager), so the call is a best-effort no-op there and returns False;
the in-app chrome still follows the interface on every platform.
"""
import sys

from src.gui.ios.theme_manager import ThemeManager

# DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 2004+ / Windows 11).
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20


def titlebar_dark_for_theme(theme: int) -> bool:
    """Pure mapping: only the Full Nugget interface gets a dark OS
    title bar; WorkSlop (Main) and WorkSlop 2 keep the light one."""
    return theme == ThemeManager.FULL_NUGGET


def apply_os_titlebar_dark(window, dark: bool) -> bool:
    """Set the OS title bar dark/light for *window* where the platform
    allows it. Returns True when the attribute was applied (Windows),
    False on other platforms or when the handle is not available yet
    (e.g. an offscreen render, where there is no native title bar)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        hwnd = int(window.winId())
        if not hwnd:
            return False
        value = ctypes.c_int(1 if dark else 0)
        hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value))
        return hr == 0
    except Exception:
        return False
