🔍 GeminiLens Pro
Ứng dụng Desktop thông minh được xây dựng bằng Python và PyQt6, tích hợp trí tuệ nhân tạo Google Gemini và mô hình nhận diện giọng nói cục bộ PhoWhisper / Faster-Whisper.
✨ Tính năng nổi bật
🎙️ Real-time Speech-to-Text (STT): Transcribe âm thanh hệ thống (video YouTube, nhạc, cuộc họp) hoặc Micro trực tiếp với độ chính xác cao nhờ mô hình PhoWhisper, hỗ trợ bộ lọc khử nhiễu nhạc nền và từ điển hậu xử lý tiếng Việt thông minh.
✨ Explain Highlight (Ctrl + Shift + Space): Tự động bôi đen chữ trên màn hình và nhờ Gemini phân tích, giải thích tức thì.
✂️ Snip & OCR: Chụp màn hình vùng tùy chọn và trích xuất toàn bộ văn bản (OCR) bằng AI.
🔴 Screen & Audio Recorder: Quay màn hình kèm âm thanh hệ thống và Microphone thành file MP4.
🎨 Giao diện hiện đại: Hỗ trợ render Markdown đầy đủ (Bold, Italic, Tables, Code block) và tùy chỉnh độ trong suốt linh hoạt.
🛠️ Cài đặt và Chạy ứng dụng
Clone repository về máy:
git clone https://github.com/Tên_Tài_Khoản_Của_Bạn/gemini-lens-pro.git
cd gemini-lens-pro
Tạo và kích hoạt môi trường ảo (Khuyên dùng):
python -m venv venv
venv\Scripts\activate (Trên Windows)
Cài đặt các thư viện phụ thuộc:
pip install -r requirements.txt
Cấu hình API Key:
Tạo một file tên là .env ở thư mục gốc.
Thêm dòng sau vào file .env:
GEMINI_API_KEY=12345_Api_Key_Của_Bạn_Ở_Đây
Khởi chạy ứng dụng:
python main.py
🚀 Biên dịch thành File .exe độc lập
Nếu bạn muốn đóng gói ứng dụng thành file chạy .exe trên Windows:
python build_exe.py
File thực thi độc lập sẽ được tạo và nằm trong thư mục dist/GeminiLens.exe.
