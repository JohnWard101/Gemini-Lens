# config.py
import json
import os
import sys
from dotenv import load_dotenv

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
load_dotenv(os.path.join(BASE_DIR, ".env"))

def get_api_key():
    key = os.getenv("GEMINI_API_KEY")
    if key and key.strip():
        return key.strip()
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("GEMINI_API_KEY", "").strip()
        except Exception:
            pass
    return ""

def save_api_key(key: str):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"GEMINI_API_KEY": key.strip()}, f, ensure_ascii=False, indent=2)

# ============================================================================
# Cấu hình STT: PhoWhisper tối ưu hóa chống tràn RAM
# ============================================================================
STT_ENGINE = os.getenv("STT_ENGINE", "whisper").lower()

WHISPER_MODEL_NAME = "vudang449/PhoWhisper-small-ct2"
WHISPER_FALLBACK_MODEL = "base"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"

WHISPER_BEAM_SIZE = 2
WHISPER_TEMPERATURE = [0.0, 0.2]
WHISPER_REPETITION_PENALTY = 1.15

# ============================================================================
# Cấu hình Gemini API (Fallback)
# ============================================================================
GEMINI_FAST_MODEL = "gemini-flash-lite-latest"
GEMINI_GENERAL_MODEL = "gemini-flash-lite-latest"
GEMINI_FALLBACK_MODEL = "gemini-3.5-flash-lite"

GEMINI_STT_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
]

GEMINI_TIMEOUT_MS = 10_000
GEMINI_STT_BUDGET_S = 12.0
REPLY_LANGUAGE = "Vietnamese"

# ============================================================================
# Cấu hình Thu âm & VAD (Tối ưu để không kẹt hàng đợi)
# ============================================================================
AUDIO_SAMPLE_RATE = 16000
RECORDINGS_DIR = os.path.join(BASE_DIR, "recordings")

AUDIO_RMS_THRESHOLD = 0.005
AUDIO_SILENCE_SEC = 0.8
AUDIO_PRE_BUFFER_SEC = 0.4
AUDIO_TAIL_SEC = 0.3

AUDIO_MIN_SPEECH_SEC = 2.0    
AUDIO_MAX_SEGMENT_SEC = 6.0   
AUDIO_OVERLAP_SEC = 0.4

TRANSCRIBE_HINT_VI = "Vì sao chúng ta ăn ba bữa một ngày? Lịch sử loài người và khoa học dinh dưỡng."
TRANSCRIBE_HINT_EN = "This is a video presentation with clear English speech."

VIETNAMESE_DICTIONARY_CORRECTIONS = {
    r"(?i)\b(?:ga\s+lê\s+li)\b": "Galile",
    r"(?i)\b(?:ô\s+ha)\b": "Ohalo",
    r"(?i)\b(?:i\s+tạng)\b": "ý tưởng",
}

SCREEN_FPS = 1.0
DIFF_THRESHOLD = 15.0
MAX_IMAGE_DIM = (1280, 720)
# ============================================================================
# Cấu hình Giao diện (UI Settings)
# ============================================================================
UI_OPACITY = float(os.getenv("UI_OPACITY", 0.96))      # Độ trong suốt nền (0.2 đến 1.0)
UI_SCALE = float(os.getenv("UI_SCALE", 1.0))            # Tỷ lệ phóng to/thu nhỏ UI (0.8 đến 1.5)