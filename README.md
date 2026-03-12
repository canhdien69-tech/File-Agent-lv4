<div align="center">

# ☀️ Sunny AI v5.0
### Local AI Agent Framework

**AI agent chạy hoàn toàn local. Không cloud. Không rò dữ liệu.**

![Agent Level](https://img.shields.io/badge/Agent_Level-4_(ReAct)-brightgreen)
![License](https://img.shields.io/badge/License-CC_BY--NC_4.0-blue)
![Python](https://img.shields.io/badge/Python-3.10+-green)
![CUDA](https://img.shields.io/badge/CUDA-12.1-76B900?logo=nvidia)

</div>

---

## ⚡ Quick Start

```bash
# Windows
install.bat

# Linux / Mac
chmod +x install.sh && ./install.sh
```

```bash
# Chạy server
python -m uvicorn sunny_web:app --host 0.0.0.0 --port 7860
```

Mở browser: **http://localhost:7860**

> ⚠️ **Không dùng** `python sunny_web.py` — một số máy bị thoát ngay.
> Hoặc double-click **run.bat** (Windows) để chạy nhanh.

---

## 🎙️ Voice & Phone

### Voice (TTS/STT)
- **TTS** — Sunny tự đọc reply ra loa, tự động nếu đã cài đủ thư viện
- **STT** — Bấm nút 🎤 Mic trên UI, nói vào mic, Sunny nghe và xử lý

```bash
pip install edge-tts pygame SpeechRecognition
```

### Phone (ADB)
1. Bật **USB Debugging**: Cài đặt → Giới thiệu → Bấm **Số bản dựng 7 lần** → Tùy chọn nhà phát triển → Bật USB Debugging
2. Cắm điện thoại vào máy tính bằng USB
3. Cài [ADB driver](https://developer.android.com/studio/releases/platform-tools)
4. Kiểm tra kết nối: `adb devices`
5. Nói với Sunny: *"Xem pin điện thoại"* hoặc *"Chụp màn hình điện thoại"*

---

## 💬 Example Prompts

| Mục đích | Ví dụ |
|---|---|
| 🌐 Web search | `Tìm tin tức AI mới nhất hôm nay` |
| 📄 Đọc file | `Phân tích file "C:\Users\you\report.xlsx"` |
| 📊 Tạo báo cáo | `Tạo báo cáo từ file "data.pdf"` |
| 🗑️ Dọn máy | `Scan file rác trong C:\Temp` |
| 📱 Điện thoại | `Xem pin điện thoại` |
| 🧠 Nhớ lại | `Em nhớ gì về cuộc trò chuyện trước?` |
| 🐍 Tính toán | `Tính sin(45 độ) cho em` |
| 💻 Hệ thống | `Kiểm tra phiên bản Python đang dùng` |

---

## 📁 Cấu trúc

```
sunny_v5/
├── core/
│   ├── config.py      ← Tất cả config tập trung
│   ├── brain.py       ← SunnyBrain: LLM inference + ReAct loop
│   ├── memory.py      ← VectorMemory (FAISS) + ConversationManager
│   ├── planner.py     ← Planning loop + Retry + Replan
│   └── sandbox.py     ← Security: path, code execution, shell guard
├── tools/
│   ├── web.py         ← DuckDuckGo search + URL fetch
│   ├── reader.py      ← PDF / DOCX / XLSX / TXT (RAM guard)
│   ├── scanner.py     ← Folder junk scan
│   ├── phone.py       ← ADB phone control
│   └── executor.py    ← Python exec + Shell run (sandboxed)
├── sunny_web.py       ← Web UI (FastAPI + WebSocket)
├── run.bat            ← Double-click để chạy (Windows)
├── install.bat        ← Installer Windows
├── install.sh         ← Installer Linux/Mac
├── requirements.txt   ← Danh sách thư viện
└── README.md
```

---

## 🐛 Lỗi thường gặp

<details>
<summary><b>❌ "module 'torch' has no attribute 'int1'"</b></summary>

Nguyên nhân thật sự là thư viện **torchao** bị xung đột. Nhổ cỏ tận gốc:

```bash
pip uninstall torchao -y
```

Nếu vẫn lỗi mới cần cài lại torch 2.5.1:

```bash
pip install torch==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121 --no-deps --force-reinstall
```

Nếu vẫn lỗi → app tự chạy **demo mode** (UI và tools vẫn hoạt động, chỉ không có LLM).
</details>

<details>
<summary><b>❌ "No module named 'core'"</b></summary>

Tên thư mục phải là `core` **chữ thường**. Đổi tên trong File Explorer nếu đang là `Core`.
</details>

<details>
<summary><b>❌ WebSocket "Connecting..." không chuyển thành "Connected"</b></summary>

- Dùng file `sunny_web.py` mới nhất. Reload trang bằng `Ctrl+Shift+R`.
- Nếu vẫn không được: Nhấn **F12** xem có báo chữ đỏ `SyntaxError` không. Nếu có là do code bị sai khoảng trắng hoặc thiếu chữ `r` trước chuỗi HTML → chạy lại file gốc của repo.
</details>

<details>
<summary><b>❌ "python sunny_web.py" chạy xong thoát liền</b></summary>

Dùng lệnh uvicorn thay thế:

```bash
python -m uvicorn sunny_web:app --host 0.0.0.0 --port 7860
```
</details>

<details>
<summary><b>❌ torchvision "Entry Point Not Found" popup</b></summary>

torchvision bị corrupt. Fix:

```bash
pip install torchvision==0.20.1+cu121 --index-url https://download.pytorch.org/whl/cu121 --no-deps --force-reinstall
```
</details>

<details>
<summary><b>❌ F5 reload trang → mất chat, WebSocket ngắt</b></summary>

Bình thường — F5 ngắt kết nối WebSocket. Đợi 2-3 giây tự reconnect, hoặc đóng tab mở lại http://localhost:7860.
</details>

---

## ✨ Tính năng

### Agent Core

| Feature | Mô tả |
|---|---|
| 🧠 Vector Memory | FAISS + sentence-transformers — nhớ ngữ nghĩa, persist qua restart |
| 📖 Episodic Memory | Diary — lịch sử hội thoại theo thời gian, agent có thể đọc lại |
| 🔧 LLM Tool Calling | Model tự quyết tool qua JSON schema |
| 📋 Planning Loop | Goal → Plan → Execute → Observe → Reply |
| 🔄 ReAct Loop | Think → Act → Observe → Critic → Loop (autonomous) |
| 🔁 Retry + Replan | Retry 3 lần, nếu fail → LLM tự tạo plan thay thế |
| 🛡️ Sandbox | Path traversal, symlink, code execution, shell command guard |

### Tools (10 tools)

| Tool | Mô tả |
|---|---|
| 🌐 Web Search | DuckDuckGo — không tracking |
| 🔗 URL Fetch | Đọc và clean nội dung web |
| 📄 File Reader | PDF/DOCX/XLSX/TXT — RAM guard |
| 📁 Folder Scan | Tìm file rác |
| 📱 Phone ADB | pin, screenshot, home, back |
| 🐍 Python Exec | Chạy Python code an toàn (sandboxed) |
| 💻 Shell Run | Chạy shell command an toàn (whitelist) |
| 🗒️ Read Diary | Đọc lại lịch sử hội thoại |
| 🧹 Scan Temp | Scan file rác hệ thống |
| 🗑️ Delete Temp | Xóa file rác hệ thống |

### Engineering
- Auto model selection: 3B (VRAM <7GB) / 8B (VRAM ≥7GB) / CPU fallback
- CUDA OOM handler + CPU fallback
- Inference timeout 120s — không deadlock
- Lock timeout 130s — không block vĩnh viễn
- Context window guard
- Repeated action guard — chống agent stuck loop
- Atomic JSON write (tmp → os.replace)
- Log rotation tự động

---

## 🔧 Cài đặt thủ công

> ⚠️ **QUAN TRỌNG** — Phải cài đúng thứ tự, sai thứ tự bị conflict!

```bash
# Bước 1: Cài torch TRƯỚC với --no-deps (bắt buộc)
pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121 --no-deps --force-reinstall

# Bước 2: Cài AI model
pip install transformers accelerate bitsandbytes

# Bước 3: Vector memory
pip install faiss-cpu sentence-transformers

# Bước 4: Web server
pip install fastapi "uvicorn[standard]" websockets python-multipart psutil

# Bước 5: Tools
pip install duckduckgo-search requests beautifulsoup4
pip install PyPDF2 python-docx openpyxl pandas

# Bước 6: Voice (tuỳ chọn)
pip install edge-tts pygame SpeechRecognition
```

---

## 💻 Yêu cầu hệ thống

| Cấu hình | RAM | VRAM | Model |
|---|---|---|---|
| Tối thiểu | 8GB | — | Llama 3.2 3B Instruct (CPU) |
| Khuyến nghị | 8GB | 4GB+ | Llama 3.2 3B Instruct (GPU) |
| Tốt nhất | 16GB | 8GB+ | Hermes 3 8B (GPU) |

> ⚠️ **Bắt buộc dùng bản Instruct**: `unsloth/Llama-3.2-3B-Instruct-bnb-4bit`
> Nếu dùng bản Base, AI sẽ không biết trả lời chat — chỉ nói lảm nhảm.

---

## ⚙️ Cấu hình (`core/config.py`)

```python
ENABLE_FILE_ACCESS = True   # Cho phép đọc file
ALLOW_INTERNET     = True   # Cho phép web search
ENABLE_PHONE       = True   # Cho phép ADB

# Thêm path bị chặn
BLOCKED_PATH_PATTERNS = [
    r"(?i)c:\\windows",
    r"(?i)/etc/passwd",
    # thêm vào đây...
]

PLAN_MAX_STEPS   = 5   # Tối đa bước mỗi plan
PLAN_MAX_RETRIES = 3   # Retry mỗi step
VECTOR_TOP_K     = 3   # Số memory liên quan
```

---

## 🏗️ Architecture

```
User Input
    │
    ▼
VectorMemory.search()      ← Tìm context liên quan (FAISS + Diary)
    │
    ▼
SunnyBrain.make_plan()     ← LLM tạo plan (JSON array)
    │
    ▼
PlanExecutor.run()
    │
    ├─ [Lv3] Classic: Tool call → Retry × 3 → Replan
    │
    └─ [Lv4] ReAct Loop:
           Think → Action → Tool → Observe → Critic
           └─ Repeated action guard (chống stuck)
    │
    ▼
SunnyBrain.think_stream()  ← Stream câu trả lời
    │
    ▼
VectorMemory.add()         ← Lưu vào long-term memory
```

---

## 📊 So sánh

| System | Sunny AI v5 |
|---|---|
| LangChain agent | Tương tự core, không dùng framework |
| AutoGPT | Đơn giản hơn, local 100% |
| Open Interpreter | Ngang, thêm ADB + vector memory |
| Ollama | Sunny = Ollama-style + agent layer |

**Agent Level: 4 (ReAct Agent)**

---

## 📄 License

**CC BY-NC 4.0** — Creative Commons Attribution-NonCommercial 4.0

- ✅ Dùng tự do cho mục đích cá nhân và cộng đồng
- ✅ Chia sẻ, chỉnh sửa, học tập thoải mái
- ✅ Phải ghi nguồn tác giả khi chia sẻ
- ❌ Cấm dùng thương mại

Chi tiết: https://creativecommons.org/licenses/by-nc/4.0/

---

<div align="center">

**Sunny AI v5.0 — Local-first AI Agent Framework**

*Build bằng điện thoại + 3 AI miễn phí. Không background IT.*

</div>
