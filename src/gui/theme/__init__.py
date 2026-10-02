from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from src.gui.theme.theme_manager import ColorThemeManager
from src.gui.theme.colors import DARK, SKY, WORKBENCH, WS_BLUE, ACCENT_PRESETS
from src.gui.theme.styles import STYLES, FONT_FAMILY, mono_family
from src.gui.theme.accent_picker import AccentPicker


def t(style_key: str) -> str:
    """Render a named stylesheet template with the current theme colors."""
    payload = dict(ColorThemeManager.instance().colors.__dict__)
    payload["font_family"] = mono_family()
    return STYLES[style_key].format_map(payload)


def themed_stylesheet(style_key: str, **extra) -> str:
    """Render a stylesheet template with the current colors plus runtime
    extras (e.g. a generated caret image path passed as ``caret=...``)."""
    payload = dict(ColorThemeManager.instance().colors.__dict__)
    payload["font_family"] = mono_family()
    payload.update(extra)
    return STYLES[style_key].format_map(payload)


def theme_icon(resource_path: str, color_hex: str) -> QIcon:
    """Recolor a monochrome (white) SVG icon to *color_hex* using its alpha."""
    img = QImage(resource_path)
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(img.rect(), QColor(color_hex))
    painter.end()
    return QIcon(QPixmap.fromImage(img))


def theme_pixmap(resource_path: str, color_hex: str, size: int,
                 dpr: float = 1.0) -> QPixmap:
    """Rasterize a monochrome SVG at *size* logical pixels, tinted to a color.

    The SVG is scaled to *fit* the square (aspect ratio preserved, centered)
    via QSvgRenderer — never stretched. ``dpr`` renders extra device pixels
    on HiDPI screens and sets the pixmap's device pixel ratio accordingly.
    """
    scale = max(1.0, float(dpr))
    px = int(round(size * scale))
    pm = QPixmap(px, px)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    # Fit the viewBox into the square, centered, keeping the aspect ratio.
    # (QIcon.pixmap() also keeps aspect, but drawPixmap(rect, pixmap) would
    # stretch the result to fill the square — that squished the 3:4 Apple
    # logo ~33% wider.)
    renderer = QSvgRenderer(resource_path)
    vb = renderer.viewBoxF()
    if vb.isValid() and vb.width() > 0 and vb.height() > 0:
        s = min(size / vb.width(), size / vb.height())
        w, h = vb.width() * s, vb.height() * s
        target = QRectF((size - w) / 2.0, (size - h) / 2.0, w, h)
    else:
        target = QRectF(0, 0, size, size)
    renderer.render(painter, target)
    painter.setCompositionMode(
        QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pm.rect(), QColor(color_hex))
    painter.end()
    return pm


__all__ = [
    "ColorThemeManager", "DARK", "SKY", "WORKBENCH", "WS_BLUE", "ACCENT_PRESETS", "STYLES", "FONT_FAMILY",
    "AccentPicker", "t", "themed_stylesheet", "theme_icon",
    "theme_pixmap",
]
