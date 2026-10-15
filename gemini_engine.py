# gemini_engine.py
from __future__ import annotations

import gc
import io
import logging
import os
import re
import threading
import time
from difflib import SequenceMatcher
from typing import Iterator, List, Optional, Tuple

import google.genai as genai
from google.genai import types
import numpy as np
import scipy.io.wavfile as wav

import config

log = logging.getLogger("gemini_engine")

HALLUCINATIONS = [
    "good boy", "the store", "thank you for watching", "thanks for watching",
    "cảm ơn các bạn đã xem", "cảm ơn các bạn đã theo dõi", "subtitles",
    "hãy đăng ký kênh", "subscribe", "chúc các bạn", "that was all for me",
]

NO_SPEECH_MARKERS = [
    "no speech", "no speech detected", "silence",
    "không có lời nói", "không có giọng nói", "không có lời thoại",
]

_PUNCT_RE = re.compile(r"[^\w\s]")
_SPACE_RE = re.compile(r"\s+")
_TAG_ONLY_RE = re.compile(r"^[\[\(\*♪♫][^\]\)]*[\]\)\*♪♫]$", re.S)

_TONE_NORMALIZATION_MAP = {
    "oà": "òa", "oá": "óa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
    "oè": "òe", "oé": "óe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe",
    "uỳ": "ùy", "uý": "úy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy",
}

def _normalize(text: str) -> str:
    return _SPACE_RE.sub(" ", _PUNCT_RE.sub(" ", text.lower())).strip()

_HALLUCINATION_RE = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(_normalize(h)) for h in HALLUCINATIONS) + r")(?!\w)")
_NO_SPEECH = {_normalize(m) for m in NO_SPEECH_MARKERS}


class VietnamesePostProcessor:
    @staticmethod
    def collapse_repeats(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"\b(\w+)(?:\s+\1\b){2,}", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"(\b.+?\b)(?:\s+\1\b)+", r"\1", text, flags=re.IGNORECASE)
        words = text.strip().split()
        if len(words) >= 6:
            unique_ratio = len(set(w.lower() for w in words)) / len(words)
            if unique_ratio < 0.35:
                return ""
        return text.strip()

    @staticmethod
    def normalize_tones(text: str) -> str:
        for old, new in _TONE_NORMALIZATION_MAP.items():
            text = text.replace(old, new).replace(old.upper(), new.upper())
        return text

    @classmethod
    def apply_corrections(cls, text: str) -> str:
        if not text:
            return ""
        text = cls.collapse_repeats(text)
        if not text:
            return ""
        corrections = getattr(config, "VIETNAMESE_DICTIONARY_CORRECTIONS", {})
        for pattern, correct in corrections.items():
            try:
                text = re.sub(pattern, correct, text)
            except re.error:
                pass
        text = cls.normalize_tones(text)
        text = re.sub(r"\s+([,.:;?!])", r"\1", text)
        text = _SPACE_RE.sub(" ", text).strip()
        if text and len(text) > 1:
            text = text[0].upper() + text[1:]
        return text

    @classmethod
    def is_hallucination(cls, text: str, max_len: int = 40) -> bool:
        stripped = text.strip()
        if not stripped or _TAG_ONLY_RE.match(stripped):
            return True
        norm = _normalize(stripped)
        if not norm or norm in _NO_SPEECH:
            return True
        return len(stripped) < max_len and bool(_HALLUCINATION_RE.search(norm))


def _wav_bytes_to_float32(audio_bytes: bytes) -> Optional[np.ndarray]:
    try:
        sr, data = wav.read(io.BytesIO(audio_bytes))
        if data.dtype == np.int16:
            audio = data.astype(np.float32) / 32768.0
        elif data.dtype == np.int32:
            audio = data.astype(np.float32) / 2147483648.0
        elif data.dtype == np.uint8:
            audio = (data.astype(np.float32) - 128.0) / 128.0
        else:
            audio = data.astype(np.float32)
        if audio.ndim > 1:
            audio = np.mean(audio, axis=-1)
        return audio
    except Exception as e:
        log.warning("Không thể decode audio: %s", e)
        return None


class TranscriptContext:
    def __init__(self, max_chars: int = 240, max_overlap_words: int = 8, min_overlap_words: int = 1):
        self.max_chars = max_chars
        self.max_overlap = max_overlap_words
        self.min_overlap = max(1, min_overlap_words)
        self._tail = ""
        self._lock = threading.Lock()
        self._last_reset = time.time()

    def tail(self) -> str:
        with self._lock:
            # Tự động reset context mỗi 5 phút để tránh phình to RAM và giảm tốc độ so khớp chuỗi
            if time.time() - self._last_reset > 300:
                self._tail = ""
                self._last_reset = time.time()
            return self._tail

    def reset(self) -> None:
        with self._lock:
            self._tail = ""
            self._last_reset = time.time()

    def add(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        with self._lock:
            new_words = text.split()
            prev_words = self._tail.split()
            k_max = min(self.max_overlap, len(new_words), len(prev_words))
            for k in range(k_max, self.min_overlap - 1, -1):
                a = " ".join(_normalize(w) for w in prev_words[-k:])
                b = " ".join(_normalize(w) for w in new_words[:k])
                if a == b or (k >= 3 and SequenceMatcher(None, a, b).ratio() >= 0.85):
                    new_words = new_words[k:]
                    break
            fresh = " ".join(new_words)
            if fresh:
                self._tail = f"{self._tail} {fresh}".strip()[-self.max_chars:]
            return fresh


class FastWhisperSTT:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.model_name = getattr(config, "WHISPER_MODEL_NAME", "vudang449/PhoWhisper-small-ct2")
        self.fallback_model = getattr(config, "WHISPER_FALLBACK_MODEL", "base")
        self.device = getattr(config, "WHISPER_DEVICE", "cpu")
        self.compute_type = getattr(config, "WHISPER_COMPUTE_TYPE", "int8")
        self.model = None
        self._load_lock = threading.Lock()
        self._is_available = True
        self._initialized = True
        self._transcribe_count = 0

    def preload(self):
        threading.Thread(target=self._ensure_loaded, daemon=True).start()

    def _ensure_loaded(self) -> bool:
        if self.model is not None:
            return True
        with self._load_lock:
            if self.model is not None:
                return True
            try:
                from faster_whisper import WhisperModel
                cpu_threads = min(4, max(2, os.cpu_count() // 2))

                try:
                    log.info("Đang nạp PhoWhisper-small-ct2 với %d CPU threads...", cpu_threads)
                    self.model = WhisperModel(
                        self.model_name, 
                        device=self.device, 
                        compute_type=self.compute_type,
                        cpu_threads=cpu_threads,
                        num_workers=1
                    )
                    log.info("🎉 PhoWhisper đã sẵn sàng hoạt động!")
                    return True
                except Exception as ex_load:
                    log.warning("Không nạp được PhoWhisper (%s). Dùng model dự phòng...", ex_load)
                    self.model = WhisperModel(
                        self.fallback_model, 
                        device=self.device, 
                        compute_type=self.compute_type,
                        cpu_threads=cpu_threads
                    )
                    return True
            except Exception as e:
                log.exception("Lỗi khi nạp Whisper: %s", e)
                self._is_available = False
                return False

    def transcribe(self, audio_bytes: bytes, language: str = "auto") -> str:
        if not self._is_available or not self._ensure_loaded():
            return ""

        lang_code = "vi" if ("vi" in language.lower() or language == "auto") else language.lower()
        prompt = getattr(config, "TRANSCRIBE_HINT_VI", None) if lang_code == "vi" else getattr(config, "TRANSCRIBE_HINT_EN", None)

        t0 = time.time()
        audio_array = _wav_bytes_to_float32(audio_bytes)
        input_data = audio_array if audio_array is not None else io.BytesIO(audio_bytes)

        beam_size = int(getattr(config, "WHISPER_BEAM_SIZE", 2))
        temperature = getattr(config, "WHISPER_TEMPERATURE", [0.0, 0.2])
        repetition_penalty = float(getattr(config, "WHISPER_REPETITION_PENALTY", 1.15))

        try:
            segments, info = self.model.transcribe(
                input_data,
                language=lang_code,
                beam_size=beam_size,
                temperature=temperature,
                initial_prompt=prompt,
                condition_on_previous_text=False,
                repetition_penalty=repetition_penalty,
                compression_ratio_threshold=2.2,
                no_speech_threshold=0.6,
                vad_filter=False,
            )

            raw_text = " ".join(seg.text for seg in segments).strip()
            
            # TỰ ĐỘNG DỌN RÁC RAM (Garbage Collection) sau mỗi 20 lần transcribe để tránh phình RAM
            self._transcribe_count += 1
            if self._transcribe_count >= 20:
                self._transcribe_count = 0
                gc.collect()

            log.info("PhoWhisper STT [%s] xong trong %.2fs: %r", lang_code, time.time() - t0, raw_text)
            return raw_text
        except Exception as e:
            log.error("Lỗi transcribe: %s", e)
            return ""


class GeminiEngine:
    def __init__(self):
        timeout_ms = max(10_000, int(getattr(config, "GEMINI_TIMEOUT_MS", 10_000)))
        self.client = genai.Client(
            api_key=config.get_api_key(),
            http_options=types.HttpOptions(timeout=timeout_ms),
        )

        self.fast_model = getattr(config, "GEMINI_FAST_MODEL", "gemini-flash-lite-latest")
        self.general_model = getattr(config, "GEMINI_GENERAL_MODEL", "gemini-flash-lite-latest")
        self.reply_language = getattr(config, "REPLY_LANGUAGE", "Vietnamese")

        self.whisper = FastWhisperSTT()
        if getattr(config, "STT_ENGINE", "whisper") == "whisper":
            self.whisper.preload()

    def transcribe_audio(self, audio_bytes: bytes, language: str = "auto", context: str = "") -> str:
        if not audio_bytes:
            return ""

        if getattr(config, "STT_ENGINE", "whisper") == "whisper" and self.whisper._is_available:
            try:
                raw_text = self.whisper.transcribe(audio_bytes=audio_bytes, language=language)
                if raw_text:
                    cleaned = VietnamesePostProcessor.apply_corrections(raw_text)
                    if not VietnamesePostProcessor.is_hallucination(cleaned):
                        return cleaned
                return ""
            except Exception as e:
                log.warning("Whisper STT lỗi: %s", e)
        return ""

    def analyze_highlighted_text(self, text: str, screen_bytes: bytes = None, instruction: str = "") -> str:
        prompt = f"Analyze this highlighted text:\n\"\"\"\n{text}\n\"\"\"\n\n{instruction or 'Provide a concise explanation.'}"
        contents = [prompt]
        if screen_bytes:
            contents.append(types.Part.from_bytes(data=screen_bytes, mime_type=_image_mime(screen_bytes)))
        cfg = types.GenerateContentConfig(system_instruction=f"Answer in {self.reply_language}.", temperature=0.3)
        try:
            response = self.client.models.generate_content(model=self.general_model, contents=contents, config=cfg)
            return (getattr(response, "text", None) or "").strip() or "(Không có nội dung)"
        except Exception as e:
            return str(e)

    def analyze_highlighted_text_stream(self, text: str, screen_bytes: bytes = None, instruction: str = "") -> Iterator[str]:
        prompt = f"Analyze this highlighted text:\n\"\"\"\n{text}\n\"\"\"\n\n{instruction or 'Provide a concise explanation.'}"
        contents = [prompt]
        if screen_bytes:
            contents.append(types.Part.from_bytes(data=screen_bytes, mime_type=_image_mime(screen_bytes)))
        cfg = types.GenerateContentConfig(system_instruction=f"Answer in {self.reply_language}.", temperature=0.3)
        try:
            for chunk in self.client.models.generate_content_stream(model=self.general_model, contents=contents, config=cfg):
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"\nError: {e}"

    def extract_text_from_image(self, image_bytes: bytes) -> str:
        prompt = "Extract ALL text from this image exactly as written. Output ONLY the text."
        contents = [prompt, types.Part.from_bytes(data=image_bytes, mime_type=_image_mime(image_bytes))]
        cfg = types.GenerateContentConfig(temperature=0.0)
        try:
            response = self.client.models.generate_content(model=self.general_model, contents=contents, config=cfg)
            return (getattr(response, "text", None) or "").strip() or "(Không tìm thấy chữ)"
        except Exception as e:
            return str(e)

def _image_mime(data: bytes, default: str = "image/jpeg") -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return default