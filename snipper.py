# snipper.py
from PyQt6.QtCore import Qt, QRect, pyqtSignal, QBuffer, QIODevice
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtGui import QPainter, QColor, QPen, QFont


class SnippingWidget(QWidget):
    snippet_captured = pyqtSignal(bytes)  # Trả về JPEG bytes

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.start_pos = None
        self.end_pos = None
        self.is_snipping = False

    def start(self):
        # Bao phủ toàn bộ các màn hình (Virtual Geometry)
        geo = QApplication.primaryScreen().virtualGeometry()
        self.setGeometry(geo)
        self.start_pos = None
        self.end_pos = None
        self.is_snipping = True
        self.show()

    def paintEvent(self, event):
        if not self.is_snipping:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Làm tối nền xung quanh
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        if self.start_pos and self.end_pos:
            rect = QRect(self.start_pos, self.end_pos).normalized()

            # Đục lỗ trong suốt vùng chọn
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # Viền phát sáng màu Cyan/Indigo
            pen = QPen(QColor(99, 102, 241), 2)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Hiển thị thước đo kích thước (HUD)
            w, h = rect.width(), rect.height()
            if w > 40 and h > 20:
                dim_text = f"{w} × {h}"
                painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                painter.fillRect(rect.x(), max(0, rect.y() - 22), 85, 20, QColor(15, 23, 42, 220))
                painter.setPen(QColor(241, 245, 249))
                painter.drawText(rect.x() + 8, max(14, rect.y() - 7), dim_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = event.pos()
            self.end_pos = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self.start_pos:
            self.end_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.start_pos and self.end_pos:
            rect = QRect(self.start_pos, self.end_pos).normalized()
            self.hide()
            self.is_snipping = False

            if rect.width() > 10 and rect.height() > 10:
                screen = QApplication.screenAt(self.start_pos) or QApplication.primaryScreen()
                pixmap = screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())

                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                pixmap.save(buffer, "JPEG", quality=95)
                self.snippet_captured.emit(buffer.data().data())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.is_snipping = False