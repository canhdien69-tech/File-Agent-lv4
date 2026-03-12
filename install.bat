@echo off
chcp 65001 >nul
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║      ☀  SUNNY AI v5.0 — Installer           ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: Check Python 3.10+
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    echo         Install Python 3.10+ from https://python.org
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER%

:: Check pip
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pip not found.
    pause & exit /b 1
)

echo.
echo [1/5] PyTorch...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 -q 2>nul
if %errorlevel% neq 0 (
    echo       CUDA version failed, installing CPU...
    pip install torch -q
)
echo       Done.

echo [2/5] AI model (unsloth)...
pip install unsloth transformers accelerate bitsandbytes -q
if %errorlevel% neq 0 (
    echo       [WARN] unsloth failed - app will run in demo mode.
)

echo [3/5] Vector memory...
pip install faiss-cpu sentence-transformers -q
if %errorlevel% neq 0 (
    echo       [WARN] FAISS not installed - JSON memory fallback.
)

echo [4/5] Web + tools...
pip install fastapi uvicorn websockets duckduckgo-search ^
            requests beautifulsoup4 ^
            PyPDF2 python-docx openpyxl pandas ^
            psutil -q
echo       Done.

echo [5/5] Optional (voice)...
pip install edge-tts pygame SpeechRecognition -q
echo       Done.

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║  Installation complete!                      ║
echo  ║                                              ║
echo  ║  Run:  python sunny_web.py                   ║
echo  ║  Open: http://localhost:7860                 ║
echo  ╚══════════════════════════════════════════════╝
echo.
pause
