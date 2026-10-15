# screen_recorder.py
import cv2
import numpy as np
import mss
import sounddevice as sd
import scipy.io.wavfile as wav
import threading
import time
import os
import subprocess
import imageio_ffmpeg
from datetime import datetime
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32


def get_open_windows():
    """Lấy danh sách các cửa sổ đang hiển thị trên màn hình."""
    windows = []

    def enum_proc(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()
                excluded = ["Program Manager", "Settings", "Default IME", "MSCTFIME UI"]
                if title and not any(x in title for x in excluded):
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w > 100 and h > 100:
                        windows.append((hwnd, title))
        return True

    ENUM_PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(ENUM_PROC(enum_proc), 0)
    return windows


def _find_wasapi_loopback():
    """Tìm thiết bị Loopback để ghi lại toàn bộ âm thanh phát ra từ loa máy tính."""
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        wasapi_id = next((i for i, h in enumerate(hostapis) if "WASAPI" in h["name"].upper()), None)
        if wasapi_id is not None:
            for idx, d in enumerate(devices):
                if d["hostapi"] == wasapi_id and d["max_input_channels"] > 0:
                    if "loopback" in d["name"].lower() or d.get("is_loopback", False):
                        return idx
    except Exception:
        pass
    return None


class ScreenRecorder:
    def __init__(self, output_dir="recordings"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.is_recording = False
        self.include_mic = False
        self.target_hwnd = None
        self.sample_rate = 44100
        self.fps = 30.0

        self.audio_frames = []
        self.mic_frames = []
        self._lock = threading.Lock()

        self.temp_video = os.path.join(self.output_dir, "temp_video.avi")
        self.temp_audio = os.path.join(self.output_dir, "temp_audio.wav")
        self.sct = mss.mss()

    def _get_target_rect(self):
        """Tính toạ độ chuẩn (kích thước chẵn) của màn hình hoặc cửa sổ."""
        mon = self.sct.monitors[1]
        screen_w, screen_h = mon["width"], mon["height"]

        if self.target_hwnd and user32.IsWindow(self.target_hwnd):
            rect = wintypes.RECT()
            user32.GetWindowRect(self.target_hwnd, ctypes.byref(rect))
            x = max(0, min(rect.left, screen_w - 100))
            y = max(0, min(rect.top, screen_h - 100))
            w = max(100, min(rect.right - rect.left, screen_w - x))
            h = max(100, min(rect.bottom - rect.top, screen_h - y))
        else:
            x, y, w, h = mon["left"], mon["top"], screen_w, screen_h

        # Codec yêu cầu chiều dài/rộng là số chẵn
        w -= (w % 2)
        h -= (h % 2)
        return {"left": x, "top": y, "width": w, "height": h}

    def _record_screen(self):
        region = self._get_target_rect()
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(self.temp_video, fourcc, self.fps, (region["width"], region["height"]))

        frame_interval = 1.0 / self.fps
        next_tick = time.time()

        while self.is_recording:
            if self.target_hwnd:
                curr = self._get_target_rect()
                region["left"], region["top"] = curr["left"], curr["top"]

            img = np.array(self.sct.grab(region))
            frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            out.write(frame)

            next_tick += frame_interval
            sleep_time = next_tick - time.time()

            # Nếu máy giật lag trễ quá 2 khung hình, đặt lại mốc để tránh desync âm thanh
            if sleep_time < -frame_interval * 2:
                next_tick = time.time()
            elif sleep_time > 0:
                time.sleep(sleep_time)

        out.release()

    def _audio_callback(self, indata, frames, time_info, status):
        if self.is_recording:
            with self._lock:
                self.audio_frames.append(indata.copy())

    def _mic_callback(self, indata, frames, time_info, status):
        if self.is_recording:
            with self._lock:
                self.mic_frames.append(indata.copy())

    def start_recording(self, include_mic: bool = False, target_hwnd: int = None):
        self.include_mic = include_mic
        self.target_hwnd = target_hwnd
        self.is_recording = True
        self.audio_frames.clear()
        self.mic_frames.clear()

        # 1. Luồng quay màn hình
        self.video_thread = threading.Thread(target=self._record_screen, daemon=True)
        self.video_thread.start()

        # 2. Thu âm hệ thống (Ưu tiên WASAPI Loopback)
        loopback_dev = _find_wasapi_loopback()
        try:
            self.sys_stream = sd.InputStream(
                device=loopback_dev,
                samplerate=self.sample_rate,
                channels=2,
                dtype="float32",
                callback=self._audio_callback
            )
            self.sys_stream.start()
        except Exception:
            self.sys_stream = None

        # 3. Thu âm Micro (nếu được bật)
        self.mic_stream = None
        if self.include_mic:
            try:
                self.mic_stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    callback=self._mic_callback
                )
                self.mic_stream.start()
            except Exception:
                pass

    def stop_recording(self) -> str:
        self.is_recording = False
        if self.sys_stream:
            try:
                self.sys_stream.stop()
                self.sys_stream.close()
            except Exception:
                pass
        if self.mic_stream:
            try:
                self.mic_stream.stop()
                self.mic_stream.close()
            except Exception:
                pass

        if hasattr(self, 'video_thread'):
            self.video_thread.join()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_mp4 = os.path.join(self.output_dir, f"recording_{timestamp}.mp4")

        self._save_combined_audio()
        self._merge_video_audio(final_mp4)
        return final_mp4

    def _save_combined_audio(self):
        with self._lock:
            has_sys = bool(self.audio_frames)
            has_mic = bool(self.mic_frames)
            sys_audio = np.concatenate(self.audio_frames, axis=0) if has_sys else None
            mic_audio = np.concatenate(self.mic_frames, axis=0) if has_mic else None

        if sys_audio is None and mic_audio is None:
            wav.write(self.temp_audio, self.sample_rate, np.zeros((self.sample_rate, 2), dtype=np.int16))
            return

        if sys_audio is None:
            sys_audio = np.zeros((len(mic_audio), 2), dtype=np.float32)

        if self.include_mic and mic_audio is not None:
            if mic_audio.shape[1] == 1:
                mic_audio = np.repeat(mic_audio, 2, axis=1)
            min_len = min(len(sys_audio), len(mic_audio))
            final_audio = (sys_audio[:min_len] * 0.7) + (mic_audio[:min_len] * 0.7)
        else:
            final_audio = sys_audio

        scaled = np.int16(np.clip(final_audio, -1.0, 1.0) * 32767)
        wav.write(self.temp_audio, self.sample_rate, scaled)

    def _merge_video_audio(self, output_path):
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe, "-y",
            "-i", self.temp_video,
            "-i", self.temp_audio,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for tmp in (self.temp_video, self.temp_audio):
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass