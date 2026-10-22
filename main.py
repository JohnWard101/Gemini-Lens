# main.py
import sys
import os

if getattr(sys, 'frozen', False):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    import google
    google_dir = os.path.join(base_path, 'google')
    try:
        google.__path__.append(google_dir)
    except Exception:
        google.__path__ = [google_dir]

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.FileHandler("app.log", encoding="utf-8")],
)
log = logging.getLogger("main")

import time
import threading
import sounddevice as sd
import numpy as np
import imageio_ffmpeg
from PyQt6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont

import config
from screen_tracker import ScreenTracker
from audio_tracker import AudioTracker
from screen_recorder import ScreenRecorder, get_open_windows
from gemini_engine import GeminiEngine, TranscriptContext
from ui_overlay import ModernOverlayUI, AIWorker, AIStreamWorker
from snipper import SnippingWidget
from selection_grabber import get_selected_text
from pynput import keyboard


class GeminiApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setFont(QFont("Segoe UI", 10))

        api_key = config.get_api_key()
        if not api_key:
            key, ok = QInputDialog.getText(
                None, "Gemini Setup", "Enter your Google Gemini API Key:", QLineEdit.EchoMode.Password
            )
            if ok and key.strip():
                config.save_api_key(key.strip())
            else:
                QMessageBox.critical(None, "Error", "Gemini API Key is required.")
                sys.exit(1)

        self.ui = ModernOverlayUI()
        self.engine = GeminiEngine()
        self.screen_tracker = ScreenTracker()
        self.recorder = ScreenRecorder(output_dir=config.RECORDINGS_DIR)
        self.snipper = SnippingWidget()
        self.worker = None

        self.transcribe_active = False
        self.current_lang = "auto"
        self.ctx = TranscriptContext()
        self.hotkey_listener = None
        self.last_speech_time = 0.0

        # Kết nối Signals
        self.ui.ask_highlight_requested.connect(self.handle_selected_text)
        self.ui.toggle_record_requested.connect(self.handle_record_toggle)
        self.ui.toggle_transcribe_requested.connect(self.handle_transcribe_toggle)
        self.ui.snip_screen_requested.connect(self.handle_snip_trigger)
        self.ui.run_diagnostics_requested.connect(self.run_full_system_test)
        self.ui.refresh_windows_requested.connect(self.refresh_window_list)
        self.snipper.snippet_captured.connect(self.handle_snippet_received)

        self.app.aboutToQuit.connect(self.cleanup)

        # Khởi động Audio Tracker
        self.audio_tracker = AudioTracker(callback=self.on_audio_chunk_captured)

        self.refresh_window_list()
        self.init_global_hotkey()
        self.ui.show()

    def refresh_window_list(self):
        windows = get_open_windows()
        self.ui.populate_windows(windows)

    def init_global_hotkey(self):
        def on_activate():
            self.ui.ask_highlight_requested.emit()
        self.hotkey_listener = keyboard.GlobalHotKeys({'<ctrl>+<shift>+<space>': on_activate})
        threading.Thread(target=self.hotkey_listener.run, daemon=True).start()

    def handle_snip_trigger(self):
        self.ui.hide()
        QTimer.singleShot(250, self.snipper.start)

    def handle_snippet_received(self, image_bytes: bytes):
        self.ui.show()
        self.ui.update_status("🔍 Extracting text (OCR)...", is_working=True)
        self.ui.output_box.setPlainText("Reading snippet...")

        self.worker = AIWorker(self.engine.extract_text_from_image, image_bytes)
        self.worker.finished.connect(self.ui.set_result)
        self.worker.error.connect(lambda err: self.ui.set_result(f"OCR Error: {err}"))
        self.worker.start()

    def handle_transcribe_toggle(self, is_active: bool, language: str, source_mode: str = "system"):
        self.transcribe_active = is_active
        if "Auto" in language:
            self.current_lang = "auto"
        elif "Vietnamese" in language or "Việt" in language:
            self.current_lang = "Vietnamese"
        elif "English" in language:
            self.current_lang = "English"
        else:
            self.current_lang = language

        self.ctx.reset()
        self.last_speech_time = 0.0

        if is_active:
            self.audio_tracker.set_source_mode(source_mode)
            self.audio_tracker.start()
            self.ui.output_box.clear()
            src_desc = "Âm thanh máy tính (Video)" if source_mode == "system" else "Microphone"
            self.ui.output_box.setPlaceholderText(f"🎙️ Đang lắng nghe ({src_desc})... Hãy bật video hoặc bắt đầu nói.")
        else:
            self.audio_tracker.stop()

    def on_audio_chunk_captured(self, audio_bytes: bytes):
        if not self.transcribe_active or self.recorder.is_recording:
            return
        try:
            raw = self.engine.transcribe_audio(
                audio_bytes, self.current_lang, context=self.ctx.tail()
            )
            fresh = self.ctx.add(raw) if raw else ""
            if fresh:
                now = time.time()
                is_new_paragraph = (self.last_speech_time == 0.0) or ((now - self.last_speech_time) > 2.5)
                self.last_speech_time = now
                self.ui.signal_append_transcript.emit(fresh, is_new_paragraph)
        except Exception:
            log.exception("Lỗi khi xử lý Transcribe audio chunk")

    def handle_selected_text(self):
        selected_text = get_selected_text()
        if not selected_text:
            selected_text = self.ui.output_box.textCursor().selectedText().strip()

        if not selected_text:
            self.ui.set_result("⚠️ No text highlighted! Select text on screen or inside the workspace first.")
            return

        self.ui.update_status("🧠 Gemini analyzing selection...", is_working=True)
        self.ui.output_box.clear()
        screen_bytes = self.screen_tracker.get_latest_bytes()

        if hasattr(self.engine, "analyze_highlighted_text_stream"):
            def stream_task():
                return self.engine.analyze_highlighted_text_stream(selected_text, screen_bytes)

            self.worker = AIStreamWorker(stream_task)
            self.worker.chunk_received.connect(self.ui.append_stream_chunk)
            self.worker.finished.connect(lambda: self.ui.update_status("⚡ Ready", is_working=False))
            self.worker.error.connect(lambda err: self.ui.set_result(f"Error: {err}"))
            self.worker.start()
        else:
            self.worker = AIWorker(self.engine.analyze_highlighted_text, selected_text, screen_bytes)
            self.worker.finished.connect(self.ui.set_result)
            self.worker.error.connect(lambda err: self.ui.set_result(f"Error: {err}"))
            self.worker.start()

    def handle_record_toggle(self, start: bool, include_mic: bool, target_hwnd: object):
        if start:
            target_desc = "Selected App" if target_hwnd else "Full Screen"
            self.ui.update_status(f"🔴 Recording ({target_desc})...", is_working=True)
            self.recorder.start_recording(include_mic=include_mic, target_hwnd=target_hwnd)
        else:
            self.ui.update_status("⏳ Finalizing MP4 file...", is_working=True)
            def stop_task():
                out_path = self.recorder.stop_recording()
                return f"✅ Recording successfully saved to:\n{out_path}"

            self.worker = AIWorker(stop_task)
            self.worker.finished.connect(self.ui.set_result)
            self.worker.start()

    def run_full_system_test(self):
        self.ui.update_status("🧪 Running Diagnostics...", is_working=True)
        self.ui.output_box.setPlainText("Running self-test on all systems...\n")

        def test_task():
            results = ["=== 🧪 SYSTEM DIAGNOSTIC REPORT ==="]
            stt_mode = getattr(config, "STT_ENGINE", "whisper")
            if stt_mode == "whisper" and getattr(self.engine, "whisper", None) and self.engine.whisper._is_available:
                results.append(
                    f"✅ STT Engine: Local Faster-Whisper "
                    f"(vi: {config.WHISPER_VI_MODEL} · other: {config.WHISPER_MULTI_MODEL})"
                )
            else:
                results.append(f"ℹ️ STT Engine: Gemini API Fallback")
            return "\n".join(results)

        self.worker = AIWorker(test_task)
        self.worker.finished.connect(self.ui.set_result)
        self.worker.error.connect(lambda err: self.ui.set_result(f"Diagnostics error: {err}"))
        self.worker.start()

    def cleanup(self):
        if hasattr(self, 'audio_tracker'):
            self.audio_tracker.stop()
        if hasattr(self, 'recorder') and self.recorder.is_recording:
            self.recorder.stop_recording()
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
        os._exit(0)

    def run(self):
        self.app.exec()
        self.cleanup()


if __name__ == "__main__":
    app = GeminiApp()
    app.run()
