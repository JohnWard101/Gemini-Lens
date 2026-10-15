# selection_grabber.py
import time
import platform
import pyperclip
from pynput.keyboard import Controller, Key

keyboard = Controller()
IS_MAC = platform.system() == "Darwin"


def get_selected_text() -> str:
    """Lấy văn bản đang được bôi đen từ bất kỳ ứng dụng nào trên Windows/Mac."""
    try:
        original_clipboard = pyperclip.paste()
    except Exception:
        original_clipboard = ""

    # Dọn clipboard tạm thời để theo dõi khi nào có dữ liệu mới
    pyperclip.copy("")

    modifier = Key.cmd if IS_MAC else Key.ctrl
    try:
        with keyboard.pressed(modifier):
            keyboard.press('c')
            keyboard.release('c')
    except Exception:
        pass

    # Polling nhanh: Kiểm tra clipboard mỗi 15ms, tối đa 200ms
    # Giúp lấy văn bản cực nhạy (thường chỉ mất 20ms - 40ms)
    selected_text = ""
    for _ in range(14):
        time.sleep(0.015)
        try:
            val = pyperclip.paste()
            if val and val.strip():
                selected_text = val.strip()
                break
        except Exception:
            pass

    # Nếu không bôi đen chữ nào, trả lại nội dung cũ của clipboard
    if not selected_text:
        try:
            pyperclip.copy(original_clipboard)
        except Exception:
            pass
        return ""

    return selected_text