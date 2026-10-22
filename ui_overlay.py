# ui_overlay.py
import html
import json
import os
import re
import tempfile
import time

import markdown
from PyQt6.QtCore import (
    Qt, pyqtSignal, QThread, QTimer, QTime, QRect, QRectF, QPointF, QPoint,
    QByteArray, QVariantAnimation, QSize,
)
from PyQt6.QtGui import (
    QAction, QActionGroup, QColor, QIcon, QPainter, QPen, QPixmap,
    QTextBlockFormat, QTextCharFormat, QTextCursor, QFont,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextBrowser, QFrame, QComboBox, QSlider, QStackedWidget, QButtonGroup,
    QMenu, QWidgetAction, QSizePolicy,
)

try:
    from PyQt6.QtSvg import QSvgRenderer
except ImportError:  # icons simply won't render; text labels still work
    QSvgRenderer = None

import config


# ============================================================================
# Background workers (unchanged)
# ============================================================================
class AIWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, task_fn, *args):
        super().__init__()
        self.task_fn = task_fn
        self.args = args

    def run(self):
        try:
            result = self.task_fn(*self.args)
            self.finished.emit(str(result))
        except Exception as e:
            self.error.emit(str(e))


class AIStreamWorker(QThread):
    chunk_received = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, stream_fn, *args):
        super().__init__()
        self.stream_fn = stream_fn
        self.args = args

    def run(self):
        try:
            for chunk in self.stream_fn(*self.args):
                if chunk:
                    self.chunk_received.emit(chunk)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


# ============================================================================
# Design tokens
# ============================================================================
SHADOW = 14   # transparent margin that holds the soft shadow
EDGE = 6      # width of the resize hot-zone inside the window border

DARK = {
    "surface": "#171C24", "raised": "#1F2631", "inset": "#12161D",
    "line": "#2C3544", "line_soft": "#232B38",
    "ink": "#E9EDF3", "muted": "#9AA5B7", "faint": "#6C778A",
    "accent": "#E8B84A", "accent_hover": "#F0C560", "accent_press": "#D4A53C",
    "accent_ink": "#1B1405", "accent_soft": "rgba(232,184,74,56)",
    "live": "#3CCFA6", "live_soft": "rgba(60,207,166,40)",
    "danger": "#EF5B5B", "danger_hover": "#F47373", "danger_soft": "rgba(239,91,91,40)",
    "on_danger": "#FFFFFF",
    "code_bg": "#0F131A", "code_ink": "#CFE3FF", "link": "#8DB6FF",
    "shadow_alpha": 95,
}

LIGHT = {
    "surface": "#FFFFFF", "raised": "#EEF0F4", "inset": "#F5F6F9",
    "line": "#DCE0E7", "line_soft": "#E8EBF0",
    "ink": "#1A202B", "muted": "#586377", "faint": "#8791A3",
    "accent": "#E2A92B", "accent_hover": "#EDB63D", "accent_press": "#CC9620",
    "accent_ink": "#1B1405", "accent_soft": "rgba(226,169,43,64)",
    "live": "#12907A", "live_soft": "rgba(18,144,122,34)",
    "danger": "#D83B3B", "danger_hover": "#E55252", "danger_soft": "rgba(216,59,59,30)",
    "on_danger": "#FFFFFF",
    "code_bg": "#EEF1F6", "code_ink": "#1F3A66", "link": "#2455B8",
    "shadow_alpha": 55,
}

QSS = """
QWidget { font-family: "Segoe UI Variable Text", "Segoe UI", "Noto Sans", sans-serif; font-size: 13px; color: @ink@; }
QFrame#surface { background: @surface@; border: 1px solid @line@; border-radius: 14px; }
QLabel { background: transparent; }
QWidget#pill { font-size: 12px; }
QToolTip { background: @raised@; color: @ink@; border: 1px solid @line@; border-radius: 6px; padding: 5px 8px; }

QLabel#title { font-size: 13px; font-weight: 600; }
QLabel#timer { color: @danger@; font-size: 12px; font-weight: 600; }
QLabel#caption { color: @faint@; font-size: 11px; }
QLabel#kbd { background: @raised@; border: 1px solid @line@; border-bottom: 2px solid @line@;
             border-radius: 6px; padding: 3px 9px; color: @muted@; font-size: 11px; font-weight: 500; }

QFrame#segment { background: @inset@; border: 1px solid @line_soft@; border-radius: 11px; }
QPushButton[variant="seg"] { background: transparent; border: 1px solid transparent; border-radius: 8px;
    padding: 6px 14px; color: @muted@; font-weight: 500; min-height: 18px; }
QPushButton[variant="seg"]:hover:!checked { color: @ink@; }
QPushButton[variant="seg"]:checked { background: @raised@; border: 1px solid @line@; color: @ink@; }
QPushButton[variant="seg"]:disabled { color: @faint@; }

QPushButton[variant="primary"], QPushButton[variant="secondary"], QPushButton[variant="danger"],
QPushButton[variant="stop_live"], QPushButton[variant="stop_danger"] {
    border-radius: 9px; padding: 0 16px; min-height: 34px; font-weight: 600; }
QPushButton[variant="primary"] { background: @accent@; color: @accent_ink@; border: 1px solid @accent@; }
QPushButton[variant="primary"]:hover { background: @accent_hover@; border-color: @accent_hover@; }
QPushButton[variant="primary"]:pressed { background: @accent_press@; border-color: @accent_press@; }
QPushButton[variant="secondary"] { background: @raised@; color: @ink@; border: 1px solid @line@; }
QPushButton[variant="secondary"]:hover { border-color: @faint@; }
QPushButton[variant="secondary"]:pressed { background: @inset@; }
QPushButton[variant="danger"] { background: @danger@; color: @on_danger@; border: 1px solid @danger@; }
QPushButton[variant="danger"]:hover { background: @danger_hover@; border-color: @danger_hover@; }
QPushButton[variant="stop_live"] { background: transparent; color: @ink@; border: 1px solid @live@; }
QPushButton[variant="stop_live"]:hover { background: @live_soft@; }
QPushButton[variant="stop_danger"] { background: transparent; color: @ink@; border: 1px solid @danger@; }
QPushButton[variant="stop_danger"]:hover { background: @danger_soft@; }
QPushButton[variant="primary"]:disabled, QPushButton[variant="secondary"]:disabled,
QPushButton[variant="danger"]:disabled { background: @raised@; color: @faint@; border: 1px solid @line_soft@; }

QPushButton[variant="chip"] { background: transparent; border: 1px solid @line@; border-radius: 9px;
    padding: 0 12px; min-height: 32px; color: @muted@; font-weight: 500; }
QPushButton[variant="chip"]:hover { border-color: @faint@; }
QPushButton[variant="chip"]:checked { border-color: @accent@; background: @accent_soft@; color: @ink@; }
QPushButton[variant="chip"]:disabled { color: @faint@; border-color: @line_soft@; }

QPushButton[variant="ghost"] { background: transparent; border: none; border-radius: 8px;
    padding: 0 10px; min-height: 28px; color: @muted@; font-weight: 500; }
QPushButton[variant="ghost"]:hover { background: @raised@; color: @ink@; }

QPushButton[variant="tool"] { background: transparent; border: none; border-radius: 8px; padding: 0;
    min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; }
QPushButton[variant="tool"]:hover { background: @raised@; }
QPushButton[variant="tool"]:pressed { background: @inset@; }
QPushButton[variant="tool"]:checked { background: @accent_soft@; }
QPushButton[variant="tool"]:disabled { background: transparent; }
QPushButton#closeBtn:hover { background: @danger_soft@; }

QComboBox { background: @raised@; border: 1px solid @line@; border-radius: 9px; padding: 0 10px;
    min-height: 34px; color: @ink@; }
QComboBox:hover { border-color: @faint@; }
QComboBox:disabled { color: @faint@; border-color: @line_soft@; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url("@chevron@"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: @surface@; border: 1px solid @line@; outline: 0; padding: 4px;
    selection-background-color: @accent_soft@; selection-color: @ink@; }

QFrame#pane { background: @inset@; border: 1px solid @line_soft@; border-radius: 12px; }
QTextBrowser { background: transparent; border: none; color: @ink@; font-size: 14px;
    selection-background-color: @accent_soft@; selection-color: @ink@; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 6px 2px; }
QScrollBar::handle:vertical { background: @line@; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: @faint@; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { height: 0; }

QMenu { background: @surface@; border: 1px solid @line@; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 14px 7px 28px; border-radius: 6px; }
QMenu::item:selected { background: @raised@; }
QMenu::separator { height: 1px; background: @line_soft@; margin: 6px 4px; }
QMenu::indicator { width: 8px; height: 8px; margin-left: 10px; border-radius: 4px; }
QMenu::indicator:checked { background: @accent@; }
QMenu::indicator:unchecked { background: transparent; }

QSlider::groove:horizontal { height: 4px; background: @line@; border-radius: 2px; }
QSlider::sub-page:horizontal { background: @accent@; border-radius: 2px; }
QSlider::handle:horizontal { background: @ink@; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
"""


# ============================================================================
# Icons (24x24 line icons, drawn from inline SVG so they follow the theme)
# ============================================================================
ICONS = {
    "mic": '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/>',
    "volume": '<path d="M11 5 6 9H2v6h4l5 4V5Z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
    "crop": '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M18 22V8a2 2 0 0 0-2-2H2"/>',
    "sparkles": '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/><path d="M4 17v2"/><path d="M5 18H3"/>',
    "video": '<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
    "rec_dot": '<circle cx="12" cy="12" r="6" fill="currentColor" stroke="none"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "minus": '<path d="M5 12h14"/>',
    "pin": '<path d="M12 17v5"/><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z"/>',
    "copy": '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "sliders": '<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/><path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
}

# role names resolved against the active theme: (normal, checked)
VARIANT_ICON = {
    "primary": ("accent_ink", None), "secondary": ("ink", None), "danger": ("on_danger", None),
    "stop_live": ("live", None), "stop_danger": ("danger", None), "ghost": ("muted", None),
    "tool": ("muted", "accent"), "chip": ("muted", "accent"), "seg": ("muted", "ink"),
}


def _render_svg(name, color, size=18, dpr=2.0):
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    if QSvgRenderer is None or name not in ICONS:
        return pm
    body = ICONS[name].replace("currentColor", color)
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pm


def build_icon(name, normal, checked, disabled, size=18, dpr=2.0):
    icon = QIcon()
    for mode, state, color in (
        (QIcon.Mode.Normal, QIcon.State.Off, normal),
        (QIcon.Mode.Normal, QIcon.State.On, checked),
        (QIcon.Mode.Disabled, QIcon.State.Off, disabled),
        (QIcon.Mode.Disabled, QIcon.State.On, disabled),
    ):
        icon.addPixmap(_render_svg(name, color, size, dpr), mode, state)
    return icon


def _write_chevron(color):
    """The combo-box arrow must be a file on disk to be used from a stylesheet."""
    path = os.path.join(tempfile.gettempdir(), f"gemini_lens_chevron_{color.strip('#')}.png")
    try:
        if not os.path.exists(path):
            _render_svg("chevron", color, 12, 2.0).save(path, "PNG")
    except Exception:
        pass
    return path.replace("\\", "/")


# ============================================================================
# Small persisted preferences (theme, opacity, size, position)
# ============================================================================
PREFS_FILE = os.path.join(config.BASE_DIR, "ui_prefs.json")


def _load_prefs():
    try:
        with open(PREFS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_prefs(data):
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _clean_status(text):
    """Drop the leading emoji/symbols that older messages carry; keep the words."""
    text = re.sub(r"^[^\w]+", "", text or "").strip().replace("...", "…")
    return text or "Ready"


# ============================================================================
# Custom widgets
# ============================================================================
class LensMark(QWidget):
    """Tiny app mark: a lens ring with a bright centre."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(20, 20)
        self._color = QColor("#E8B84A")

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(self._color, 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(2, 2, 16, 16))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(QPointF(10, 10), 3.2, 3.2)


class StatusPill(QWidget):
    """Status dot + short text. The dot pulses while something is happening."""

    COLOR_KEY = {"ready": "live", "listening": "live", "working": "accent", "recording": "danger"}

    def __init__(self):
        super().__init__()
        self.setObjectName("pill")
        self.setFixedHeight(26)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._text = "Ready"
        self._state = "ready"
        self._phase = 0.0
        self._theme = DARK
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1500)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._on_phase)

    def _on_phase(self, value):
        self._phase = float(value)
        self.update()

    def set_theme(self, theme):
        self._theme = theme
        self.update()

    def set_state(self, text, state):
        self._text = text
        self._state = state
        self.setToolTip(text)
        if state == "ready":
            self._anim.stop()
            self._phase = 0.0
        elif self._anim.state() != QVariantAnimation.State.Running:
            self._anim.start()
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        text_w = self.fontMetrics().horizontalAdvance(self._text)
        return QSize(min(self.maximumWidth(), text_w + 24 + 12), 26)

    def paintEvent(self, event):
        t = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2
        p.setPen(QPen(QColor(t["line"]), 1))
        p.setBrush(QColor(t["raised"]))
        p.drawRoundedRect(rect, radius, radius)

        dot = QColor(t[self.COLOR_KEY[self._state]])
        center = QPointF(14, rect.height() / 2 + 0.5)
        if self._state != "ready":
            halo = QColor(dot)
            halo.setAlpha(int(130 * (1.0 - self._phase)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(center, 3.5 + 5.0 * self._phase, 3.5 + 5.0 * self._phase)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(dot)
        p.drawEllipse(center, 3.5, 3.5)

        text_rect = QRectF(25, 0, self.width() - 25 - 11, self.height())
        p.setPen(QColor(t["muted"]))
        elided = self.fontMetrics().elidedText(self._text, Qt.TextElideMode.ElideRight, int(text_rect.width()))
        p.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), elided)


class TitleBar(QWidget):
    """Drag the window from here (frameless windows have no native title bar)."""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
        event.accept()


class _Surface(QFrame):
    """Rounded window body. Its thin outer band acts as a resize border."""

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)

    def _edges(self, pos):
        edges = Qt.Edge(0)
        if pos.x() <= EDGE:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= self.width() - EDGE:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= EDGE:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= self.height() - EDGE:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _cursor_for(edges):
        left, right = bool(edges & Qt.Edge.LeftEdge), bool(edges & Qt.Edge.RightEdge)
        top, bottom = bool(edges & Qt.Edge.TopEdge), bool(edges & Qt.Edge.BottomEdge)
        if (left and top) or (right and bottom):
            return Qt.CursorShape.SizeFDiagCursor
        if (right and top) or (left and bottom):
            return Qt.CursorShape.SizeBDiagCursor
        if left or right:
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def mouseMoveEvent(self, event):
        edges = self._edges(event.position().toPoint())
        if edges:
            self.setCursor(self._cursor_for(edges))
        else:
            self.unsetCursor()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edges = self._edges(event.position().toPoint())
            handle = self.window().windowHandle()
            if edges and handle is not None:
                handle.startSystemResize(edges)

    def leaveEvent(self, event):
        self.unsetCursor()


class OutputView(QTextBrowser):
    """Reading pane with a friendly empty state instead of a grey placeholder."""

    DEFAULT_HEADLINE = "Nothing here yet"
    DEFAULT_DETAIL = "Start transcribing, or select text in any app and press Ctrl+Shift+Space."

    def __init__(self):
        super().__init__()
        self.setOpenExternalLinks(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.document().setDocumentMargin(16)
        self._headline = self.DEFAULT_HEADLINE
        self._detail = self.DEFAULT_DETAIL
        self._colors = ("#E9EDF3", "#9AA5B7")
        self._empty = QLabel(self.viewport())
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        self._empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.textChanged.connect(self._sync_empty)
        self._render_empty()
        self._sync_empty()

    def set_empty_colors(self, ink, muted):
        self._colors = (ink, muted)
        self._render_empty()

    def set_empty_state(self, headline=None, detail=None):
        self._headline = headline or self.DEFAULT_HEADLINE
        self._detail = detail or self.DEFAULT_DETAIL
        self._render_empty()

    def setPlaceholderText(self, text):
        # main.py calls this when transcription starts; show it as the empty-state detail line.
        self._detail = re.sub(r"^[^\w]+", "", text or "").strip() or self.DEFAULT_DETAIL
        self._render_empty()

    def _render_empty(self):
        ink, muted = self._colors
        self._empty.setText(
            f'<div style="font-size:15px; font-weight:600; color:{ink};">{html.escape(self._headline)}</div>'
            f'<div style="font-size:12px; color:{muted}; margin-top:6px;">{html.escape(self._detail)}</div>'
        )

    def _sync_empty(self):
        self._empty.setVisible(self.document().isEmpty())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._empty.setGeometry(28, 0, max(0, self.viewport().width() - 56), self.viewport().height())


# ============================================================================
# Main window
# ============================================================================
class ModernOverlayUI(QWidget):
    ask_highlight_requested = pyqtSignal()
    toggle_record_requested = pyqtSignal(bool, bool, object)
    toggle_transcribe_requested = pyqtSignal(bool, str, str)
    snip_screen_requested = pyqtSignal()
    run_diagnostics_requested = pyqtSignal()
    refresh_windows_requested = pyqtSignal()
    signal_append_transcript = pyqtSignal(str, bool)

    def __init__(self):
        super().__init__()
        self._prefs = _load_prefs()
        self.is_recording = False
        self.is_transcribing = False
        self.record_time = QTime(0, 0, 0)
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self._update_record_clock)

        # content state
        self._stream_buffer = ""
        self._stream_dirty = False
        self._mode = "empty"          # empty | stream | markdown | transcript
        self._transcript = []         # [{"ts": "12:04", "text": "..."}]
        self._stream_timer = QTimer(self)
        self._stream_timer.setSingleShot(True)
        self._stream_timer.setInterval(60)
        self._stream_timer.timeout.connect(self._flush_stream)

        # appearance state
        default_opacity = int(float(getattr(config, "UI_OPACITY", 0.96)) * 100)
        opacity = int(self._prefs.get("opacity", default_opacity))
        self.current_opacity = max(30, min(100, opacity)) / 100.0
        self.theme_pref = self._prefs.get("theme", "dark")
        if self.theme_pref not in ("dark", "light", "system"):
            self.theme_pref = "dark"
        self.t = dict(DARK)
        self._btns = {}

        self.init_ui()
        self.signal_append_transcript.connect(self._safe_append_transcript)

    # ------------------------------------------------------------------ build
    def init_ui(self):
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        if self._prefs.get("pinned", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setWindowTitle("Gemini Lens Pro")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(self.current_opacity)
        self.setMinimumSize(480 + 2 * SHADOW, 400 + 2 * SHADOW)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        self.surface = _Surface()
        self.surface.setObjectName("surface")
        outer.addWidget(self.surface)

        root = QVBoxLayout(self.surface)
        root.setContentsMargins(EDGE, EDGE, EDGE, EDGE)
        root.setSpacing(0)
        root.addWidget(self._build_titlebar())

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(10, 2, 10, 6)
        body_l.setSpacing(12)
        body_l.addWidget(self._build_tabs())
        body_l.addWidget(self._build_controls())
        body_l.addWidget(self._build_pane(), 1)
        body_l.addLayout(self._build_footer())
        root.addWidget(body, 1)

        self._apply_theme()
        self.update_status("Ready")

        w = int(self._prefs.get("w", 600 + 2 * SHADOW))
        h = int(self._prefs.get("h", 580 + 2 * SHADOW))
        self.resize(w, h)
        x, y = self._prefs.get("x"), self._prefs.get("y")
        if isinstance(x, int) and isinstance(y, int) and self._is_on_screen(x, y, w, h):
            self.move(x, y)

    # -- helpers to create styled buttons -------------------------------------
    def _btn(self, text, icon, variant, checkable=False, tip=None, icon_px=18):
        btn = QPushButton(text)
        btn.setProperty("variant", variant)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setCheckable(checkable)
        btn.setIconSize(QSize(icon_px, icon_px))
        if tip:
            btn.setToolTip(tip)
        if icon:
            self._btns[btn] = (icon, variant)
        return btn

    def _tool_button(self, icon, tip, checkable=False):
        return self._btn("", icon, "tool", checkable=checkable, tip=tip)

    def _set_btn(self, btn, text=None, icon=None, variant=None):
        if text is not None:
            btn.setText(text)
        name, current = self._btns.get(btn, (icon, variant or btn.property("variant")))
        name = icon or name
        variant = variant or current
        self._btns[btn] = (name, variant)
        btn.setProperty("variant", variant)
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        self._paint_icon(btn)

    def _paint_icon(self, btn):
        spec = self._btns.get(btn)
        if not spec:
            return
        name, variant = spec
        normal, checked = VARIANT_ICON[variant]
        n_color = self.t[normal]
        c_color = self.t[checked] if checked else n_color
        px = btn.iconSize().width() or 18
        btn.setIcon(build_icon(name, n_color, c_color, self.t["faint"], px, max(2.0, self.devicePixelRatioF())))

    def _refresh_icons(self):
        for btn in list(self._btns):
            self._paint_icon(btn)

    # -- title bar ---------------------------------------------------------------
    def _build_titlebar(self):
        bar = TitleBar()
        bar.setFixedHeight(44)
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 0, 2, 0)
        row.setSpacing(8)

        self.lens_mark = LensMark()
        title = QLabel("Gemini Lens Pro")
        title.setObjectName("title")
        title.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.status_pill = StatusPill()

        self.btn_pin = self._tool_button("pin", "Keep on top", checkable=True)
        self.btn_pin.setChecked(bool(self._prefs.get("pinned", True)))
        self.btn_pin.toggled.connect(self._set_pinned)
        self.btn_menu = self._tool_button("sliders", "Opacity, theme and tools")
        self.btn_menu.clicked.connect(self._show_menu)
        self.btn_min = self._tool_button("minus", "Minimize")
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_close = self._tool_button("x", "Close")
        self.btn_close.setObjectName("closeBtn")
        self.btn_close.clicked.connect(self.close)

        row.addWidget(self.lens_mark)
        row.addWidget(title)
        row.addSpacing(4)
        row.addWidget(self.status_pill)
        row.addStretch(1)
        for b in (self.btn_pin, self.btn_menu, self.btn_min, self.btn_close):
            row.addWidget(b)
        return bar

    # -- tabs + per-tab controls ----------------------------------------------------
    def _build_tabs(self):
        seg = QFrame()
        seg.setObjectName("segment")
        row = QHBoxLayout(seg)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self._tab_buttons = []
        for i, (label, icon) in enumerate((("Transcribe", "mic"), ("Explain", "sparkles"), ("Record", "video"))):
            btn = self._btn(label, icon, "seg", checkable=True, icon_px=16)
            self.tab_group.addButton(btn, i)
            btn.clicked.connect(lambda _checked, idx=i: self._set_tab(idx))
            row.addWidget(btn, 1)
            self._tab_buttons.append(btn)
        return seg

    def _page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        return page, layout

    def _build_controls(self):
        self.stack = QStackedWidget()

        # --- Transcribe ---
        page, row = self._page()
        self.btn_transcribe = self._btn("Start", "mic", "primary")
        self.btn_transcribe.clicked.connect(self._handle_transcribe_click)

        source = QFrame()
        source.setObjectName("segment")
        src_l = QHBoxLayout(source)
        src_l.setContentsMargins(3, 3, 3, 3)
        src_l.setSpacing(2)
        self.src_system = self._btn("System", "volume", "seg", checkable=True, tip="Computer audio: videos, calls, lectures", icon_px=16)
        self.src_mic = self._btn("Mic", "mic", "seg", checkable=True, tip="Your microphone", icon_px=16)
        self.src_system.setChecked(True)
        self.src_group = QButtonGroup(self)
        self.src_group.setExclusive(True)
        self.src_group.addButton(self.src_system)
        self.src_group.addButton(self.src_mic)
        src_l.addWidget(self.src_system)
        src_l.addWidget(self.src_mic)

        self.combo_lang = QComboBox()
        for label, code in (
            ("Tiếng Việt", "vi"), ("English", "en"), ("Auto detect", "auto"),
            ("日本語", "ja"), ("中文", "zh"), ("한국어", "ko"), ("Français", "fr"),
        ):
            self.combo_lang.addItem(label, code)
        self.combo_lang.setToolTip("Spoken language")

        row.addWidget(self.btn_transcribe)
        row.addWidget(source)
        row.addWidget(self.combo_lang, 1)
        self.stack.addWidget(page)

        # --- Explain ---
        page, row = self._page()
        self.btn_explain = self._btn("Explain highlight", "sparkles", "primary",
                                     tip="Select text in any app first, then click or use the shortcut")
        self.btn_explain.clicked.connect(lambda: self.ask_highlight_requested.emit())
        self.btn_snip = self._btn("Snip text", "crop", "secondary", tip="Drag over part of the screen to read its text")
        self.btn_snip.clicked.connect(lambda: self.snip_screen_requested.emit())
        kbd = QLabel("Ctrl + Shift + Space")
        kbd.setObjectName("kbd")
        kbd.setToolTip("Global shortcut for Explain highlight")
        row.addWidget(self.btn_explain)
        row.addWidget(self.btn_snip)
        row.addStretch(1)
        row.addWidget(kbd)
        self.stack.addWidget(page)

        # --- Record ---
        page, row = self._page()
        self.btn_record = self._btn("Record", "rec_dot", "danger")
        self.btn_record.clicked.connect(self._handle_record_click)
        self.combo_target = QComboBox()
        self.combo_target.addItem("Entire screen", None)
        self.combo_target.setToolTip("What to record")
        self.btn_refresh = self._tool_button("refresh", "Refresh window list")
        self.btn_refresh.clicked.connect(lambda: self.refresh_windows_requested.emit())
        self.mic_toggle = self._btn("Mic", "mic", "chip", checkable=True, tip="Mix your microphone into the recording", icon_px=16)
        self.mic_toggle.setChecked(True)
        self.timer_label = QLabel("00:00")
        self.timer_label.setObjectName("timer")
        self.timer_label.setVisible(False)
        row.addWidget(self.btn_record)
        row.addWidget(self.combo_target, 1)
        row.addWidget(self.btn_refresh)
        row.addWidget(self.mic_toggle)
        row.addWidget(self.timer_label)
        self.stack.addWidget(page)

        tab = int(self._prefs.get("tab", 0))
        tab = tab if 0 <= tab < 3 else 0
        self.stack.setCurrentIndex(tab)
        self._tab_buttons[tab].setChecked(True)
        return self.stack

    def _build_pane(self):
        pane = QFrame()
        pane.setObjectName("pane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(2, 2, 2, 2)
        self.output_box = OutputView()
        layout.addWidget(self.output_box)
        return pane

    def _build_footer(self):
        row = QHBoxLayout()
        row.setContentsMargins(4, 0, 0, 0)
        row.setSpacing(4)
        if getattr(config, "STT_ENGINE", "whisper") == "whisper":
            note = "PhoWhisper + Whisper base · runs on this device"
        else:
            note = "Speech recognition via Gemini API"
        caption = QLabel(note)
        caption.setObjectName("caption")
        caption.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.btn_copy = self._btn("Copy", "copy", "ghost", icon_px=16)
        self.btn_copy.clicked.connect(self._copy_output)
        self.btn_clear = self._btn("Clear", "trash", "ghost", icon_px=16)
        self.btn_clear.clicked.connect(self._clear_output)
        row.addWidget(caption, 1)
        row.addWidget(self.btn_copy)
        row.addWidget(self.btn_clear)
        return row

    # ------------------------------------------------------------------ theme
    def _is_dark(self):
        if self.theme_pref == "dark":
            return True
        if self.theme_pref == "light":
            return False
        try:
            scheme = QApplication.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return True
            if scheme == Qt.ColorScheme.Light:
                return False
        except Exception:
            pass
        return QApplication.palette().window().color().lightness() < 128

    def _apply_theme(self):
        self.t = dict(DARK if self._is_dark() else LIGHT)
        self.t["chevron"] = _write_chevron(self.t["muted"])
        qss = QSS
        for key, value in self.t.items():
            qss = qss.replace(f"@{key}@", str(value))
        self.setStyleSheet(qss)

        self.status_pill.set_theme(self.t)
        self.lens_mark.set_color(self.t["accent"])
        self.output_box.set_empty_colors(self.t["ink"], self.t["muted"])
        self.output_box.document().setDefaultStyleSheet(self._markdown_css())
        self._refresh_icons()
        self.update()

        # re-render content so colours baked into the document follow the theme
        if self._mode in ("stream", "markdown") and self._stream_buffer:
            self._render_markdown(self._stream_buffer, follow=False, keep_scroll=True)
        elif self._mode == "transcript" and self._transcript:
            self._render_transcript_full()

    def _markdown_css(self):
        t = self.t
        mono = "Consolas, 'Cascadia Mono', monospace"
        return f"""
        h1 {{ font-size: 20px; font-weight: 600; margin-top: 16px; margin-bottom: 8px; }}
        h2 {{ font-size: 17px; font-weight: 600; margin-top: 14px; margin-bottom: 6px; }}
        h3 {{ font-size: 15px; font-weight: 600; margin-top: 12px; margin-bottom: 4px; }}
        p {{ margin-top: 0px; margin-bottom: 10px; line-height: 150%; }}
        ul, ol {{ margin-top: 2px; margin-bottom: 10px; }}
        li {{ margin-bottom: 4px; line-height: 150%; }}
        strong, b {{ font-weight: 600; }}
        a {{ color: {t['link']}; }}
        code {{ font-family: {mono}; color: {t['code_ink']}; background-color: {t['code_bg']}; }}
        pre {{ font-family: {mono}; color: {t['code_ink']}; background-color: {t['code_bg']}; margin-top: 6px; margin-bottom: 10px; }}
        blockquote {{ color: {t['muted']}; margin-left: 14px; }}
        table {{ border-collapse: collapse; margin-top: 6px; margin-bottom: 10px; }}
        th, td {{ border: 1px solid {t['line']}; padding: 6px; }}
        th {{ background-color: {t['raised']}; font-weight: 600; }}
        """

    def paintEvent(self, event):
        """Cheap soft shadow drawn by hand (a QGraphicsEffect would repaint on every pulse/stream update)."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = QRectF(SHADOW, SHADOW + 2, self.width() - 2 * SHADOW, self.height() - 2 * SHADOW)
        peak = self.t.get("shadow_alpha", 90)
        for i in range(SHADOW, 0, -1):
            alpha = int(peak * (1 - i / SHADOW) ** 2 * 0.5)
            p.setPen(QPen(QColor(0, 0, 0, alpha), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(base.adjusted(-i, -i, i, i), 14 + i, 14 + i)

    # ------------------------------------------------------- window behaviour
    def _set_tab(self, index):
        self.stack.setCurrentIndex(index)
        self._persist()

    def _set_pinned(self, on):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(on))
        self.show()
        self._persist()

    def _set_theme(self, key):
        self.theme_pref = key
        self._apply_theme()
        self._persist()

    def _on_opacity_changed(self, value):
        self.current_opacity = value / 100.0
        self.setWindowOpacity(self.current_opacity)

    def _show_menu(self):
        menu = QMenu(self)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        box = QWidget()
        box_l = QVBoxLayout(box)
        box_l.setContentsMargins(12, 8, 12, 8)
        box_l.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(QLabel("Window opacity"))
        head.addStretch(1)
        value_label = QLabel(f"{int(self.current_opacity * 100)}%")
        value_label.setObjectName("caption")
        head.addWidget(value_label)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(30, 100)
        slider.setValue(int(self.current_opacity * 100))
        slider.setMinimumWidth(220)
        slider.valueChanged.connect(lambda v: (self._on_opacity_changed(v), value_label.setText(f"{v}%")))
        box_l.addLayout(head)
        box_l.addWidget(slider)
        widget_action = QWidgetAction(menu)
        widget_action.setDefaultWidget(box)
        menu.addAction(widget_action)
        menu.addSeparator()

        group = QActionGroup(menu)
        group.setExclusive(True)
        for key, label in (("dark", "Dark"), ("light", "Light"), ("system", "Match system")):
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(self.theme_pref == key)
            action.triggered.connect(lambda _checked, k=key: self._set_theme(k))
            group.addAction(action)
            menu.addAction(action)
        menu.addSeparator()
        diag = QAction("Run diagnostics", menu)
        diag.triggered.connect(lambda: self.run_diagnostics_requested.emit())
        menu.addAction(diag)

        menu.exec(self.btn_menu.mapToGlobal(QPoint(0, self.btn_menu.height() + 4)))
        self._persist()

    @staticmethod
    def _is_on_screen(x, y, w, h):
        rect = QRect(x, y, w, h)
        for screen in QApplication.screens():
            inter = screen.availableGeometry().intersected(rect)
            if inter.width() >= 120 and inter.height() >= 60:
                return True
        return False

    def _persist(self):
        geo = self.geometry()
        data = dict(self._prefs)
        data.update({
            "theme": self.theme_pref,
            "opacity": int(self.current_opacity * 100),
            "pinned": bool(self.btn_pin.isChecked()),
            "tab": self.stack.currentIndex(),
            "w": geo.width(), "h": geo.height(), "x": geo.x(), "y": geo.y(),
        })
        self._prefs = data
        _save_prefs(data)

    # --------------------------------------------------------- status handling
    def update_status(self, text: str, is_working: bool = False):
        clean = _clean_status(text)
        low = clean.lower()
        if self.is_recording:
            state = "recording"
        elif is_working:
            state = "listening" if low.startswith("listening") else "working"
        elif self.is_transcribing:
            state = "listening"
            if low.startswith("ready"):
                clean = "Listening"
        else:
            state = "ready"
        self.status_pill.set_state(clean, state)

    def _update_record_clock(self):
        self.record_time = self.record_time.addSecs(1)
        stamp = self.record_time.toString("mm:ss")
        self.timer_label.setText(stamp)
        self.update_status(f"Recording · {stamp}", is_working=True)

    # ------------------------------------------------------------ user actions
    def _copy_output(self):
        text = self.output_box.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.update_status("Copied to clipboard", is_working=False)

    def _clear_output(self):
        self.output_box.clear()
        self._stream_buffer = ""
        self._stream_dirty = False
        self._transcript = []
        self._mode = "empty"
        self.update_status("Ready", is_working=False)

    def populate_windows(self, windows):
        current = self.combo_target.currentData()
        self.combo_target.clear()
        self.combo_target.addItem("Entire screen", None)
        for hwnd, title in windows:
            short = title if len(title) <= 34 else title[:31] + "…"
            self.combo_target.addItem(short, hwnd)
            self.combo_target.setItemData(self.combo_target.count() - 1, title, Qt.ItemDataRole.ToolTipRole)
        idx = self.combo_target.findData(current)
        if idx != -1:
            self.combo_target.setCurrentIndex(idx)

    def _handle_transcribe_click(self):
        self.is_transcribing = not self.is_transcribing
        lang = self.combo_lang.currentData() or "vi"
        is_system = self.src_system.isChecked()
        source_mode = "system" if is_system else "mic"
        where = "computer audio" if is_system else "microphone"

        if self.is_transcribing:
            self._set_btn(self.btn_transcribe, "Stop", "stop", "stop_live")
            for w in (self.combo_lang, self.src_system, self.src_mic):
                w.setEnabled(False)
            self.update_status(f"Listening to {where} · {lang.upper()}", is_working=True)
            self.toggle_transcribe_requested.emit(True, lang, source_mode)
            self.output_box.set_empty_state(
                "Listening…", f"Waiting for speech from your {where}. Play a video or start talking."
            )
        else:
            self._set_btn(self.btn_transcribe, "Start", "mic", "primary")
            for w in (self.combo_lang, self.src_system, self.src_mic):
                w.setEnabled(True)
            self.toggle_transcribe_requested.emit(False, lang, source_mode)
            self.output_box.set_empty_state()
            self.update_status("Ready", is_working=False)

    def _handle_record_click(self):
        self.is_recording = not self.is_recording
        if self.is_recording:
            self._set_btn(self.btn_record, "Stop", "stop", "stop_danger")
            for w in (self.combo_target, self.btn_refresh, self.mic_toggle):
                w.setEnabled(False)
            self.timer_label.setVisible(True)
            self.record_time = QTime(0, 0, 0)
            self.timer_label.setText("00:00")
            self.record_timer.start(1000)
            self.toggle_record_requested.emit(True, self.mic_toggle.isChecked(), self.combo_target.currentData())
        else:
            self._set_btn(self.btn_record, "Record", "rec_dot", "danger")
            for w in (self.combo_target, self.btn_refresh, self.mic_toggle):
                w.setEnabled(True)
            self.record_timer.stop()
            self.timer_label.setVisible(False)
            self.toggle_record_requested.emit(False, self.mic_toggle.isChecked(), None)

    # --------------------------------------------------------- content display
    def _render_markdown(self, text, follow, keep_scroll=False):
        try:
            body = markdown.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
        except Exception:
            body = f"<p>{html.escape(text)}</p>"
        box = self.output_box
        bar = box.verticalScrollBar()
        previous = bar.value()
        stick = follow and bar.value() >= bar.maximum() - 8
        box.setHtml(body)
        if follow and stick:
            QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))
        elif follow or keep_scroll:
            QTimer.singleShot(0, lambda: bar.setValue(previous))
        else:
            QTimer.singleShot(0, lambda: bar.setValue(0))

    def set_result(self, result_text: str):
        self._stream_timer.stop()
        self._stream_dirty = False
        self._stream_buffer = result_text
        self._mode = "markdown"
        self._render_markdown(result_text, follow=False)
        self.update_status("Ready", is_working=False)

    def append_stream_chunk(self, chunk: str):
        starting_new = self._mode != "stream" or (
            self.output_box.document().isEmpty() and not self._stream_dirty
        )
        if starting_new:
            self._stream_buffer = ""
            self._mode = "stream"
        self._stream_buffer += chunk
        self._stream_dirty = True
        if not self._stream_timer.isActive():
            self._stream_timer.start()

    def _flush_stream(self):
        self._stream_dirty = False
        self._render_markdown(self._stream_buffer, follow=True)

    # -- live transcript ----------------------------------------------------------
    def _transcript_formats(self):
        block = QTextBlockFormat()
        block.setBottomMargin(10)
        block.setLineHeight(150.0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        stamp = QTextCharFormat()
        stamp.setForeground(QColor(self.t["faint"]))
        stamp.setFontPointSize(8.25)
        stamp.setFontWeight(QFont.Weight.DemiBold.value)
        plain = QTextCharFormat()
        return block, stamp, plain

    def _insert_paragraph(self, cursor, ts, text, first):
        block, stamp, plain = self._transcript_formats()
        if first:
            cursor.setBlockFormat(block)
        else:
            cursor.insertBlock(block)
        cursor.insertText(ts, stamp)
        cursor.insertText("   ", plain)
        cursor.insertText(text, plain)

    def _render_transcript_full(self):
        paragraphs = list(self._transcript)
        self.output_box.clear()
        self._mode = "transcript"
        cursor = QTextCursor(self.output_box.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.beginEditBlock()
        for i, para in enumerate(paragraphs):
            self._insert_paragraph(cursor, para["ts"], para["text"], first=(i == 0))
        cursor.endEditBlock()
        bar = self.output_box.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def _safe_append_transcript(self, text: str, is_new_paragraph: bool = False):
        box = self.output_box
        doc = box.document()
        first = doc.isEmpty()
        if first:
            self._transcript = []
            self._mode = "transcript"

        bar = box.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 8

        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.beginEditBlock()
        if first or is_new_paragraph:
            ts = time.strftime("%H:%M")
            self._insert_paragraph(cursor, ts, text, first)
            if self._mode == "transcript":
                self._transcript.append({"ts": ts, "text": text})
        else:
            cursor.insertText(" " + text, self._transcript_formats()[2])
            if self._mode == "transcript" and self._transcript:
                self._transcript[-1]["text"] += " " + text
        cursor.endEditBlock()

        if at_bottom or first:
            QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    # --------------------------------------------------------------- lifecycle
    def closeEvent(self, event):
        self._persist()
        QApplication.quit()
        event.accept()
