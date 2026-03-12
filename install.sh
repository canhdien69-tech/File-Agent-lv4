#!/bin/bash
set -e

echo ""
echo " ╔══════════════════════════════════════════════╗"
echo " ║      ☀  SUNNY AI v5.0 — Installer           ║"
echo " ╚══════════════════════════════════════════════╝"
echo ""

# Python check
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found. Install Python 3.10+"
    exit 1
fi
PYVER=$(python3 --version)
echo "[OK] $PYVER"

echo ""
echo "[1/6] PyTorch (QUAN TRONG: cai truoc, dung --no-deps)..."
if command -v nvcc &>/dev/null; then
    echo "      CUDA detected — GPU version"
    pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121 \
        --index-url https://download.pytorch.org/whl/cu121 --no-deps -q
else
    echo "      No CUDA — CPU version"
    pip install torch -q
fi

echo "[2/6] Transformers + bitsandbytes..."
pip install transformers==4.51.0 tokenizers==0.21.0 huggingface-hub==0.29.0 \
    accelerate bitsandbytes --no-deps -q \
    || echo "      [WARN] AI libs failed — demo mode only"

echo "[3/6] Vector memory..."
pip install faiss-cpu sentence-transformers -q \
    || echo "      [WARN] FAISS not installed — JSON fallback"

echo "[4/6] Web server..."
pip install fastapi "uvicorn==0.41.0" "websockets==12.0" python-multipart psutil -q

echo "[5/6] Tools..."
pip install duckduckgo-search requests beautifulsoup4 \
    PyPDF2 python-docx openpyxl pandas -q

echo "[6/6] Optional (voice)..."
pip install edge-tts pygame SpeechRecognition -q \
    || echo "      [WARN] Voice libs optional, skipping"

echo ""
echo " ╔══════════════════════════════════════════════╗"
echo " ║  Installation complete!                      ║"
echo " ║                                              ║"
echo " ║  Run:  python3 -m uvicorn sunny_web:app      ║"
echo " ║        --host 0.0.0.0 --port 7860            ║"
echo " ║  Open: http://localhost:7860                 ║"
echo " ╚══════════════════════════════════════════════╝"
echo ""
