# screen_tracker.py
import io
import mss
import numpy as np
from PIL import Image
from config import MAX_IMAGE_DIM, DIFF_THRESHOLD


class ScreenTracker:
    def __init__(self):
        self.sct = mss.mss()
        self.last_frame = None
        self.monitor = self.sct.monitors[1]

    def capture_frame(self) -> Image.Image:
        """Chụp màn hình chính và nén tỉ lệ nhanh, tiết kiệm RAM/CPU."""
        sct_img = self.sct.grab(self.monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        # Dùng BILINEAR để giảm tải CPU tối đa thay vì LANCZOS nặng nề
        img.thumbnail(MAX_IMAGE_DIM, Image.Resampling.BILINEAR)
        return img

    def has_screen_changed(self, current_img: Image.Image) -> bool:
        """Kiểm tra màn hình có thay đổi đáng kể không để tránh gọi API thừa."""
        small = current_img.resize((64, 36), Image.Resampling.NEAREST).convert("L")
        current_array = np.asarray(small, dtype=np.int16)

        if self.last_frame is None:
            self.last_frame = current_array
            return True

        diff = float(np.mean(np.abs(current_array - self.last_frame)))
        self.last_frame = current_array
        return diff > DIFF_THRESHOLD

    def get_latest_bytes(self) -> bytes:
        img = self.capture_frame()
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=80, optimize=False)
        return buffer.getvalue()