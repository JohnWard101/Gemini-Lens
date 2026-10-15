# audio_tracker.py
import io
import logging
import queue
import threading
import time

import numpy as np
import scipy.io.wavfile as wav
import scipy.signal as signal

import config

log = logging.getLogger("audio_tracker")


class AudioTracker:
    BLOCK_SEC = 0.05

    def __init__(self, callback):
        self.sample_rate = config.AUDIO_SAMPLE_RATE
        self.callback = callback
        self.is_running = False
        self.source_mode = "system"

        self._read_config()
        self._reset_state()
        # GIỚI HẠN TỐI ĐA 8 MỤC TRONG QUEUE: Tránh trễ real-time khi máy chạy lâu bị nghẽn
        self._queue = queue.Queue(maxsize=8)
        self._worker_thread = None
        self._capture_thread = None
        self.pa = None

        try:
            self._hp_b, self._hp_a = signal.butter(2, 80 / (self.sample_rate / 2), btype="highpass")
        except Exception:
            self._hp_b, self._hp_a = None, None

    def _read_config(self):
        self.rms_threshold = float(getattr(config, "AUDIO_RMS_THRESHOLD", 0.005))
        self.silence_limit = int(getattr(config, "AUDIO_SILENCE_SEC", 0.8) / self.BLOCK_SEC)
        self.pre_blocks = int(getattr(config, "AUDIO_PRE_BUFFER_SEC", 0.4) / self.BLOCK_SEC)
        self.tail_blocks = int(getattr(config, "AUDIO_TAIL_SEC", 0.3) / self.BLOCK_SEC)
        self.min_blocks = int(getattr(config, "AUDIO_MIN_SPEECH_SEC", 2.0) / self.BLOCK_SEC)
        self.max_blocks = int(getattr(config, "AUDIO_MAX_SEGMENT_SEC", 6.0) / self.BLOCK_SEC)
        self.overlap_blocks = int(getattr(config, "AUDIO_OVERLAP_SEC", 0.4) / self.BLOCK_SEC)

    def _reset_state(self):
        self.blocks = []
        self.pre_buffer = []
        self.silent_count = 0
        self.last_loud_idx = -1
        self.is_speaking = False
        self.noise_floor = self.rms_threshold * 0.5

    def set_source_mode(self, mode: str):
        if mode != self.source_mode:
            self.source_mode = mode
            if self.is_running:
                log.info("Chuyển nguồn âm thanh sang: %s", mode)
                self.stop()
                self.start()

    def _apply_audio_filters(self, audio: np.ndarray) -> np.ndarray:
        if self._hp_b is not None and self._hp_a is not None:
            try:
                filtered = signal.lfilter(self._hp_b, self._hp_a, audio)
                return filtered.astype(np.float32)
            except Exception:
                pass
        return audio

    def _process_audio_chunk(self, raw_data, in_rate, in_channels):
        try:
            audio_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0

            if in_channels > 1:
                audio_data = audio_data.reshape(-1, in_channels)
                mono = np.mean(audio_data, axis=1)
            else:
                mono = audio_data

            if in_rate != self.sample_rate:
                target_samples = int(len(mono) * self.sample_rate / in_rate)
                block = signal.resample(mono, target_samples).astype(np.float32)
            else:
                block = mono

            block = self._apply_audio_filters(block)
            rms = float(np.sqrt(np.mean(block ** 2)))

            if not self.is_speaking and rms < self.rms_threshold:
                self.noise_floor = self.noise_floor * 0.95 + rms * 0.05

            dynamic_threshold = max(self.rms_threshold, self.noise_floor * 1.6)
            is_sound = rms > dynamic_threshold

            if is_sound:
                if not self.is_speaking:
                    self.is_speaking = True
                    self.blocks = list(self.pre_buffer)
                    self.pre_buffer.clear()

                self.blocks.append(block)
                self.last_loud_idx = len(self.blocks) - 1
                self.silent_count = 0
            elif self.is_speaking:
                self.blocks.append(block)
                self.silent_count += 1
                if self.silent_count >= self.silence_limit:
                    self._finish_segment()
            else:
                self.pre_buffer.append(block)
                if len(self.pre_buffer) > self.pre_blocks:
                    self.pre_buffer.pop(0)

            if self.is_speaking and len(self.blocks) >= self.max_blocks:
                self._submit(self.blocks)
                self.blocks = self.blocks[-self.overlap_blocks:]
                self.last_loud_idx = len(self.blocks) - 1
        except Exception as e:
            log.error("Lỗi xử lý audio chunk: %s", e)

    def _finish_segment(self):
        end = min(len(self.blocks), self.last_loud_idx + 1 + self.tail_blocks)
        segment = self.blocks[:end]
        self.blocks.clear()
        self.last_loud_idx = -1
        self.silent_count = 0
        self.is_speaking = False

        if not segment:
            return

        if len(segment) < self.min_blocks:
            needed_blocks = self.min_blocks - len(segment)
            left_pad = needed_blocks // 2
            right_pad = needed_blocks - left_pad
            empty_block = np.zeros(int(self.sample_rate * self.BLOCK_SEC), dtype=np.float32)
            segment = [empty_block] * left_pad + segment + [empty_block] * right_pad

        self._submit(segment)

    def _submit(self, blocks):
        if not blocks:
            return
        audio = np.concatenate(blocks).astype(np.float32)
        try:
            self._queue.put_nowait(audio)
        except queue.Full:
            # Nếu queue đầy (máy đang xử lý đoạn trước), tự động bỏ qua đoạn cũ nhất để luôn lấy tiếng mới nhất
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(audio)
            except Exception:
                pass

    def _worker_loop(self):
        while self.is_running:
            try:
                audio_array = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if audio_array is None:
                break

            try:
                max_val = float(np.max(np.abs(audio_array)))
                if max_val > 0.001:
                    audio_array = (audio_array / max_val) * 0.95

                byte_io = io.BytesIO()
                wav.write(byte_io, self.sample_rate, np.int16(audio_array * 32767))
                raw_bytes = byte_io.getvalue()
                self.callback(raw_bytes)
            except Exception:
                log.exception("Lỗi trong audio worker loop")
            finally:
                self._queue.task_done()

    def _capture_loop(self):
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            log.error("Chưa cài đặt PyAudioWPatch.")
            return

        self.pa = pyaudio.PyAudio()
        stream = None

        try:
            if self.source_mode == "system":
                wasapi_info = self.pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                default_speakers = self.pa.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
                
                loopback_dev = None
                if not default_speakers.get("isLoopbackDevice", False):
                    for dev in self.pa.get_loopback_device_info_generator():
                        if default_speakers["name"] in dev["name"]:
                            loopback_dev = dev
                            break
                else:
                    loopback_dev = default_speakers

                if loopback_dev is None:
                    dev_index = None
                    channels = 1
                    rate = 16000
                else:
                    dev_index = loopback_dev["index"]
                    channels = loopback_dev["maxInputChannels"]
                    rate = int(loopback_dev["defaultSampleRate"])
            else:
                dev_index = None
                channels = 1
                rate = 16000

            chunk_size = int(rate * self.BLOCK_SEC)
            stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=dev_index,
                frames_per_buffer=chunk_size
            )

            while self.is_running:
                data = stream.read(chunk_size, exception_on_overflow=False)
                self._process_audio_chunk(data, rate, channels)

        except Exception as e:
            log.exception("Lỗi luồng thu âm: %s", e)
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if self.pa:
                try:
                    self.pa.terminate()
                except Exception:
                    pass

    def start(self) -> bool:
        if self.is_running:
            return True
        self.is_running = True
        self._reset_state()

        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        return True

    def stop(self):
        self.is_running = False
        if self._worker_thread and self._worker_thread.is_alive():
            try:
                self._queue.put_nowait(None)
            except Exception:
                pass
        self._reset_state()