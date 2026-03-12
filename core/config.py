# ==============================================================================
#  SUNNY AI v5.0 — core/config.py
#  Tất cả config tập trung một chỗ.
# ==============================================================================
import os, torch

PERSONA_NAME  = "Sunny"
APP_VERSION   = "5.0"

# ── Optional lib flags ────────────────────────────────────────
try:
    import edge_tts, pygame  # noqa
    HAS_TTS = True
except ImportError:
    HAS_TTS = False

try:
    import speech_recognition  # noqa
    HAS_MIC = True
except ImportError:
    HAS_MIC = False

# ── Security flags ────────────────────────────────────────────
ENABLE_FILE_ACCESS = True
ENABLE_SCAN        = True
ALLOW_INTERNET     = True
ENABLE_PHONE       = True

# ── Sandbox ───────────────────────────────────────────────────
BLOCKED_PATH_PATTERNS = [
    r"(?i)c:\\windows",
    r"(?i)c:\\system32",
    r"(?i)/etc/passwd",
    r"(?i)/etc/shadow",
    r"(?i)/root",
    r"(?i)\.ssh",
    r"(?i)\.env$",
    r"(?i)id_rsa",
    r"(?i)private.?key",
    r"(?i)appdata\\roaming",
]
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.xlsx', '.xls', '.txt', '.csv', '.md'}

# ── File paths ────────────────────────────────────────────────
FILES = {
    "MEMORY"      : "sunny_memory.json",
    "VECTOR_INDEX": "sunny_vector.index",
    "VECTOR_META" : "sunny_vector_meta.json",
    "DIARY"       : "sunny_diary.txt",
    "LOG"         : "sunny_system.log",
    "AUDIT"       : "sunny_audit.jsonl",
    "UPLOAD_DIR"  : "sunny_uploads",
}

# ── Agent settings ────────────────────────────────────────────
MEMORY_LIMIT      = 20
MAX_RESPONSE_LEN  = 4000
PLAN_MAX_STEPS    = 5
PLAN_MAX_RETRIES  = 3
VECTOR_TOP_K      = 3

# ── Model settings ────────────────────────────────────────────
DEVICE         = "cpu"
vram_gb        = 0.0
MODEL_NAME     = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"
MAX_SEQ_LENGTH = 2048
MAX_NEW_TOKENS = 400

def _detect_device():
    global DEVICE, vram_gb, MODEL_NAME, MAX_SEQ_LENGTH, MAX_NEW_TOKENS
    try:
        import bitsandbytes  # noqa
        HAS_BNB = True
    except ImportError:
        HAS_BNB = False

    if torch.cuda.is_available() and HAS_BNB:
        try:
            vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
            if vram_gb >= 7.0:
                DEVICE, MODEL_NAME     = "cuda", "unsloth/Hermes-3-Llama-3.1-8B-bnb-4bit"
                MAX_SEQ_LENGTH, MAX_NEW_TOKENS = 4096, 600
            elif vram_gb >= 3.5:
                DEVICE = "cuda"
                MAX_NEW_TOKENS = 400
        except Exception:
            pass

    if DEVICE == "cpu":
        torch.set_num_threads(min(4, os.cpu_count() or 2))

_detect_device()

# ── Tool schema (dùng cho LLM tool calling) ───────────────────
TOOL_SCHEMA = """Available tools — output ONLY valid JSON:

{ "tool": "web_search",    "input": "<query>" }
{ "tool": "visit_url",     "input": "<https://...>" }
{ "tool": "read_file",     "input": "<absolute path>" }
{ "tool": "scan_folder",   "input": "<absolute path>" }
{ "tool": "scan_temp",     "input": "" }
{ "tool": "delete_temp",   "input": "" }
{ "tool": "phone_control", "input": "<pin|screenshot|home|back>" }
{ "tool": "read_diary",    "input": "" }
{ "tool": "none",          "input": "" }

Rules: ONE tool per step. Output ONLY the JSON. Use "none" if no tool needed."""
