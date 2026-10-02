import math
import re

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QTime, QDate, QTimer, QPropertyAnimation,
    QEasingCurve, Property,
)
from PySide6.QtGui import (
    QPainter, QPainterPath, QColor, QFont, QPen, QPixmap, QLinearGradient,
    QPolygonF,
)
from PySide6.QtWidgets import QWidget

_BEZEL = QColor(0x1C, 0x1C, 0x1E)
_SCREEN_BG = QColor(0x0B, 0x0B, 0x0C)
_DATE_TEXT = QColor(0xDD, 0xDD, 0xDE, 235)
_HOME_DIM = QColor(0x00, 0x00, 0x00, 30)
_DOCK_BG = QColor(0xFF, 0xFF, 0xFF, 64)
_HINT = QColor(0xFF, 0xFF, 0xFF, 150)


def notch_type_for_product(product_type) -> str:
    """Map an iOS ProductType (e.g. "iPhone14,5") to a screen-cutout kind.

    - iPhone 11 (iPhone12,*) / iPhone 12 (iPhone13,*) -> "notch_large"
    - iPhone 13 (iPhone14,2-14,5), iPhone 14/Plus (iPhone14,7/14,8),
      SE 2022 (iPhone14,6) -> "notch_small"
    - iPhone 14 Pro/Max (iPhone15,2/15,3), iPhone 15 (iPhone15,4/15,5,
      iPhone16,1/16,2), iPhone 16 (iPhone17,*), iPhone 17 (iPhone18,*)
      -> "island"
    - Unknown / no device -> "island" (modern fallback)
    """
    if not product_type:
        return "island"
    match = re.match(r"\s*iPhone(\d+),(\d+)", str(product_type))
    if not match:
        return "island"
    major = int(match.group(1))
    if major >= 15:
        return "island"
    if major == 14:
        return "notch_small"
    if major in (12, 13):
        return "notch_large"
    return "island"


# Home-screen app grid (label, glyph kind). Glyphs are drawn with QPainter
# in _paint_app_icon — simple original shapes, no Apple artwork.
_HOME_GRID_APPS = [
    ("Calendar", "calendar"), ("Photos", "photos"),
    ("Camera", "camera"), ("Mail", "mail"),
    ("Clock", "clock"), ("Maps", "maps"),
    ("Weather", "weather"), ("Notes", "notes"),
    ("Reminders", "reminders"), ("App Store", "appstore"),
    ("Settings", "settings"), ("Wallet", "wallet"),
    ("Health", "health"), ("Files", "files"),
    ("Calculator", "calculator"), ("FaceTime", "facetime"),
    ("TV", "tv"), ("Stocks", "stocks"),
    ("Home", "home"), ("News", "news"),
]
_DOCK_APPS = [
    ("Phone", "phone"), ("Safari", "safari"),
    ("Messages", "messages"), ("Music", "music"),
]

# Real iPhone 15 / 15 Pro display: 393x852 pt at @3x (1179x2556 native px).
DEVICE_PT_W = 393
DEVICE_PT_H = 852
DEVICE_SCALE = 3
_MAX_CA_EDGE = DEVICE_PT_H * DEVICE_SCALE


class PhoneFrame(QWidget):

    SCREEN_ASPECT = 19.5 / 9.0

    def __init__(self, parent=None, show_chrome=True):
        super().__init__(parent)
        self._pixmap = None
        self._placeholder = ""
        self._time = QTime.currentTime()
        self._date = QDate.currentDate()
        self._show_chrome = show_chrome

        self._ca_renderer = None
        self._ca_home_renderer = None
        self._ca_loop = 0.0
        self._ca_elapsed = 0.0
        self._ca_pixmap = None
        self._ca_transition = None
        self._ca_timer = QTimer(self)
        self._ca_timer.setInterval(33)
        self._ca_timer.timeout.connect(self._advance_ca)

        self._progress = 0.0
        self._drag_y = None
        self._drag_progress = 0.0
        self._anim = QPropertyAnimation(self, b"unlock_progress", self)
        self._anim.setDuration(420)
        # Screen cutout follows the detected device (see
        # notch_type_for_product); Dynamic Island until a device says
        # otherwise.
        self._notch_type = "island"
        self._product_type = ""

        self.setMinimumSize(120, 240)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def device_pixel_size(self):
        """Native screen pixel size of the represented iPhone (e.g. 1179x2556)."""
        return (DEVICE_PT_W * DEVICE_SCALE, DEVICE_PT_H * DEVICE_SCALE)

    def set_wallpaper(self, pixmap, live_clock: bool = True):
        self._stop_ca()
        if pixmap is None or pixmap.isNull():
            self._pixmap = None
        else:
            self._pixmap = pixmap
        if live_clock:
            self._time = QTime.currentTime()
        self.update()

    def set_ca_scene(self, renderer, loop_seconds: float, home_renderer=None):
        self._stop_ca()
        self._pixmap = None
        self._ca_renderer = renderer
        self._ca_home_renderer = home_renderer
        self._ca_loop = float(loop_seconds or 0.0)
        self._ca_elapsed = 0.0
        self._ca_pixmap = None
        if renderer is not None:
            self._render_ca_frame()
            if self._ca_loop > 0.5:
                self._ca_timer.start()
        self.update()

    def set_ca_transition(self, renderer, transition):
        self._stop_ca()
        self._pixmap = None
        self._ca_renderer = renderer
        self._ca_transition = tuple(transition)
        self._ca_elapsed = 0.0
        self._ca_pixmap = None
        if renderer is not None:
            self._render_ca_frame()
        self.update()

    def _stop_ca(self):
        self._ca_timer.stop()
        self._ca_renderer = None
        self._ca_home_renderer = None
        self._ca_loop = 0.0
        self._ca_transition = None
        self._ca_pixmap = None

    def _render_transition_frame(self, transition, progress: float):
        from_state, to_state = transition[0], transition[1]
        return self._ca_renderer.render_state_transition(
            from_state, to_state, max(0.0, min(1.0, progress)))

    def _render_ca_frame(self) -> float:
        if self._ca_renderer is None:
            return 0.0
        import time as _time
        started = _time.monotonic()
        if self._ca_transition:
            img = self._render_transition_frame(
                self._ca_transition, self._progress)
        else:
            renderer = self._ca_renderer
            if self._progress >= 1.0 and self._ca_home_renderer is not None:
                renderer = self._ca_home_renderer
            start = self._ca_elapsed
            if self._ca_loop > 0.5:
                start %= self._ca_loop
            img = renderer.render(start * 1000.0)
            self._ca_elapsed += self._ca_timer.interval() / 1000.0
        if img is not None and not img.isNull():
            long_edge = max(img.width(), img.height())
            if long_edge > _MAX_CA_EDGE:
                scale = _MAX_CA_EDGE / long_edge
                img = img.scaled(
                    max(1, int(img.width() * scale)),
                    max(1, int(img.height() * scale)),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
            self._ca_pixmap = QPixmap.fromImage(img)
        return (_time.monotonic() - started) * 1000.0

    def _advance_ca(self):
        took_ms = self._render_ca_frame()
        self.update()
        desired = 33
        if 30 < took_ms < 1000:
            desired = max(33, int(took_ms * 1.5))
        if self._ca_timer.interval() != desired:
            self._ca_timer.stop()
            self._ca_timer.setInterval(desired)
            self._ca_timer.start()

    def set_placeholder(self, text: str = ""):
        self._placeholder = text
        self._pixmap = None
        self.update()

    def set_live_clock(self, live: bool):
        self._show_chrome = live
        self.update()

    # -- device-matched frame -------------------------------------------------
    @property
    def notch_type(self) -> str:
        """Current screen cutout: "island", "notch_small" or "notch_large"."""
        return self._notch_type

    @property
    def product_type(self) -> str:
        return self._product_type

    def set_product_type(self, product_type: str):
        """Match the frame cutout to a detected device ProductType."""
        self._product_type = str(product_type or "")
        new_type = notch_type_for_product(self._product_type)
        if new_type != self._notch_type:
            self._notch_type = new_type
        self.update()

    def show_home_screen(self, animated: bool = False):
        """Show the (real) home screen instead of the lock screen."""
        if animated:
            self._animate_to(1.0)
        else:
            self._anim.stop()
            self._progress = 1.0
            self.update()

    @property
    def showing_home_screen(self) -> bool:
        return self._progress >= 0.99

    def relock(self, animated: bool = True):
        self._drag_y = None
        if animated and self._progress > 0.0:
            self._animate_to(0.0)
        else:
            self._progress = 0.0
            self.update()

    def _get_progress(self):
        return self._progress

    def _set_progress(self, value):
        self._progress = max(0.0, min(1.0, value))
        if self._ca_transition is not None:
            self._render_ca_frame()
        self.update()

    unlock_progress = Property(float, _get_progress, _set_progress)

    def _animate_to(self, target: float):
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(
            QEasingCurve.Type.OutCubic if target > self._progress
            else QEasingCurve.Type.InOutCubic)
        self._anim.start()

    def _screen_rect(self):
        w = self.width()
        h = self.height()
        inset_x = max(7.0, w * 0.045)
        inset_y = max(8.0, h * 0.032)
        return QRectF(inset_x, inset_y, w - 2 * inset_x, h - 2 * inset_y)

    def _clock_font(self, size_pt):
        f = QFont()
        f.setPointSizeF(size_pt)
        f.setWeight(QFont.Weight.DemiBold)
        return f

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._anim.stop()
            self._drag_y = event.position().y()
            self._drag_progress = self._progress
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_y is None:
            super().mouseMoveEvent(event)
            return
        dy = event.position().y() - self._drag_y
        self._set_progress(self._drag_progress - dy / max(1.0, self.height()))
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_y is None:
            super().mouseReleaseEvent(event)
            return
        dy = event.position().y() - self._drag_y
        start_y = self._drag_y
        self._drag_y = None
        moved = abs(event.position().y() - start_y)
        if moved < 8:
            if self._progress >= 0.99:
                self._animate_to(0.0)
        elif self._progress > 0.33:
            self._animate_to(1.0)
        else:
            self._animate_to(0.0)
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(0, 0, self.width(), self.height())
        screen = self._screen_rect()
        radius = min(screen.width(), screen.height()) * 0.14

        # Outer silver edge, then the thin black bezel, then the screen.
        outer = QPainterPath()
        outer.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5),
                             radius + 6, radius + 6)
        silver = QLinearGradient(rect.topLeft(), rect.bottomRight())
        silver.setColorAt(0.0, QColor(0xF2, 0xF4, 0xF6))
        silver.setColorAt(0.5, QColor(0xB9, 0xBE, 0xC4))
        silver.setColorAt(1.0, QColor(0xE3, 0xE6, 0xEA))
        painter.fillPath(outer, silver)
        bezel_rect = rect.adjusted(2.5, 2.5, -2.5, -2.5)
        bezel = QPainterPath()
        bezel.addRoundedRect(bezel_rect, radius + 4, radius + 4)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, _BEZEL.lighter(116))
        gradient.setColorAt(0.5, _BEZEL)
        gradient.setColorAt(1.0, _BEZEL.darker(118))
        painter.fillPath(bezel, gradient)

        clip = QPainterPath()
        clip.addRoundedRect(screen, radius, radius)
        painter.save()
        painter.setClipPath(clip)
        try:
            painter.fillRect(screen, _SCREEN_BG)
            if self._pixmap is not None or self._ca_pixmap is not None:
                self._paint_wallpaper(painter, screen)
            else:
                self._paint_placeholder(painter, screen)

            t = self._progress
            if t > 0.0:
                self._paint_home_screen(painter, screen, t)
            if self._show_chrome and t < 1.0:
                self._paint_lockscreen_chrome(painter, screen, t)
        finally:
            painter.restore()

        # Screen cutout (Dynamic Island or notch, per detected device),
        # always on top of the screen.
        self._paint_cutout(painter, screen)
        painter.end()

    def _paint_cutout(self, painter, screen: QRectF):
        """Draw the screen cutout that matches the detected device."""
        painter.setPen(Qt.NoPen)
        if self._notch_type == "island":
            island_w = screen.width() * 0.34
            island_h = max(7.0, screen.height() * 0.026)
            island = QRectF(screen.center().x() - island_w / 2,
                            screen.top() + screen.height() * 0.018,
                            island_w, island_h)
            painter.setBrush(QColor(0x05, 0x05, 0x06))
            painter.drawRoundedRect(island, island_h / 2, island_h / 2)
            cam_r = island_h * 0.16
            painter.setBrush(QColor(0x1D, 0x2A, 0x3A))
            painter.drawEllipse(
                island.right() - island_h * 0.85, island.center().y() - cam_r,
                cam_r * 2, cam_r * 2)
            return

        # Notch: black tab hanging from the top edge, rounded bottom
        # corners, speaker slot + camera inside. The large notch
        # (iPhone 11/12) is noticeably wider than the small one (13/14).
        if self._notch_type == "notch_large":
            width_frac, height_frac = 0.56, 0.031
        else:
            width_frac, height_frac = 0.44, 0.027
        nw = screen.width() * width_frac
        nh = max(9.0, screen.height() * height_frac)
        x = screen.center().x() - nw / 2
        y = screen.top()
        r = nh * 0.55
        path = QPainterPath()
        path.moveTo(x, y)
        path.lineTo(x + nw, y)
        path.lineTo(x + nw, y + nh - r)
        path.quadTo(x + nw, y + nh, x + nw - r, y + nh)
        path.lineTo(x + r, y + nh)
        path.quadTo(x, y + nh, x, y + nh - r)
        path.closeSubpath()
        painter.fillPath(path, QColor(0x05, 0x05, 0x06))
        # Speaker slot.
        sp_w, sp_h = nw * 0.26, max(2.0, nh * 0.20)
        painter.setBrush(QColor(0x22, 0x24, 0x2A))
        painter.drawRoundedRect(
            QRectF(screen.center().x() - sp_w / 2, y + nh * 0.16, sp_w, sp_h),
            sp_h / 2, sp_h / 2)
        # Front camera, right of the speaker.
        cam_r = nh * 0.17
        painter.setBrush(QColor(0x1D, 0x2A, 0x3A))
        painter.drawEllipse(QPointF(
            screen.center().x() + nw * 0.24, y + nh * 0.42), cam_r, cam_r)

    def _paint_wallpaper(self, painter, screen: QRectF):
        pm = self._ca_pixmap if self._ca_pixmap is not None else self._pixmap
        scale = max(screen.width() / pm.width(), screen.height() / pm.height())
        w = pm.width() * scale
        h = pm.height() * scale
        target = QRectF(screen.center().x() - w / 2,
                        screen.center().y() - h / 2, w, h)
        painter.drawPixmap(target, pm, QRectF(pm.rect()))

    def _paint_placeholder(self, painter, screen: QRectF):
        if not self._placeholder:
            return
        f = self._clock_font(max(9.0, screen.width() * 0.032))
        painter.setFont(f)
        painter.setPen(QColor(0x8E, 0x8E, 0x93))
        painter.drawText(screen,
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                         self._placeholder)

    def _paint_lockscreen_chrome(self, painter, screen: QRectF, t: float):
        lift = t * screen.height()
        painter.save()
        painter.setOpacity(max(0.0, 1.0 - t * 1.25))
        painter.translate(0.0, -lift)

        f_date = self._clock_font(max(8.0, screen.width() * 0.034))
        painter.setFont(f_date)
        painter.setPen(_DATE_TEXT)
        date_rect = QRectF(screen.left(), screen.top() + screen.height() * 0.075,
                           screen.width(), screen.height() * 0.05)
        painter.drawText(date_rect,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         self._date.toString("dddd, MMMM d").upper())

        f_time = self._clock_font(max(20.0, screen.width() * 0.115))
        painter.setFont(f_time)
        painter.setPen(Qt.white)
        time_rect = QRectF(screen.left(), date_rect.bottom() - screen.height() * 0.012,
                           screen.width(), screen.height() * 0.13)
        painter.drawText(time_rect,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         self._time.toString("H:mm"))

        if t < 0.5:
            f_hint = self._clock_font(max(9.0, screen.width() * 0.05))
            painter.setFont(f_hint)
            painter.setPen(_HINT)
            hint_rect = QRectF(screen.left(), screen.bottom() - screen.height() * 0.055,
                               screen.width(), screen.height() * 0.04)
            painter.drawText(hint_rect, Qt.AlignmentFlag.AlignHCenter, "\u2303")

        painter.restore()

    def _paint_home_screen(self, painter, screen: QRectF, t: float):
        """A real iOS-style home screen: status bar, labelled app-icon
        grid, page dots and a dock — drawn, never a lock-screen gimmick."""
        painter.save()
        painter.fillRect(screen, _HOME_DIM)
        if t < 1.0:
            painter.setOpacity(t)
        slide_in = (1.0 - t) * screen.height() * 0.05

        self._paint_status_bar(painter, screen)

        margin_x = screen.width() * 0.070
        cell_w = (screen.width() - 2 * margin_x) / 4.0
        icon = cell_w * 0.84
        label_h = max(8.0, screen.height() * 0.023)
        row_pitch = icon + label_h + screen.height() * 0.016
        y0 = screen.top() + screen.height() * 0.080 + slide_in

        label_font = QFont()
        label_font.setPixelSize(max(7, int(screen.width() * 0.047)))
        label_font.setWeight(QFont.Weight.Medium)

        for idx, (label, kind) in enumerate(_HOME_GRID_APPS):
            row, col = divmod(idx, 4)
            cx = screen.left() + margin_x + cell_w * (col + 0.5)
            x = cx - icon / 2
            y = y0 + row * row_pitch
            self._paint_app_icon(painter, QRectF(x, y, icon, icon), kind)
            label_rect = QRectF(x - cell_w * 0.14, y + icon + 1.5,
                                icon + cell_w * 0.28, label_h)
            painter.setFont(label_font)
            painter.setPen(QColor(0, 0, 0, 130))
            painter.drawText(label_rect.translated(0, 1),
                             Qt.AlignmentFlag.AlignHCenter
                             | Qt.AlignmentFlag.AlignTop, label)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(label_rect,
                             Qt.AlignmentFlag.AlignHCenter
                             | Qt.AlignmentFlag.AlignTop, label)

        # Page dots above the dock (two pages, first active).
        dots_y = screen.bottom() - screen.height() * 0.138 + slide_in * 0.4
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(2):
            painter.setBrush(QColor(255, 255, 255, 235 if i == 0 else 110))
            painter.drawEllipse(QPointF(
                screen.center().x() + (i - 0.5) * screen.width() * 0.045,
                dots_y), 2.1, 2.1)

        # Dock: frosted bar with four always-present apps (no labels).
        dock_w = screen.width() * 0.90
        dock_h = icon * 1.30
        dock_x = screen.center().x() - dock_w / 2
        dock_y = screen.bottom() - dock_h - screen.height() * 0.016 \
            + slide_in * 0.4
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_DOCK_BG)
        painter.drawRoundedRect(QRectF(dock_x, dock_y, dock_w, dock_h),
                                dock_h * 0.24, dock_h * 0.24)
        dock_cell = dock_w / 4.0
        for i, (_label, kind) in enumerate(_DOCK_APPS):
            cx = dock_x + dock_cell * (i + 0.5)
            self._paint_app_icon(
                painter,
                QRectF(cx - icon / 2, dock_y + (dock_h - icon) / 2, icon, icon),
                kind)

        painter.restore()

    def _paint_status_bar(self, painter, screen: QRectF):
        """Small clock on the left; signal / Wi-Fi / battery on the right."""
        top = screen.top() + screen.height() * 0.006
        height = screen.height() * 0.034
        white = QColor(255, 255, 255, 235)

        f = QFont()
        f.setPixelSize(max(8, int(screen.width() * 0.058)))
        f.setWeight(QFont.Weight.DemiBold)
        painter.setFont(f)
        painter.setPen(white)
        time_rect = QRectF(screen.left() + screen.width() * 0.085, top,
                           screen.width() * 0.30, height)
        painter.drawText(time_rect, Qt.AlignmentFlag.AlignLeft
                         | Qt.AlignmentFlag.AlignVCenter,
                         self._time.toString("H:mm"))

        # Battery (rightmost): outline + 65% fill + nub.
        batt_w = screen.width() * 0.105
        batt_h = height * 0.46
        batt_x = screen.right() - screen.width() * 0.075 - batt_w
        batt_y = top + (height - batt_h) / 2
        painter.setPen(QPen(QColor(255, 255, 255, 150), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(batt_x, batt_y, batt_w, batt_h), 2.2, 2.2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(white)
        painter.drawRoundedRect(
            QRectF(batt_x + 1.4, batt_y + 1.4, (batt_w - 2.8) * 0.65,
                   batt_h - 2.8), 1.2, 1.2)
        painter.drawRoundedRect(
            QRectF(batt_x + batt_w + 1.0, batt_y + batt_h * 0.28, 1.8,
                   batt_h * 0.44), 0.9, 0.9)

        # Wi-Fi: three arcs + dot, left of the battery.
        wifi_cx = batt_x - screen.width() * 0.075
        wifi_cy = top + height * 0.66
        painter.setBrush(white)
        painter.drawEllipse(QPointF(wifi_cx, wifi_cy), 1.1, 1.1)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for frac in (0.30, 0.52, 0.74):
            r = screen.width() * frac * 0.10
            painter.setPen(QPen(white, 1.3, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawArc(QRectF(wifi_cx - r, wifi_cy - r, 2 * r, 2 * r),
                            45 * 16, 90 * 16)

        # Signal bars: four ascending bars, left of Wi-Fi.
        bar_w = max(2.0, screen.width() * 0.013)
        bars_x = wifi_cx - screen.width() * 0.085 - 4 * bar_w - 3 * 1.6
        base_y = top + height * 0.78
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(white)
        for i in range(4):
            bh = height * (0.22 + 0.15 * i)
            painter.drawRoundedRect(
                QRectF(bars_x + i * (bar_w + 1.6), base_y - bh, bar_w, bh),
                0.8, 0.8)

    # -- home-screen app icons (original QPainter glyphs, no Apple art) -----
    def _paint_app_icon(self, painter, rect: QRectF, kind: str):
        w, h = rect.width(), rect.height()
        cx, cy = rect.center().x(), rect.center().y()
        radius = w * 0.225

        gradients = {
            "mail": ("#2E9BF0", "#0B65D8"), "weather": ("#2E9BF0", "#0B65D8"),
            "appstore": ("#1C9BF5", "#0A5CD6"),
            "music": ("#FC6A85", "#EE2D4F"),
            "phone": ("#43DB7C", "#14B84A"),
            "messages": ("#43DB7C", "#14B84A"),
            "facetime": ("#43DB7C", "#14B84A"),
            "camera": ("#F6F6F8", "#C6CAD1"),
            "settings": ("#EFEFF2", "#B4B9C2"),
        }
        light = {"calendar", "photos", "clock", "maps", "notes",
                 "reminders", "health", "files", "safari"}
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        if kind in gradients:
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0.0, QColor(gradients[kind][0]))
            grad.setColorAt(1.0, QColor(gradients[kind][1]))
            painter.fillPath(path, grad)
        elif kind in ("wallet", "tv"):
            painter.fillPath(path, QColor(0x1C, 0x1C, 0x1E))
        elif kind == "calculator":
            painter.fillPath(path, QColor(0x2C, 0x2C, 0x2E))
        else:  # light icons
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0.0, QColor(0xFF, 0xFF, 0xFF))
            grad.setColorAt(1.0, QColor(0xF0, 0xF1, 0xF4))
            painter.fillPath(path, grad)

        painter.save()
        painter.setClipPath(path)
        white = Qt.GlobalColor.white
        try:
            if kind == "calendar":
                f = QFont()
                f.setPixelSize(max(6, int(h * 0.17)))
                f.setWeight(QFont.Weight.Bold)
                painter.setFont(f)
                painter.setPen(QColor(0xF5, 0x2D, 0x4E))
                painter.drawText(
                    QRectF(rect.left(), rect.top() + h * 0.07, w, h * 0.22),
                    Qt.AlignmentFlag.AlignHCenter,
                    self._date.toString("ddd").upper())
                f.setPixelSize(max(9, int(h * 0.40)))
                f.setWeight(QFont.Weight.Light)
                painter.setFont(f)
                painter.setPen(QColor(0x1C, 0x1C, 0x1E))
                painter.drawText(
                    QRectF(rect.left(), rect.top() + h * 0.28, w, h * 0.55),
                    Qt.AlignmentFlag.AlignHCenter, str(self._date.day()))
            elif kind == "photos":
                petal_colors = ["#F7B731", "#F97F31", "#F95D6A", "#C86DD7",
                                "#5B8DEF", "#38C6B8", "#7ED321", "#B8E62E"]
                painter.setPen(Qt.PenStyle.NoPen)
                for i, color in enumerate(petal_colors):
                    painter.save()
                    painter.translate(cx, cy)
                    painter.rotate(i * 45.0)
                    col = QColor(color)
                    col.setAlpha(185)
                    painter.setBrush(col)
                    painter.drawEllipse(QRectF(-w * 0.075, -h * 0.30,
                                               w * 0.15, h * 0.30))
                    painter.restore()
            elif kind == "camera":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0x3A, 0x3A, 0x3C))
                painter.drawRoundedRect(
                    QRectF(rect.left() + w * 0.13, rect.top() + h * 0.30,
                           w * 0.74, h * 0.44), w * 0.08, w * 0.08)
                painter.drawRoundedRect(
                    QRectF(cx - w * 0.13, rect.top() + h * 0.22,
                           w * 0.26, h * 0.12), w * 0.04, w * 0.04)
                painter.setBrush(white)
                painter.drawEllipse(QPointF(cx, cy + h * 0.02), w * 0.13,
                                    w * 0.13)
                painter.setBrush(QColor(0x1C, 0x1C, 0x1E))
                painter.drawEllipse(QPointF(cx, cy + h * 0.02), w * 0.085,
                                    w * 0.085)
                painter.setBrush(QColor(0x5B, 0xC8, 0xFA))
                painter.drawEllipse(QPointF(cx - w * 0.03, cy - h * 0.01),
                                    w * 0.028, w * 0.028)
            elif kind == "mail":
                env = QRectF(rect.left() + w * 0.18, rect.top() + h * 0.28,
                             w * 0.64, h * 0.44)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(white)
                painter.drawRoundedRect(env, w * 0.05, w * 0.05)
                painter.setPen(QPen(QColor(0x0B, 0x65, 0xD8), max(1.2, w * 0.045),
                                    Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap))
                painter.drawLine(env.topLeft() + QPointF(w * 0.03, h * 0.03),
                                 QPointF(cx, env.top() + h * 0.24))
                painter.drawLine(QPointF(cx, env.top() + h * 0.24),
                                 env.topRight() + QPointF(-w * 0.03, h * 0.03))
            elif kind == "clock":
                painter.setPen(QPen(QColor(0x1C, 0x1C, 0x1E),
                                    max(1.2, w * 0.05)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(rect.adjusted(w * 0.13, h * 0.13,
                                                  -w * 0.13, -h * 0.13))
                painter.setPen(QPen(QColor(0x1C, 0x1C, 0x1E),
                                    max(1.2, w * 0.05), Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(cx, cy), QPointF(cx, cy - h * 0.20))
                painter.drawLine(QPointF(cx, cy), QPointF(cx + w * 0.15, cy + h * 0.04))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0xF9, 0x7F, 0x31))
                painter.drawEllipse(QPointF(cx, cy), w * 0.035, w * 0.035)
            elif kind == "maps":
                painter.fillRect(rect, QColor(0xE9, 0xF4, 0xDF))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0xA9, 0xD6, 0x8F))
                painter.drawRect(QRectF(rect.left(), rect.top(), w * 0.44, h * 0.46))
                painter.setBrush(QColor(0xBF, 0xE3, 0xF2))
                painter.drawRect(QRectF(rect.right() - w * 0.34, rect.bottom() - h * 0.40,
                                        w * 0.34, h * 0.40))
                painter.setPen(QPen(white, max(1.4, w * 0.06),
                                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(rect.left() + w * 0.06, rect.bottom() - h * 0.10,
                                 rect.left() + w * 0.52, rect.top() + h * 0.30)
                painter.setPen(QPen(QColor(0xF7, 0xCE, 0x46), max(1.2, w * 0.045),
                                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(rect.left() + w * 0.10, rect.top() + h * 0.08,
                                 rect.right() - w * 0.08, rect.bottom() - h * 0.28)
                pin = QPointF(rect.left() + w * 0.64, rect.top() + h * 0.38)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0xF5, 0x2D, 0x4E))
                painter.drawEllipse(pin, w * 0.105, w * 0.105)
                painter.drawPolygon(QPolygonF([
                    pin + QPointF(-w * 0.07, h * 0.05),
                    pin + QPointF(w * 0.07, h * 0.05),
                    pin + QPointF(0, h * 0.22)]))
                painter.setBrush(white)
                painter.drawEllipse(pin, w * 0.042, w * 0.042)
            elif kind == "weather":
                painter.setPen(Qt.PenStyle.NoPen)
                sun = QPointF(rect.left() + w * 0.36, rect.top() + h * 0.34)
                painter.setPen(QPen(QColor(0xF7, 0xCE, 0x46), max(1.2, w * 0.045),
                                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                for i in range(8):
                    ang = math.radians(i * 45.0)
                    painter.drawLine(
                        sun + QPointF(math.cos(ang) * w * 0.17,
                                      math.sin(ang) * w * 0.17),
                        sun + QPointF(math.cos(ang) * w * 0.23,
                                      math.sin(ang) * w * 0.23))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0xF7, 0xCE, 0x46))
                painter.drawEllipse(sun, w * 0.125, w * 0.125)
                painter.setBrush(white)
                cloud_y = rect.top() + h * 0.60
                painter.drawEllipse(QPointF(rect.left() + w * 0.40, cloud_y), w * 0.15, w * 0.13)
                painter.drawEllipse(QPointF(rect.left() + w * 0.60, cloud_y + h * 0.03), w * 0.18, w * 0.15)
                painter.drawRoundedRect(
                    QRectF(rect.left() + w * 0.26, cloud_y, w * 0.52, h * 0.14),
                    w * 0.06, w * 0.06)
            elif kind == "notes":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0xF7, 0xCE, 0x46))
                painter.drawRect(QRectF(rect.left(), rect.top(), w, h * 0.26))
                painter.setBrush(QColor(0xC7, 0xC7, 0xCC))
                for i in range(3):
                    painter.drawRoundedRect(
                        QRectF(rect.left() + w * 0.16,
                               rect.top() + h * (0.42 + 0.16 * i),
                               w * 0.68, h * 0.065), w * 0.03, w * 0.03)
            elif kind == "reminders":
                painter.setPen(Qt.PenStyle.NoPen)
                for i, color in enumerate(["#F97F31", "#0B65D8", "#7B5CD6"]):
                    yy = rect.top() + h * (0.28 + 0.22 * i)
                    painter.setBrush(QColor(color))
                    painter.drawEllipse(QPointF(rect.left() + w * 0.22, yy),
                                        w * 0.055, w * 0.055)
                    painter.setBrush(QColor(0xC7, 0xC7, 0xCC))
                    painter.drawRoundedRect(
                        QRectF(rect.left() + w * 0.36, yy - h * 0.033,
                               w * 0.46, h * 0.066), w * 0.03, w * 0.03)
            elif kind == "appstore":
                pen = QPen(white, max(1.6, w * 0.085), Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(rect.left() + w * 0.28, rect.bottom() - h * 0.28,
                                 rect.left() + w * 0.50, rect.top() + h * 0.26)
                painter.drawLine(rect.left() + w * 0.50, rect.top() + h * 0.26,
                                 rect.left() + w * 0.72, rect.bottom() - h * 0.28)
                painter.drawLine(rect.left() + w * 0.375, rect.top() + h * 0.575,
                                 rect.left() + w * 0.625, rect.top() + h * 0.575)
            elif kind == "settings":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0x6E, 0x72, 0x78))
                for i in range(8):
                    painter.save()
                    painter.translate(cx, cy)
                    painter.rotate(i * 45.0)
                    painter.drawRoundedRect(
                        QRectF(-w * 0.045, -h * 0.40, w * 0.09, h * 0.17),
                        w * 0.03, w * 0.03)
                    painter.restore()
                painter.drawEllipse(QPointF(cx, cy), w * 0.25, w * 0.25)
                painter.setBrush(QColor(0xD9, 0xDB, 0xE0))
                painter.drawEllipse(QPointF(cx, cy), w * 0.115, w * 0.115)
            elif kind == "wallet":
                painter.setPen(Qt.PenStyle.NoPen)
                for i, color in enumerate(
                        ["#3E9BE8", "#2FBF71", "#F5C33B", "#F95D6A"]):
                    painter.setBrush(QColor(color))
                    painter.drawRoundedRect(
                        QRectF(rect.left() + w * 0.09,
                               rect.top() + h * (0.16 + 0.17 * i),
                               w * 0.82, h * 0.105), w * 0.04, w * 0.04)
            elif kind == "health":
                heart = QPainterPath()
                hx, hy = cx, cy - h * 0.02
                heart.moveTo(hx, hy + h * 0.30)
                heart.cubicTo(hx - w * 0.44, hy + h * 0.02,
                              hx - w * 0.30, hy - h * 0.34, hx, hy - h * 0.15)
                heart.cubicTo(hx + w * 0.30, hy - h * 0.34,
                              hx + w * 0.44, hy + h * 0.02, hx, hy + h * 0.30)
                painter.fillPath(heart, QColor(0xF5, 0x2D, 0x4E))
                painter.setPen(QPen(white, max(1.1, w * 0.038),
                                    Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap,
                                    Qt.PenJoinStyle.RoundJoin))
                pts = [(0.30, 0.52), (0.43, 0.52), (0.49, 0.41),
                       (0.56, 0.61), (0.62, 0.52), (0.71, 0.52)]
                painter.drawPolyline(QPolygonF([
                    QPointF(rect.left() + w * px, rect.top() + h * py)
                    for px, py in pts]))
            elif kind == "files":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0x2E, 0x8F, 0xE0))
                painter.drawRoundedRect(
                    QRectF(rect.left() + w * 0.15, rect.top() + h * 0.30,
                           w * 0.70, h * 0.44), w * 0.05, w * 0.05)
                painter.drawRoundedRect(
                    QRectF(rect.left() + w * 0.15, rect.top() + h * 0.235,
                           w * 0.30, h * 0.12), w * 0.05, w * 0.05)
                painter.setBrush(QColor(0x5F, 0xB2, 0xF5))
                painter.drawRoundedRect(
                    QRectF(rect.left() + w * 0.12, rect.top() + h * 0.42,
                           w * 0.76, h * 0.34), w * 0.05, w * 0.05)
            elif kind == "calculator":
                painter.setPen(Qt.PenStyle.NoPen)
                for row in range(3):
                    for col in range(3):
                        painter.setBrush(
                            QColor(0xF9, 0x7F, 0x31) if col == 2
                            else QColor(0xE8, 0xE8, 0xEC))
                        painter.drawRoundedRect(
                            QRectF(rect.left() + w * (0.17 + 0.24 * col),
                                   rect.top() + h * (0.24 + 0.24 * row),
                                   w * 0.17, h * 0.17), w * 0.045, w * 0.045)
            elif kind == "facetime":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(white)
                painter.drawRoundedRect(
                    QRectF(rect.left() + w * 0.16, rect.top() + h * 0.31,
                           w * 0.44, h * 0.38), w * 0.07, w * 0.07)
                painter.drawPolygon(QPolygonF([
                    QPointF(rect.left() + w * 0.60, rect.top() + h * 0.43),
                    QPointF(rect.left() + w * 0.84, rect.top() + h * 0.30),
                    QPointF(rect.left() + w * 0.84, rect.top() + h * 0.70),
                    QPointF(rect.left() + w * 0.60, rect.top() + h * 0.57)]))
            elif kind == "tv":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(white)
                painter.drawRoundedRect(
                    QRectF(rect.left() + w * 0.16, rect.top() + h * 0.26,
                           w * 0.68, h * 0.48), w * 0.07, w * 0.07)
                painter.setBrush(QColor(0x1C, 0x1C, 0x1E))
                painter.drawPolygon(QPolygonF([
                    QPointF(rect.left() + w * 0.42, rect.top() + h * 0.38),
                    QPointF(rect.left() + w * 0.42, rect.top() + h * 0.62),
                    QPointF(rect.left() + w * 0.62, rect.top() + h * 0.50)]))
            elif kind == "stocks":
                painter.setPen(QPen(QColor(0xC7, 0xC7, 0xCC),
                                    max(1.0, w * 0.03)))
                painter.drawLine(rect.left() + w * 0.18, rect.top() + h * 0.20,
                                 rect.left() + w * 0.18, rect.bottom() - h * 0.20)
                painter.drawLine(rect.left() + w * 0.18, rect.bottom() - h * 0.20,
                                 rect.right() - w * 0.14, rect.bottom() - h * 0.20)
                pts = [(0.22, 0.62), (0.42, 0.50), (0.56, 0.56),
                       (0.72, 0.34), (0.84, 0.40)]
                painter.setPen(QPen(QColor(0x0B, 0x65, 0xD8),
                                    max(1.4, w * 0.05), Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap,
                                    Qt.PenJoinStyle.RoundJoin))
                painter.drawPolyline(QPolygonF([
                    QPointF(rect.left() + w * px, rect.top() + h * py)
                    for px, py in pts]))
            elif kind == "home":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0xF9, 0x7F, 0x31))
                painter.drawPolygon(QPolygonF([
                    QPointF(cx, rect.top() + h * 0.16),
                    QPointF(rect.left() + w * 0.82, rect.top() + h * 0.46),
                    QPointF(rect.right() - w * 0.30, rect.top() + h * 0.46),
                    QPointF(rect.right() - w * 0.30, rect.bottom() - h * 0.18),
                    QPointF(rect.left() + w * 0.30, rect.bottom() - h * 0.18),
                    QPointF(rect.left() + w * 0.18, rect.top() + h * 0.46)]))
                painter.setBrush(white)
                painter.drawRoundedRect(
                    QRectF(cx - w * 0.07, rect.bottom() - h * 0.36,
                           w * 0.14, h * 0.18), w * 0.03, w * 0.03)
            elif kind == "news":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0xF5, 0x2D, 0x4E))
                painter.drawRect(QRectF(rect.left(), rect.top(), w, h * 0.30))
                f = QFont()
                f.setPixelSize(max(7, int(h * 0.19)))
                f.setWeight(QFont.Weight.Black)
                painter.setFont(f)
                painter.setPen(white)
                painter.drawText(
                    QRectF(rect.left(), rect.top() + h * 0.04, w, h * 0.24),
                    Qt.AlignmentFlag.AlignHCenter, "N")
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0xC7, 0xC7, 0xCC))
                for i in range(2):
                    painter.drawRoundedRect(
                        QRectF(rect.left() + w * 0.16,
                               rect.top() + h * (0.46 + 0.18 * i),
                               w * 0.68, h * 0.07), w * 0.03, w * 0.03)
            elif kind == "phone":
                painter.save()
                painter.translate(cx, cy)
                painter.rotate(45.0)
                pen = QPen(white, max(2.0, w * 0.15), Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                arc = QRectF(-w * 0.27, -h * 0.27, w * 0.54, h * 0.54)
                painter.drawArc(arc, 105 * 16, 150 * 16)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(white)
                for ang_deg in (105.0, 255.0):
                    ang = math.radians(ang_deg)
                    painter.drawEllipse(
                        QPointF(math.cos(ang) * w * 0.27,
                                -math.sin(ang) * h * 0.27),
                        w * 0.075, w * 0.075)
                painter.restore()
            elif kind == "safari":
                painter.setPen(QPen(QColor(0x0B, 0x65, 0xD8),
                                    max(1.2, w * 0.045)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(rect.adjusted(w * 0.11, h * 0.11,
                                                  -w * 0.11, -h * 0.11))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0xF5, 0x2D, 0x4E))
                painter.drawPolygon(QPolygonF([
                    QPointF(cx, cy - h * 0.24), QPointF(cx + w * 0.065, cy),
                    QPointF(cx, cy)]))
                painter.setBrush(QColor(0xC7, 0xC7, 0xCC))
                painter.drawPolygon(QPolygonF([
                    QPointF(cx, cy + h * 0.24), QPointF(cx - w * 0.065, cy),
                    QPointF(cx, cy)]))
            elif kind == "messages":
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(white)
                painter.drawRoundedRect(
                    QRectF(rect.left() + w * 0.17, rect.top() + h * 0.25,
                           w * 0.66, h * 0.42), w * 0.11, w * 0.11)
                painter.drawPolygon(QPolygonF([
                    QPointF(rect.left() + w * 0.30, rect.top() + h * 0.64),
                    QPointF(rect.left() + w * 0.46, rect.top() + h * 0.64),
                    QPointF(rect.left() + w * 0.28, rect.top() + h * 0.82)]))
            elif kind == "music":
                painter.setPen(QPen(white, max(1.4, w * 0.05),
                                    Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap))
                stem_x = rect.left() + w * 0.60
                painter.drawLine(stem_x, rect.top() + h * 0.24,
                                 stem_x, rect.top() + h * 0.64)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(white)
                painter.drawPolygon(QPolygonF([
                    QPointF(stem_x, rect.top() + h * 0.24),
                    QPointF(rect.left() + w * 0.76, rect.top() + h * 0.33),
                    QPointF(rect.left() + w * 0.76, rect.top() + h * 0.47),
                    QPointF(stem_x, rect.top() + h * 0.38)]))
                painter.save()
                painter.translate(rect.left() + w * 0.50, rect.top() + h * 0.68)
                painter.rotate(-18.0)
                painter.drawEllipse(QRectF(-w * 0.10, -h * 0.065,
                                           w * 0.20, h * 0.13))
                painter.restore()
        finally:
            painter.restore()