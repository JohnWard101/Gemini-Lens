# build_exe.py
import os
import shutil
import PyInstaller.__main__

print("🧹 Dọn dẹp thư mục build và dist cũ...")
for folder in ['build', 'dist']:
    if os.path.exists(folder):
        shutil.rmtree(folder, ignore_errors=True)

if os.path.exists('GeminiLens.spec'):
    try:
        os.remove('GeminiLens.spec')
    except Exception:
        pass

print("🚀 Đang biên dịch GeminiLens.exe...")

PyInstaller.__main__.run([
    'main.py',
    '--name=GeminiLens',
    '--onefile',
    '--noconsole',
    '--clean',
    
    # 1. Thu thập Google GenAI & Pydantic
    '--collect-submodules=google.genai',
    '--hidden-import=google',
    '--hidden-import=google.genai',
    '--hidden-import=google.genai.types',
    '--hidden-import=pydantic',
    '--hidden-import=httpx',
    
    # 2. Thu thập Faster-Whisper, CTranslate2, Tokenizers & Markdown
    '--collect-all=faster_whisper',
    '--collect-all=ctranslate2',
    '--collect-all=tokenizers',
    '--collect-all=markdown',
    
    # 3. Thu thập âm thanh, giao diện & phím tắt
    '--collect-all=imageio_ffmpeg',
    '--collect-all=sounddevice',
    '--collect-all=mss',
    '--collect-all=pyaudiowpatch',
    '--hidden-import=pynput.keyboard._win32',
    '--hidden-import=pynput.mouse._win32',
    
    # 4. Loại trừ thư viện rác không dùng đến để tránh phình to file exe
    '--exclude-module=tkinter',
    '--exclude-module=matplotlib',
    '--exclude-module=unittest',
    '--exclude-module=pydoc',
])

print("\n🎉 ĐÃ BIÊN DỊCH THÀNH CÔNG!")
print(f"📁 Đường dẫn file chạy độc lập: {os.path.abspath('dist/GeminiLens.exe')}")