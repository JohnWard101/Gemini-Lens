# 🔍 GeminiLens Pro

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-UI-green.svg)
![Gemini](https://img.shields.io/badge/Google-Gemini%20AI-orange.svg)
![PhoWhisper](https://img.shields.io/badge/STT-PhoWhisper-purple.svg)

*Ứng dụng Desktop thông minh hỗ trợ Transcribe thời gian thực, Giải thích văn bản bằng AI và OCR màn hình.*

</div>

---

## ✨ Tính năng nổi bật

- **🎙️ Real-time Speech-to-Text (STT):** Transcribe âm thanh hệ thống (video YouTube, nhạc, cuộc họp) hoặc Micro trực tiếp với độ chính xác cao nhờ mô hình **PhoWhisper**, tích hợp bộ lọc khử nhiễu nhạc nền và từ điển hậu xử lý tiếng Việt chuẩn xác 99%.
- **✨ Explain Highlight (`Ctrl + Shift + Space`):** Tự động bôi đen chữ trên màn hình và nhờ Gemini phân tích, giải thích trực tiếp.
- **✂️ Snip & OCR:** Chụp màn hình vùng tùy chọn và trích xuất toàn bộ văn bản (OCR) bằng AI.
- **🔴 Screen & Audio Recorder:** Quay màn hình kèm âm thanh hệ thống và Microphone thành file MP4.
- **🎨 Giao diện hiện đại:** Hỗ trợ render Markdown đầy đủ (Bold, Italic, Tables, Code block) và tùy chỉnh độ trong suốt linh hoạt qua menu trực quan.

---

## 🛠️ Cài đặt và Chạy ứng dụng

### 1. Clone repository về máy
```bash
git clone https://github.com/Tên_Tài_Khoản_Của_Bạn/gemini-lens-pro.git
cd gemini-lens-pro
```
### 2. Tạo và kích hoạt môi trường ảo
```bash
python -m venv venv
venv\Scripts\activate    # Trên Windows
```
### 3. Cài đặt các thư viện phụ thuộc
``` bash
pip install -r requirements.txt
```
### 4. Cấu hình Biến môi trường
Tạo một file tên là .env ở thư mục gốc của dự án và thêm vào nội dung sau:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
```
### 5. Khởi chạy ứng dụng
```bash
python main.py
```
### 🚀 Biên dịch thành File .exe độc lập
Nếu bạn muốn đóng gói ứng dụng thành file chạy .exe duy nhất trên Windows:
```bash
python build_exe.py
```
File thực thi độc lập sẽ được tạo và nằm trong thư mục dist/GeminiLens.exe.
### 📂 Cấu trúc dự án
```bash
gemini-lens-pro/
│
├── main.py              # File khởi chạy chính của ứng dụng
├── config.py            # Cấu hình hệ thống, từ điển hậu xử lý
├── gemini_engine.py     # Động cơ AI Gemini & PhoWhisper STT
├── audio_tracker.py     # Quản lý thu âm hệ thống & lọc ồn
├── screen_tracker.py    # Theo dõi màn hình & bắt sự kiện
├── screen_recorder.py   # Quay video màn hình và âm thanh
├── ui_overlay.py        # Giao diện PyQt6 (Markdown, Opacity)
├── snipper.py           # Công cụ cắt ảnh màn hình (Snip & OCR)
├── selection_grabber.py # Bắt chữ bôi đen màn hình
├── build_exe.py         # Script đóng gói PyInstaller
├── requirements.txt     # Thư viện yêu cầu
└── .gitignore           # Cấu hình loại trừ file bảo mật
```
