# ui_overlay.py
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QTime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTextBrowser, QFrame, QGraphicsDropShadowEffect,
    QCheckBox, QComboBox, QSlider
)
from PyQt6.QtGui import QColor, QFont, QTextCursor
import markdown
import config


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
        self.is_recording = False
        self.is_transcribing = False
        self.record_time = QTime(0, 0, 0)
        self.record_timer = QTimer()
        self.record_timer.timeout.connect(self._update_record_clock)
        
        self._stream_buffer = ""
        self.current_opacity = float(getattr(config, "UI_OPACITY", 0.96))

        self.init_ui()
        self.signal_append_transcript.connect(self._safe_append_transcript)

    def init_ui(self):
        # Standard window so it behaves like a normal application (resizable, minimizable, taskbar-friendly)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle("Gemini Lens Pro")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(self.current_opacity)
        self.setFont(QFont("Segoe UI", 10))
        self.setMinimumSize(540, 400)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)

        self.container = QFrame(self)
        self.container.setObjectName("container")
        self.container.setStyleSheet("""
            QFrame#container {
                background-color: rgba(18, 20, 29, 0.98);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.15);
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 6)
        self.container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.container)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 10, 14, 14)

        # 1. HEADER
        header = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #10B981; font-size: 13px;")

        self.title_label = QLabel("GEMINI LENS PRO")
        self.title_label.setStyleSheet("color: #E2E8F0; font-weight: 700; font-size: 11px; letter-spacing: 1px;")

        engine_mode = getattr(config, "STT_ENGINE", "whisper").upper()
        engine_text = "⚡ PHOWHISPER" if engine_mode == "WHISPER" else "🌐 GEMINI CLOUD"
        self.badge_engine = QLabel(engine_text)
        self.badge_engine.setStyleSheet("background: rgba(16, 185, 129, 0.15); color: #34D399; border: 1px solid #10B981; border-radius: 4px; padding: 1px 6px; font-size: 9px; font-weight: bold;")

        self.btn_diag = QPushButton("🧪 Test")
        self.btn_diag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_diag.setStyleSheet("QPushButton { background: rgba(99, 102, 241, 0.2); color: #A5B4FC; border: 1px solid #6366F1; border-radius: 4px; padding: 2px 7px; font-size: 10px; font-weight: bold; } QPushButton:hover { background: #6366F1; color: white; }")
        self.btn_diag.clicked.connect(lambda: self.run_diagnostics_requested.emit())

        self.btn_close = QPushButton("✕")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet("QPushButton { background: transparent; color: #94A3B8; border: none; font-size: 13px; font-weight: bold; } QPushButton:hover { color: #EF4444; }")
        self.btn_close.clicked.connect(lambda: QApplication.quit())

        header.addWidget(self.status_dot)
        header.addWidget(self.title_label)
        header.addWidget(self.badge_engine)
        header.addStretch()
        header.addWidget(self.btn_diag)
        header.addWidget(self.btn_close)
        layout.addLayout(header)

        # 1.5 OPACITY SLIDER BAR (Thanh trượt độ trong suốt trực tiếp)
        slider_bar = QHBoxLayout()
        lbl_slider = QLabel("👁️ Opacity:")
        lbl_slider.setStyleSheet("color: #94A3B8; font-size: 11px; font-weight: bold;")
        
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)  # Từ 20% đến 100% độ hiển thị
        self.opacity_slider.setValue(int(self.current_opacity * 100))
        self.opacity_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.opacity_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #334155;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #6366F1;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
        """)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        
        self.lbl_opacity_val = QLabel(f"{int(self.current_opacity * 100)}%")
        self.lbl_opacity_val.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: bold; min-width: 35px;")

        slider_bar.addWidget(lbl_slider)
        slider_bar.addWidget(self.opacity_slider, 1)
        slider_bar.addWidget(self.lbl_opacity_val)
        layout.addLayout(slider_bar)

        # 2. ACTION ROW
        action_row = QHBoxLayout()
        self.btn_explain = QPushButton("✨ Explain Highlight (Ctrl+Shift+Space)")
        self.btn_explain.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_explain.setStyleSheet("QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #8B5CF6); color: white; font-weight: 600; font-size: 11px; border-radius: 6px; padding: 7px; border: none; }")
        self.btn_explain.clicked.connect(lambda: self.ask_highlight_requested.emit())

        self.btn_snip = QPushButton("✂️ Snip & OCR")
        self.btn_snip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_snip.setStyleSheet("QPushButton { background-color: #0EA5E9; color: white; font-weight: 600; font-size: 11px; border-radius: 6px; padding: 7px; border: none; }")
        self.btn_snip.clicked.connect(lambda: self.snip_screen_requested.emit())

        action_row.addWidget(self.btn_explain, 2)
        action_row.addWidget(self.btn_snip, 1)
        layout.addLayout(action_row)

        # 3. TRANSCRIBE BAR
        transcribe_bar = QHBoxLayout()
        self.btn_transcribe = QPushButton("🎙️ Start Transcribe")
        self.btn_transcribe.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_transcribe.setStyleSheet("QPushButton { background-color: #10B981; color: white; font-weight: 600; font-size: 11px; border-radius: 6px; padding: 6px 10px; border: none; }")
        self.btn_transcribe.clicked.connect(self._handle_transcribe_click)

        self.combo_source = QComboBox()
        self.combo_source.addItems(["🔊 Âm thanh Máy tính (Video)", "🎙️ Micro (Nói)"])
        self.combo_source.setStyleSheet("QComboBox { background-color: #1E293B; color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 4px 6px; font-size: 11px; }")

        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["Tự động (Auto)", "Tiếng Việt (Vietnamese)", "English"])
        self.combo_lang.setStyleSheet("QComboBox { background-color: #1E293B; color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 4px 6px; font-size: 11px; }")

        transcribe_bar.addWidget(self.btn_transcribe)
        transcribe_bar.addWidget(self.combo_source)
        transcribe_bar.addWidget(self.combo_lang)
        transcribe_bar.addStretch()
        layout.addLayout(transcribe_bar)

        # 4. RECORDING BAR
        rec_bar = QHBoxLayout()
        self.btn_record = QPushButton("⏺ Record")
        self.btn_record.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_record.setStyleSheet("QPushButton { background-color: #DC2626; color: white; font-weight: 600; font-size: 11px; border-radius: 6px; padding: 6px 10px; border: none; }")
        self.btn_record.clicked.connect(self._handle_record_click)

        self.combo_target = QComboBox()
        self.combo_target.setStyleSheet("QComboBox { background-color: #1E293B; color: #F1F5F9; border: 1px solid rgba(255,255,255,0.15); border-radius: 6px; padding: 4px 6px; font-size: 11px; }")
        self.combo_target.addItem("🖥️ Entire Screen", None)

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet("QPushButton { background: #334155; color: white; border: none; border-radius: 6px; padding: 4px 8px; font-size: 11px; }")
        self.btn_refresh.clicked.connect(lambda: self.refresh_windows_requested.emit())

        self.mic_toggle = QCheckBox("Mic")
        self.mic_toggle.setChecked(True)
        self.mic_toggle.setStyleSheet("QCheckBox { color: #CBD5E1; font-size: 11px; }")

        self.timer_label = QLabel("00:00")
        self.timer_label.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 11px;")
        self.timer_label.setVisible(False)

        rec_bar.addWidget(self.btn_record)
        rec_bar.addWidget(self.combo_target, 1)
        rec_bar.addWidget(self.btn_refresh)
        rec_bar.addWidget(self.mic_toggle)
        rec_bar.addWidget(self.timer_label)
        layout.addLayout(rec_bar)

        # 5. STATUS BAR
        status_bar = QHBoxLayout()
        self.feed_label = QLabel("⚡ Ready")
        self.feed_label.setStyleSheet("color: #94A3B8; font-size: 10px; background: rgba(0,0,0,0.3); padding: 3px 8px; border-radius: 4px;")

        self.btn_copy = QPushButton("📋 Copy")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setStyleSheet("QPushButton { background: rgba(255,255,255,0.06); color: #CBD5E1; border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; padding: 2px 7px; font-size: 10px; }")
        self.btn_copy.clicked.connect(self._copy_output)

        self.btn_clear = QPushButton("🗑️ Clear")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet("QPushButton { background: rgba(255,255,255,0.06); color: #CBD5E1; border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; padding: 2px 7px; font-size: 10px; }")
        self.btn_clear.clicked.connect(self._clear_output)

        status_bar.addWidget(self.feed_label)
        status_bar.addStretch()
        status_bar.addWidget(self.btn_copy)
        status_bar.addWidget(self.btn_clear)
        layout.addLayout(status_bar)

        # 6. WORKSPACE
        self.output_box = QTextBrowser()
        self.output_box.setOpenExternalLinks(True)
        self.output_box.setPlaceholderText("Transcripts, OCR text, and formatted explanations will appear here...")
        self.output_box.setStyleSheet("""
            QTextBrowser {
                background-color: rgba(13, 17, 23, 0.95);
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 10px;
                font-size: 12px;
                line-height: 1.5;
            }
        """)
        layout.addWidget(self.output_box, 1)

        main_layout.addWidget(self.container)
        self.resize(560, 420)

    def _on_opacity_changed(self, value):
        opacity = value / 100.0
        self.setWindowOpacity(opacity)
        self.lbl_opacity_val.setText(f"{value}%")

    def _update_record_clock(self):
        self.record_time = self.record_time.addSecs(1)
        self.timer_label.setText(self.record_time.toString("mm:ss"))

    def _copy_output(self):
        text = self.output_box.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.update_status("📋 Copied to clipboard!", is_working=False)

    def _clear_output(self):
        self.output_box.clear()
        self._stream_buffer = ""
        self.update_status("⚡ Ready", is_working=False)

    def populate_windows(self, windows):
        current_data = self.combo_target.currentData()
        self.combo_target.clear()
        self.combo_target.addItem("🖥️ Entire Screen", None)
        for hwnd, title in windows:
            short_title = title if len(title) <= 30 else title[:27] + "..."
            self.combo_target.addItem(f"🪟 {short_title}", hwnd)

        idx = self.combo_target.findData(current_data)
        if idx != -1:
            self.combo_target.setCurrentIndex(idx)

    def _handle_transcribe_click(self):
        self.is_transcribing = not self.is_transcribing
        selected_lang = "Vietnamese" if "Vietnamese" in self.combo_lang.currentText() else ("English" if "English" in self.combo_lang.currentText() else "auto")
        is_system_sound = "Máy tính" in self.combo_source.currentText()
        source_mode = "system" if is_system_sound else "mic"

        if self.is_transcribing:
            self.btn_transcribe.setText("⏹️ Stop Transcribe")
            self.btn_transcribe.setStyleSheet("background-color: #4B5563; color: white; font-weight: 600; font-size: 11px; border-radius: 6px; padding: 6px 10px; border: none;")
            self.combo_lang.setEnabled(False)
            self.combo_source.setEnabled(False)
            
            mode_desc = "Video Máy tính" if is_system_sound else "Micro"
            self.update_status(f"🎙️ Đang nghe ({mode_desc})...", is_working=True)
            self.toggle_transcribe_requested.emit(True, selected_lang, source_mode)
        else:
            self.btn_transcribe.setText("🎙️ Start Transcribe")
            self.btn_transcribe.setStyleSheet("background-color: #10B981; color: white; font-weight: 600; font-size: 11px; border-radius: 6px; padding: 6px 10px; border: none;")
            self.combo_lang.setEnabled(True)
            self.combo_source.setEnabled(True)
            self.update_status("⚡ Ready", is_working=False)
            self.toggle_transcribe_requested.emit(False, selected_lang, source_mode)

    def _handle_record_click(self):
        self.is_recording = not self.is_recording
        if self.is_recording:
            self.btn_record.setText("⏹ Stop")
            self.btn_record.setStyleSheet("background-color: #4B5563; color: white; border-radius: 6px; padding: 6px 10px; font-weight: 600;")
            self.combo_target.setEnabled(False)
            self.btn_refresh.setEnabled(False)
            self.mic_toggle.setEnabled(False)
            self.timer_label.setVisible(True)
            self.record_time = QTime(0, 0, 0)
            self.timer_label.setText("00:00")
            self.record_timer.start(1000)
            target_hwnd = self.combo_target.currentData()
            self.toggle_record_requested.emit(True, self.mic_toggle.isChecked(), target_hwnd)
        else:
            self.btn_record.setText("⏺ Record")
            self.btn_record.setStyleSheet("background-color: #DC2626; color: white; border-radius: 6px; padding: 6px 10px; font-weight: 600;")
            self.combo_target.setEnabled(True)
            self.btn_refresh.setEnabled(True)
            self.mic_toggle.setEnabled(True)
            self.record_timer.stop()
            self.timer_label.setVisible(False)
            self.toggle_record_requested.emit(False, self.mic_toggle.isChecked(), None)

    def update_status(self, text: str, is_working: bool = False):
        self.feed_label.setText(text)
        color = "#F59E0B" if is_working else "#10B981"
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 13px;")

    def set_result(self, result_text: str):
        self._stream_buffer = result_text
        html_content = markdown.markdown(result_text, extensions=['fenced_code', 'tables', 'nl2br'])
        
        styled_html = f"""
        <style>
            body {{ color: #F8FAFC; font-family: 'Segoe UI', sans-serif; font-size: 12px; line-height: 1.5; }}
            strong, b {{ color: #38BDF8; font-weight: bold; }}
            em, i {{ color: #A5B4FC; font-style: italic; }}
            code {{ background-color: #1E293B; color: #34D399; padding: 2px 4px; border-radius: 4px; font-family: monospace; }}
            pre code {{ background-color: #0F172A; display: block; padding: 8px; border-radius: 6px; border: 1px solid #334155; }}
            blockquote {{ border-left: 3px solid #6366F1; margin: 0; padding-left: 8px; color: #94A3B8; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #334155; padding: 6px; text-align: left; }}
            th {{ background-color: #1E293B; color: #F1F5F9; }}
        </style>
        {html_content}
        """
        self.output_box.setHtml(styled_html)
        self.output_box.moveCursor(QTextCursor.MoveOperation.End)
        self.update_status("⚡ Ready", is_working=False)

    def append_stream_chunk(self, chunk: str):
        self._stream_buffer += chunk
        html_content = markdown.markdown(self._stream_buffer, extensions=['fenced_code', 'tables', 'nl2br'])
        
        styled_html = f"""
        <style>
            body {{ color: #F8FAFC; font-family: 'Segoe UI', sans-serif; font-size: 12px; line-height: 1.5; }}
            strong, b {{ color: #38BDF8; font-weight: bold; }}
            em, i {{ color: #A5B4FC; font-style: italic; }}
            code {{ background-color: #1E293B; color: #34D399; padding: 2px 4px; border-radius: 4px; font-family: monospace; }}
            pre code {{ background-color: #0F172A; display: block; padding: 8px; border-radius: 6px; border: 1px solid #334155; }}
        </style>
        {html_content}
        """
        self.output_box.setHtml(styled_html)
        self.output_box.moveCursor(QTextCursor.MoveOperation.End)

    def _safe_append_transcript(self, text: str, is_new_paragraph: bool = False):
        cursor = self.output_box.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        current = self.output_box.toPlainText().strip()
        if not current:
            cursor.insertText(f"🗣️ {text}")
        elif is_new_paragraph:
            cursor.insertText(f"\n\n🗣️ {text}")
        else:
            cursor.insertText(f" {text}")

        self.output_box.setTextCursor(cursor)
        self.output_box.ensureCursorVisible()

    def closeEvent(self, event):
        QApplication.quit()
        event.accept()